"""Audio: efectos sintetizados al iniciar (sin archivos externos).

Si existe assets/sonidos/<nombre>.wav (u .ogg) se usa ese archivo.
Si el mezclador no está disponible (sin placa de sonido, SDL sin audio, etc.)
el juego sigue funcionando en silencio.

Cada sonido es una "receta" (SOUND_RECIPES): una o más capas que se mezclan.
Una capa es un tono (Tone), un ruido filtrado (Noise) o una serie de notas
(Notes). Frecuencias en Hz, duraciones y comienzos ("at") en segundos,
volúmenes de 0 a 1. "decay" es qué tan rápido se apaga (más = más corto).
"""
import array
import logging
import math
import random
from typing import NamedTuple, Optional, Tuple

import pygame

from .assets import override_path

log = logging.getLogger("fdc.audio")

AUDIO_RATE = 22050          # Hz: frecuencia de muestreo del mezclador de audio
AUDIO_BITS = -16            # muestras de 16 bits con signo (el signo negativo lo indica)
AUDIO_CHANNELS = 1          # sonido mono
AUDIO_BUFFER = 512          # muestras por búfer: poco retraso entre el golpe y el sonido
MIXER_CHANNELS = 16         # sonidos que pueden sonar a la vez
NOISE_SEED = 99             # semilla del ruido: los sonidos salen iguales en cada corrida
HALF_LEVEL = 0.5            # las ondas cuadrada y diente de sierra suenan más fuerte: se bajan a la mitad
NOTE_DECAY = 5              # qué tan rápido se apaga cada nota de una serie
PCM_PEAK = 32000            # valor máximo de una muestra de 16 bits (un poco menos que 32767, sin saturar)
SILENCE = 1e-6              # pico mínimo (evita dividir por cero con un sonido mudo)
CROWD_FADE_IN_MS = 800      # ms: la hinchada aparece de a poco...
CROWD_FADE_OUT_MS = 500     # ...y se va de a poco
CROWD_LOOP = -1             # la hinchada se repite sin fin
TONE_VOLUME = 0.6           # volumen de un tono si la receta no dice otro
TONE_ATTACK = 0.005         # s que tarda un tono en llegar a su volumen
NOISE_VOLUME = 0.5          # volumen de un ruido si la receta no dice otro
NOISE_SMOOTHING = 0.3       # suavizado del ruido (1 = áspero, cerca de 0 = sordo)
NOISE_DECAY = 6.0           # qué tan rápido se apaga un ruido
NOISE_ATTACK = 0.002        # s que tarda un ruido en llegar a su volumen
NOTES_VOLUME = 0.5          # volumen de una serie de notas si la receta no dice otro
# volumen propio de algunos sonidos (los demás suenan a 1)
SOUND_VOLUMES = {"kick": 0.9, "crowd": 0.35}

SOUND_NAMES = ("kick", "whoosh", "bounce", "header", "post", "goal", "whistle", "whistle_end",
               "select", "confirm", "back", "power_good", "power_bad", "power_global", "spawn",
               "bomb_tick", "explosion", "beep", "go", "blocked", "crowd")


class Tone(NamedTuple):
    """Tono que va de f0 a f1 Hz (si f1 falta, se queda en f0)."""
    secs: float
    f0: float
    f1: Optional[float] = None
    wave: str = "sine"              # "sine", "square", "tri" o "saw"
    vol: float = TONE_VOLUME
    attack: float = TONE_ATTACK
    decay: Optional[float] = None   # None: se apaga en línea recta hasta el final
    vib: float = 0.0                # vibrato: cuánto varía la frecuencia (fracción)...
    vib_hz: float = 0.0             # ...y cuántas veces por segundo
    at: float = 0.0


class Noise(NamedTuple):
    """Ruido blanco suavizado (lp: 1 = áspero, cerca de 0 = sordo, como viento)."""
    secs: float
    vol: float = NOISE_VOLUME
    lp: float = NOISE_SMOOTHING
    decay: float = NOISE_DECAY
    attack: float = NOISE_ATTACK
    swell: bool = False             # True: sube y baja (en vez de apagarse)
    at: float = 0.0


class Notes(NamedTuple):
    """Serie de notas iguales, una detrás de otra."""
    freqs: Tuple[float, ...]
    dur: float
    wave: str = "sine"
    vol: float = NOTES_VOLUME
    gap: float = 0.0                # s de silencio entre notas
    at: float = 0.0


WHISTLE = dict(vol=0.35, vib=0.03, vib_hz=38, decay=1)   # silbato del árbitro: tono agudo con vibrato
WHISTLE_HZ = 2900                  # silbato de inicio
FINAL_WHISTLE_HZ = 2850            # silbato final (apenas más grave)
# acordes en Hz: do, mi, sol y do agudo (y mi agudo)
C5, E5, G5, C6, E6 = 523, 659, 784, 1046, 1318

SOUND_RECIPES = {
    "kick": [Tone(0.16, 150, 48, vol=0.9, decay=10), Noise(0.03, 0.5, 0.7, 30)],          # golpe seco
    "whoosh": [Noise(0.16, 0.25, 0.08, 0, swell=True)],                                    # aire de la patada
    "bounce": [Tone(0.07, 420, 300, vol=0.35, decay=14), Noise(0.02, 0.2, 0.5, 40)],       # pique
    "header": [Tone(0.12, 320, 190, vol=0.6, decay=9), Noise(0.03, 0.25, 0.6, 30)],        # cabezazo
    "post": [Tone(0.45, C5, vol=0.3, decay=7), Tone(0.45, 1375, vol=0.18, decay=9),        # travesaño: metal
             Tone(0.35, 2140, vol=0.1, decay=12)],
    "goal": [Noise(1.8, 0.55, 0.12, 0, attack=0.2, swell=True),                            # hinchada + fanfarria
             Notes((C5, E5, G5, C6), 0.16, "square", 0.22, at=0.05)],
    "whistle": [Tone(0.22, WHISTLE_HZ, **WHISTLE), Tone(0.32, WHISTLE_HZ, **WHISTLE, at=0.28)],   # dos pitidos
    "whistle_end": [Tone(0.3, FINAL_WHISTLE_HZ, **WHISTLE), Tone(0.3, FINAL_WHISTLE_HZ, **WHISTLE, at=0.36),
                    Tone(0.7, FINAL_WHISTLE_HZ, **WHISTLE, at=0.72)],                     # dos cortos y uno largo
    "select": [Tone(0.06, 660, 880, "square", 0.22, decay=6)],                             # moverse en un menú
    "confirm": [Notes((660, 990), 0.08, "square", 0.22)],                                  # elegir
    "back": [Notes((660, 440), 0.08, "square", 0.2)],                                      # volver
    "power_good": [Notes((C5, E5, G5, C6, E6), 0.07, "tri", 0.4)],                         # arpegio que sube
    "power_bad": [Tone(0.5, 440, 150, "saw", 0.35, decay=3, vib=0.06, vib_hz=9)],          # tono que se cae
    "power_global": [Noise(0.35, 0.25, 0.1, 0, swell=True), Tone(0.4, 300, 900, "tri", 0.3, decay=3)],
    "spawn": [Tone(0.12, 500, 1100, "sine", 0.3, decay=5)],                                # aparece un poder
    "bomb_tick": [Tone(0.05, 1500, vol=0.3, decay=20)],                                    # tic de la mecha
    "explosion": [Noise(0.9, 0.9, 0.06, 4, attack=0.003), Tone(0.5, 90, 35, vol=0.8, decay=5)],
    "beep": [Tone(0.12, 880, 880, "square", 0.22, decay=4)],                               # cuenta regresiva
    "go": [Tone(0.35, 1320, wave="square", vol=0.25, decay=3)],                            # "¡YA!"
    "blocked": [Tone(0.12, 180, 140, "square", 0.25, decay=6)],                            # acción no permitida
    "crowd": [Noise(3.0, 0.22, 0.05, 0, attack=0.3, swell=True)],                          # murmullo de fondo
}


class Synth:
    def __init__(self, rate):
        self.rate = rate
        self.rng = random.Random(NOISE_SEED)

    def n(self, secs):
        return int(self.rate * secs)

    def tone(self, secs, f0, f1=None, wave="sine", vol=TONE_VOLUME, attack=TONE_ATTACK, decay=None, vib=0.0,
             vib_hz=0.0):
        f1 = f0 if f1 is None else f1
        n = self.n(secs)
        out = [0.0] * n
        phase = 0.0
        for i in range(n):
            t = i / n
            f = f0 * (f1 / f0) ** t if f0 > 0 and f1 > 0 else f0
            if vib:
                f *= 1 + vib * math.sin(2 * math.pi * vib_hz * i / self.rate)
            phase += 2 * math.pi * f / self.rate
            if wave == "sine":
                v = math.sin(phase)
            elif wave == "square":
                v = 1.0 if math.sin(phase) >= 0 else -1.0
                v *= HALF_LEVEL
            elif wave == "tri":
                v = 2 / math.pi * math.asin(math.sin(phase))
            else:  # saw
                v = ((phase / math.pi) % 2) - 1
                v *= HALF_LEVEL
            env = min(1.0, i / max(1, self.n(attack)))
            env *= math.exp(-t * decay) if decay else (1 - t)
            out[i] = v * env * vol
        return out

    def noise(self, secs, vol=NOISE_VOLUME, lp=NOISE_SMOOTHING, decay=NOISE_DECAY, attack=NOISE_ATTACK, swell=False):
        n = self.n(secs)
        out = [0.0] * n
        y = 0.0
        for i in range(n):
            t = i / n
            y += lp * (self.rng.uniform(-1, 1) - y)
            env = min(1.0, i / max(1, self.n(attack)))
            env *= math.sin(math.pi * t) if swell else math.exp(-t * decay)
            out[i] = y * env * vol
        return out

    @staticmethod
    def mix(*tracks, offsets=None):
        offsets = offsets or [0] * len(tracks)
        n = max(len(t) + o for t, o in zip(tracks, offsets))
        out = [0.0] * n
        for tr, o in zip(tracks, offsets):
            for i, v in enumerate(tr):
                out[i + o] += v
        return out

    def seq(self, notes, dur, wave="sine", vol=NOTES_VOLUME, gap=0.0):
        tracks, offs = [], []
        for k, f in enumerate(notes):
            tracks.append(self.tone(dur, f, wave=wave, vol=vol, decay=NOTE_DECAY))
            offs.append(self.n(k * (dur + gap)))
        return self.mix(*tracks, offsets=offs)

    def layer(self, part):
        """Muestras de una capa de una receta."""
        if isinstance(part, Tone):
            return self.tone(part.secs, part.f0, part.f1, part.wave, part.vol, part.attack, part.decay, part.vib,
                             part.vib_hz)
        if isinstance(part, Noise):
            return self.noise(part.secs, part.vol, part.lp, part.decay, part.attack, part.swell)
        return self.seq(part.freqs, part.dur, part.wave, part.vol, part.gap)


def build_samples(rate):
    s = Synth(rate)
    return {name: s.mix(*[s.layer(part) for part in parts], offsets=[s.n(part.at) for part in parts])
            for name, parts in SOUND_RECIPES.items()}


class Audio:
    def __init__(self, enabled=True):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        self.crowd_channel = None
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(AUDIO_RATE, AUDIO_BITS, AUDIO_CHANNELS, AUDIO_BUFFER)
            freq, size, channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(MIXER_CHANNELS)
        except (pygame.error, TypeError) as exc:
            log.warning("audio no disponible, el juego sigue en silencio: %s", exc)
            return
        try:
            samples = build_samples(freq)
            for name, data in samples.items():
                self.sounds[name] = self._load_override(name) or self._to_sound(data, channels)
            for name, volume in SOUND_VOLUMES.items():
                self.sounds[name].set_volume(volume)
            self.enabled = True
        except pygame.error as exc:
            log.warning("no se pudieron crear los sonidos: %s", exc)

    @staticmethod
    def _load_override(name):
        for ext in ("wav", "ogg"):
            path = override_path("sonidos", f"{name}.{ext}")
            if path:
                try:
                    return pygame.mixer.Sound(path)
                except pygame.error as exc:
                    log.warning("no se pudo cargar %s: %s", path, exc)
        return None

    @staticmethod
    def _to_sound(data, channels):
        peak = max(SILENCE, max(abs(v) for v in data))
        scale = PCM_PEAK / peak if peak > 1.0 else PCM_PEAK   # normaliza sólo si satura
        buf = array.array("h")
        for v in data:
            buf.extend([int(v * scale)] * channels)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name, volume=1.0):
        if not self.enabled or self.muted:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        ch = snd.play()
        if ch is not None and volume != 1.0:
            ch.set_volume(volume)

    def crowd(self, on):
        if not self.enabled:
            return
        if on and not self.muted:
            if self.crowd_channel is None or not self.crowd_channel.get_busy():
                self.crowd_channel = self.sounds["crowd"].play(loops=CROWD_LOOP, fade_ms=CROWD_FADE_IN_MS)
        elif self.crowd_channel is not None:
            self.crowd_channel.fadeout(CROWD_FADE_OUT_MS)
            self.crowd_channel = None

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.stop()
            self.crowd_channel = None
        return self.muted
