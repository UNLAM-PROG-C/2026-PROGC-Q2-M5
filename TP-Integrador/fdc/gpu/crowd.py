"""Animated crowd of the stands (F11): only in the FULL mode.

The band of the stadium is repainted every frame by `k_tribuna` (or by its
numpy version): seats, one person per seat and some flags, all from a hash
of the seat, so the kernel needs no shared memory and no atomics.

On the CPU this is the most expensive stage of the chain and that is on
purpose: it is what makes a notebook without NVIDIA stutter in FULL and run
smooth in OPTIMIZADO. On the GPU it is one more measured kernel.
"""
import pygame

from fdc import config

G = config.Gpu
CROWD = "tribuna"           # name of the stage in the metrics and the overlay
NO_TEAM = -1                # nobody is celebrating: the stands just move
NO_BOOST = 0.0              # stands at rest (no goal)
FULL_BOOST = 1.0            # stands jumping as hard as they can
SCORER_KEYS = ("scorer", "side")   # who scored, or which goal it was


def band(size):
    """(x, y, width, height) of the stands inside a screen of `size`."""
    width, height = size
    top = max(0, min(G.CROWD_TOP, height))
    bottom = max(top, min(G.CROWD_BOTTOM, height))
    return pygame.Rect(0, top, width, bottom - top)


def params():
    """(cfg, pal) of the kernel: seat geometry and the colours of the day."""
    return _cfg(), _pal()


def _cfg():
    """Parameters of the kernel: the seat, the person and the animation."""
    seat_w, seat_h = G.CROWD_SEAT
    body_w, body_h = G.CROWD_BODY
    flag_w, flag_h = G.CROWD_FLAG
    return (float(seat_w), float(seat_h), G.CROWD_JUMP, G.CROWD_JUMP_HZ,
            G.CROWD_GOAL_JUMP, G.CROWD_GOAL_HZ, G.CROWD_WAVE,
            float(flag_w), float(flag_h), float(G.CROWD_FILL),
            float(G.CROWD_FLAGS), float(body_w), float(body_h),
            float(G.CROWD_HEAD), float(G.CROWD_STEP), float(G.CROWD_POLE),
            G.CROWD_SHADE_TOP, G.CROWD_SHADE_BOTTOM, G.CROWD_VAR_MIN,
            G.CROWD_VAR_RANGE, G.CROWD_HEAD_CUT, G.CROWD_OUTLINE,
            G.CROWD_SHOULDER_EDGE, G.CROWD_SHOULDER_SHADE)


def _pal():
    """Colours of the kernel: shirts, skins, hairs, steps, flags and rim."""
    colours = (G.CROWD_SHIRTS + G.CROWD_SKINS + G.CROWD_HAIRS
               + (G.CROWD_TREAD, G.CROWD_RISER, G.CROWD_EDGE,
                  G.CROWD_POLE_COLOUR, G.CROWD_FLAG_WHITE)
               + G.CROWD_FLAG_COLOURS + (G.CROWD_OUTLINE_COLOUR,))
    return tuple(channel for colour in colours for channel in colour)


def scene(celebration, clock):
    """(side, boost) of the stands: the scorer's half jumps, fading out."""
    if celebration is None:
        return NO_TEAM, NO_BOOST
    side = NO_TEAM
    for key in SCORER_KEYS:
        value = celebration.goal.get(key)
        if value is not None:
            side = int(value)
            break
    left = FULL_BOOST - celebration.progress(clock)
    return side, max(NO_BOOST, left * left)
