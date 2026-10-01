"""Audio: efectos sintetizados al iniciar (sin archivos externos).

Si existe assets/sonidos/<nombre>.wav (u .ogg) se usa ese archivo.
Si el mezclador no está disponible (sin placa de sonido, SDL sin audio, etc.)
el juego sigue funcionando en silencio.
"""
import array
import logging
import math
import random

import pygame

from .assets import override_path

log = logging.getLogger("fdc.audio")

SOUND_NAMES = ("kick", "whoosh", "bounce", "header", "post", "goal", "whistle", "whistle_end",
               "select", "confirm", "back", "power_good", "power_bad", "power_global", "spawn",
               "bomb_tick", "explosion", "beep", "go", "blocked", "crowd")


class Synth:
    def __init__(self, rate):
        self.rate = rate
        self.rng = random.Random(99)

    def n(self, secs):
        return int(self.rate * secs)

    def tone(self, secs, f0, f1=None, wave="sine", vol=0.6, attack=0.005, decay=None, vib=0.0, vib_hz=0.0):
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
                v *= 0.5
            elif wave == "tri":
                v = 2 / math.pi * math.asin(math.sin(phase))
            else:  # saw
                v = ((phase / math.pi) % 2) - 1
                v *= 0.5
            env = min(1.0, i / max(1, self.n(attack)))
            env *= math.exp(-t * decay) if decay else (1 - t)
            out[i] = v * env * vol
        return out

    def noise(self, secs, vol=0.5, lp=0.3, decay=6.0, attack=0.002, swell=False):
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

    def seq(self, notes, dur, wave="sine", vol=0.5, gap=0.0):
        tracks, offs = [], []
        for k, f in enumerate(notes):
            tracks.append(self.tone(dur, f, wave=wave, vol=vol, decay=5))
            offs.append(self.n(k * (dur + gap)))
        return self.mix(*tracks, offsets=offs)


def build_samples(rate):
    s = Synth(rate)
    return {
        "kick": s.mix(s.tone(0.16, 150, 48, vol=0.9, decay=10), s.noise(0.03, 0.5, 0.7, 30)),
        "whoosh": s.noise(0.16, 0.25, 0.08, 0, swell=True),
        "bounce": s.mix(s.tone(0.07, 420, 300, vol=0.35, decay=14), s.noise(0.02, 0.2, 0.5, 40)),
        "header": s.mix(s.tone(0.12, 320, 190, vol=0.6, decay=9), s.noise(0.03, 0.25, 0.6, 30)),
        "post": s.mix(s.tone(0.45, 523, vol=0.3, decay=7), s.tone(0.45, 1375, vol=0.18, decay=9),
                      s.tone(0.35, 2140, vol=0.1, decay=12)),
        "goal": s.mix(s.noise(1.8, 0.55, 0.12, 0, attack=0.2, swell=True),
                      s.seq([523, 659, 784, 1046], 0.16, "square", 0.22),
                      offsets=[0, s.n(0.05)]),
        "whistle": s.mix(s.tone(0.22, 2900, vol=0.35, vib=0.03, vib_hz=38, decay=1),
                         s.tone(0.32, 2900, vol=0.35, vib=0.03, vib_hz=38, decay=1),
                         offsets=[0, s.n(0.28)]),
        "whistle_end": s.mix(*[s.tone(0.3 if k < 2 else 0.7, 2850, vol=0.35, vib=0.03, vib_hz=38, decay=1)
                               for k in range(3)], offsets=[0, s.n(0.36), s.n(0.72)]),
        "select": s.tone(0.06, 660, 880, "square", 0.22, decay=6),
        "confirm": s.seq([660, 990], 0.08, "square", 0.22),
        "back": s.seq([660, 440], 0.08, "square", 0.2),
        "power_good": s.seq([523, 659, 784, 1046, 1318], 0.07, "tri", 0.4),
        "power_bad": s.mix(s.tone(0.5, 440, 150, "saw", 0.35, decay=3, vib=0.06, vib_hz=9)),
        "power_global": s.mix(s.noise(0.35, 0.25, 0.1, 0, swell=True), s.tone(0.4, 300, 900, "tri", 0.3, decay=3)),
        "spawn": s.tone(0.12, 500, 1100, "sine", 0.3, decay=5),
        "bomb_tick": s.tone(0.05, 1500, vol=0.3, decay=20),
        "explosion": s.mix(s.noise(0.9, 0.9, 0.06, 4, attack=0.003), s.tone(0.5, 90, 35, vol=0.8, decay=5)),
        "beep": s.tone(0.12, 880, 880, "square", 0.22, decay=4),
        "go": s.tone(0.35, 1320, wave="square", vol=0.25, decay=3),
        "blocked": s.tone(0.12, 180, 140, "square", 0.25, decay=6),
        "crowd": s.noise(3.0, 0.22, 0.05, 0, attack=0.3, swell=True),
    }


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
                pygame.mixer.init(22050, -16, 1, 512)
            freq, size, channels = pygame.mixer.get_init()
            pygame.mixer.set_num_channels(16)
        except (pygame.error, TypeError) as exc:
            log.warning("audio no disponible, el juego sigue en silencio: %s", exc)
            return
        try:
            samples = build_samples(freq)
            for name, data in samples.items():
                self.sounds[name] = self._load_override(name) or self._to_sound(data, channels)
            self.sounds["kick"].set_volume(0.9)
            self.sounds["crowd"].set_volume(0.35)
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
        peak = max(1e-6, max(abs(v) for v in data))
        scale = 32000 / peak if peak > 1.0 else 32000   # normaliza sólo si satura
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
                self.crowd_channel = self.sounds["crowd"].play(loops=-1, fade_ms=800)
        elif self.crowd_channel is not None:
            self.crowd_channel.fadeout(500)
            self.crowd_channel = None

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.stop()
            self.crowd_channel = None
        return self.muted
