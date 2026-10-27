"""Audio: effects synthesized at start-up (no external files).

If assets/sounds/<name>.wav (or .ogg) exists, that file is used. If the
mixer is not available (no sound card, SDL without audio, etc.) the game
keeps working in silence.

Each sound is a "recipe" (SOUND_RECIPES): one or more layers that are
mixed. A layer is a tone (Tone), filtered noise (Noise) or a series of
notes (Notes). Frequencies in Hz, durations and starts ("at") in seconds,
volumes from 0 to 1. "decay" is how fast it fades (more = shorter).
"""
import array
import logging
import math
import random
import typing

import pygame

from fdc.ui import assets

log = logging.getLogger("fdc.audio")

AUDIO_RATE = 22050          # Hz: sample rate of the audio mixer
AUDIO_BITS = -16            # signed 16-bit samples (negative means signed)
AUDIO_CHANNELS = 1          # mono sound
AUDIO_BUFFER = 512          # samples per buffer: little delay hit -> sound
MIXER_CHANNELS = 16         # sounds that can play at the same time
NOISE_SEED = 99             # noise seed: sounds are equal on every run
HALF_LEVEL = 0.5            # square and saw waves sound louder: halved
NOTE_DECAY = 5              # how fast each note of a series fades
# Peak of a 16-bit sample (a bit less than 32767, so it never clips).
PCM_PEAK = 32000
SILENCE = 1e-6              # minimum peak (avoids dividing by zero)
CROWD_FADE_IN_MS = 800      # ms: the crowd comes in slowly...
CROWD_FADE_OUT_MS = 500     # ...and goes away slowly
CROWD_LOOP = -1             # the crowd loops forever
TONE_VOLUME = 0.6           # volume of a tone if the recipe does not say
TONE_ATTACK = 0.005         # s a tone takes to reach its volume
NOISE_VOLUME = 0.5          # volume of a noise if the recipe does not say
NOISE_SMOOTHING = 0.3       # noise smoothing (1 = harsh, near 0 = dull)
NOISE_DECAY = 6.0           # how fast a noise fades
NOISE_ATTACK = 0.002        # s a noise takes to reach its volume
NOTES_VOLUME = 0.5          # volume of a series of notes by default
# Own volume of some sounds (the others play at 1).
SOUND_VOLUMES = {"kick": 0.9, "crowd": 0.35}
OVERRIDE_EXTENSIONS = ("wav", "ogg")

SOUND_NAMES = ("kick", "whoosh", "bounce", "header", "post", "goal",
               "whistle", "whistle_end", "select", "confirm", "back",
               "power_good", "power_bad", "power_global", "spawn",
               "bomb_tick", "explosion", "beep", "go", "blocked", "crowd")


class Tone(typing.NamedTuple):
    """Tone that goes from f0 to f1 Hz (if f1 is missing, it stays)."""
    secs: float
    f0: float
    f1: typing.Optional[float] = None
    wave: str = "sine"              # "sine", "square", "tri" or "saw"
    vol: float = TONE_VOLUME
    attack: float = TONE_ATTACK
    decay: typing.Optional[float] = None   # None: fades in a straight line
    vib: float = 0.0                # vibrato: how much the frequency varies...
    vib_hz: float = 0.0             # ...and how many times per second
    at: float = 0.0


class Noise(typing.NamedTuple):
    """Smoothed white noise (lp: 1 = harsh, near 0 = dull, like wind)."""
    secs: float
    vol: float = NOISE_VOLUME
    lp: float = NOISE_SMOOTHING
    decay: float = NOISE_DECAY
    attack: float = NOISE_ATTACK
    swell: bool = False             # True: rises and falls (does not fade)
    at: float = 0.0


class Notes(typing.NamedTuple):
    """Series of equal notes, one after the other."""
    freqs: typing.Tuple[float, ...]
    dur: float
    wave: str = "sine"
    vol: float = NOTES_VOLUME
    gap: float = 0.0                # s of silence between notes
    at: float = 0.0


# Referee whistle: high tone with vibrato.
WHISTLE = {"vol": 0.35, "vib": 0.03, "vib_hz": 38, "decay": 1}
WHISTLE_HZ = 2900                  # start whistle (Hz)
FINAL_WHISTLE_HZ = 2850            # final whistle (a bit lower, Hz)
# Chords in Hz: C, E, G and high C (and high E).
C5, E5, G5, C6, E6 = 523, 659, 784, 1046, 1318

SOUND_RECIPES = {
    # Dry hit.
    "kick": [Tone(0.16, 150, 48, vol=0.9, decay=10),
             Noise(0.03, 0.5, 0.7, 30)],
    # Air of the kick.
    "whoosh": [Noise(0.16, 0.25, 0.08, 0, swell=True)],
    # Bounce.
    "bounce": [Tone(0.07, 420, 300, vol=0.35, decay=14),
               Noise(0.02, 0.2, 0.5, 40)],
    # Header.
    "header": [Tone(0.12, 320, 190, vol=0.6, decay=9),
               Noise(0.03, 0.25, 0.6, 30)],
    # Crossbar: metal.
    "post": [Tone(0.45, C5, vol=0.3, decay=7),
             Tone(0.45, 1375, vol=0.18, decay=9),
             Tone(0.35, 2140, vol=0.1, decay=12)],
    # Crowd plus fanfare.
    "goal": [Noise(1.8, 0.55, 0.12, 0, attack=0.2, swell=True),
             Notes((C5, E5, G5, C6), 0.16, "square", 0.22, at=0.05)],
    # Two whistles.
    "whistle": [Tone(0.22, WHISTLE_HZ, **WHISTLE),
                Tone(0.32, WHISTLE_HZ, **WHISTLE, at=0.28)],
    # Two short whistles and a long one.
    "whistle_end": [Tone(0.3, FINAL_WHISTLE_HZ, **WHISTLE),
                    Tone(0.3, FINAL_WHISTLE_HZ, **WHISTLE, at=0.36),
                    Tone(0.7, FINAL_WHISTLE_HZ, **WHISTLE, at=0.72)],
    # Moving in a menu.
    "select": [Tone(0.06, 660, 880, "square", 0.22, decay=6)],
    # Choosing.
    "confirm": [Notes((660, 990), 0.08, "square", 0.22)],
    # Going back.
    "back": [Notes((660, 440), 0.08, "square", 0.2)],
    # Rising arpeggio.
    "power_good": [Notes((C5, E5, G5, C6, E6), 0.07, "tri", 0.4)],
    # Falling tone.
    "power_bad": [Tone(0.5, 440, 150, "saw", 0.35, decay=3, vib=0.06,
                       vib_hz=9)],
    # Swell of wind and a rising tone.
    "power_global": [Noise(0.35, 0.25, 0.1, 0, swell=True),
                     Tone(0.4, 300, 900, "tri", 0.3, decay=3)],
    # A power appears.
    "spawn": [Tone(0.12, 500, 1100, "sine", 0.3, decay=5)],
    # Tick of the fuse.
    "bomb_tick": [Tone(0.05, 1500, vol=0.3, decay=20)],
    # Blast and a deep rumble.
    "explosion": [Noise(0.9, 0.9, 0.06, 4, attack=0.003),
                  Tone(0.5, 90, 35, vol=0.8, decay=5)],
    # Countdown.
    "beep": [Tone(0.12, 880, 880, "square", 0.22, decay=4)],
    # Start of play after the countdown.
    "go": [Tone(0.35, 1320, wave="square", vol=0.25, decay=3)],
    # Action not allowed.
    "blocked": [Tone(0.12, 180, 140, "square", 0.25, decay=6)],
    # Background murmur.
    "crowd": [Noise(3.0, 0.22, 0.05, 0, attack=0.3, swell=True)],
}


def _wave(wave, phase):
    """Value of one sample of the wave at that phase."""
    if wave == "sine":
        return math.sin(phase)
    if wave == "square":
        v = 1.0 if math.sin(phase) >= 0 else -1.0
        return v * HALF_LEVEL
    if wave == "tri":
        return 2 / math.pi * math.asin(math.sin(phase))
    v = ((phase / math.pi) % 2) - 1     # saw
    return v * HALF_LEVEL


def mix(*tracks, offsets=None):
    """Adds the tracks, each one starting at its offset (samples)."""
    offsets = offsets or [0] * len(tracks)
    n = max(len(t) + o for t, o in zip(tracks, offsets))
    out = [0.0] * n
    for tr, o in zip(tracks, offsets):
        for i, v in enumerate(tr):
            out[i + o] += v
    return out


class Synth:
    """Tiny synthesizer that turns the recipes into samples."""

    def __init__(self, rate):
        self.rate = rate
        self.rng = random.Random(NOISE_SEED)

    def n(self, secs):
        """Samples in that many seconds."""
        return int(self.rate * secs)

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def tone(self, secs, f0, f1=None, wave="sine", vol=TONE_VOLUME,
             attack=TONE_ATTACK, decay=None, vib=0.0, vib_hz=0.0):
        f1 = f0 if f1 is None else f1
        n = self.n(secs)
        out = [0.0] * n
        phase = 0.0
        for i in range(n):
            t = i / n
            phase += 2 * math.pi * self._frequency(i, t, f0, f1, vib,
                                                   vib_hz) / self.rate
            env = min(1.0, i / max(1, self.n(attack)))
            env *= math.exp(-t * decay) if decay else (1 - t)
            out[i] = _wave(wave, phase) * env * vol
        return out

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def _frequency(self, i, t, f0, f1, vib, vib_hz):
        f = f0 * (f1 / f0) ** t if f0 > 0 and f1 > 0 else f0
        if vib:
            f *= 1 + vib * math.sin(2 * math.pi * vib_hz * i / self.rate)
        return f

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def noise(self, secs, vol=NOISE_VOLUME, lp=NOISE_SMOOTHING,
              decay=NOISE_DECAY, attack=NOISE_ATTACK, swell=False):
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

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def seq(self, notes, dur, wave="sine", vol=NOTES_VOLUME, gap=0.0):
        tracks, offs = [], []
        for k, f in enumerate(notes):
            tracks.append(self.tone(dur, f, wave=wave, vol=vol,
                                    decay=NOTE_DECAY))
            offs.append(self.n(k * (dur + gap)))
        return mix(*tracks, offsets=offs)

    def layer(self, part):
        """Samples of one layer of a recipe."""
        if isinstance(part, Tone):
            return self.tone(part.secs, part.f0, part.f1, part.wave, part.vol,
                             part.attack, part.decay, part.vib, part.vib_hz)
        if isinstance(part, Noise):
            return self.noise(part.secs, part.vol, part.lp, part.decay,
                              part.attack, part.swell)
        return self.seq(part.freqs, part.dur, part.wave, part.vol, part.gap)


def build_samples(rate):
    """{name: samples} of every recipe."""
    s = Synth(rate)
    return {name: mix(*[s.layer(part) for part in parts],
                      offsets=[s.n(part.at) for part in parts])
            for name, parts in SOUND_RECIPES.items()}


def _load_override(name):
    for ext in OVERRIDE_EXTENSIONS:
        path = assets.override_path("sounds", f"{name}.{ext}")
        if path:
            try:
                return pygame.mixer.Sound(path)
            except pygame.error as exc:
                log.warning("could not load %s: %s", path, exc)
    return None


def _to_sound(data, channels):
    peak = max(SILENCE, max(abs(v) for v in data))
    # Normalizes only if it clips.
    scale = PCM_PEAK / peak if peak > 1.0 else PCM_PEAK
    buf = array.array("h")
    for v in data:
        buf.extend([int(v * scale)] * channels)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _open_mixer():
    """(frequency, channels) of the mixer, or None if there is no audio."""
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(AUDIO_RATE, AUDIO_BITS, AUDIO_CHANNELS,
                              AUDIO_BUFFER)
        freq, _, channels = pygame.mixer.get_init()
        pygame.mixer.set_num_channels(MIXER_CHANNELS)
    except (pygame.error, TypeError) as exc:
        log.warning("audio not available, the game goes on in silence: %s",
                    exc)
        return None
    return freq, channels


class Audio:
    """Plays the sounds; does nothing when audio is off or missing."""

    def __init__(self, enabled=True):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        self.crowd_channel = None
        mixer = _open_mixer() if enabled else None
        if mixer is None:
            return
        try:
            self._create_sounds(*mixer)
            self.enabled = True
        except pygame.error as exc:
            log.warning("could not create the sounds: %s", exc)

    def _create_sounds(self, freq, channels):
        for name, data in build_samples(freq).items():
            self.sounds[name] = (_load_override(name)
                                 or _to_sound(data, channels))
        for name, volume in SOUND_VOLUMES.items():
            self.sounds[name].set_volume(volume)

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
        """Starts or fades out the background crowd loop."""
        if not self.enabled:
            return
        if on and not self.muted:
            if self.crowd_channel is None or not self.crowd_channel.get_busy():
                self.crowd_channel = self.sounds["crowd"].play(
                    loops=CROWD_LOOP, fade_ms=CROWD_FADE_IN_MS)
        elif self.crowd_channel is not None:
            self.crowd_channel.fadeout(CROWD_FADE_OUT_MS)
            self.crowd_channel = None

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            pygame.mixer.stop()
            self.crowd_channel = None
        return self.muted
