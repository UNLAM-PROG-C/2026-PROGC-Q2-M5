"""Pixel art characters: a big head plus a boot that moves.

The sprites (assets/characters/) look to the LEFT; for the right they are
mirrored. The boot hangs from an invisible "hip" below the centre of the
head: at rest it stays behind (as in the original drawings) and when
kicking it sweeps forward in an arc while it turns. Everything is composed
at native resolution and scaled x2 (retro.PX) without smoothing.

Flyweight pattern: every composed frame is cached and shared by all the
players that use the same character, angle and effects.
"""
import json
import math
import os

import pygame

from fdc import config
from fdc.ui import assets
from fdc.ui import characters
from fdc.ui import layout
from fdc.ui import palette
from fdc.ui import retro

SPRITE_DIR = os.path.join(assets.ROOT, "assets", "characters")
# Hip relative to the head centre (native px, looking to the left).
HIP = (2.0, 12.0)
CANVAS = (84, 76)          # native composition canvas (px)
ORIGIN = (42, 70)          # position of the sole inside the canvas (px)
FRONT_ANGLE = -40          # from this angle the boot is drawn over the head
MASK_THRESHOLD = 20        # minimum opacity of a pixel in the silhouette
# Translucent light blue that covers a frozen player (r, g, b, a).
ICE_TINT = (150, 215, 255, 120)
CACHE_LIMIT = 3000         # frame combinations kept before emptying the cache
PORTRAIT_SIZE = (150, 180)  # px: card of the character selection
PORTRAIT_SHIRT_SHARE = 0.35  # card background: 35 % the shirt colour...
PORTRAIT_WHITE_SHARE = 0.65  # ...and 65 % white (light tone)
PORTRAIT_STRIPE_SHARE = 0.25  # stripes: 25 % the secondary colour...
PORTRAIT_STRIPE_WHITE = 0.75  # ...and 75 % white
PORTRAIT_STRIPE_EVERY = 10  # native px between diagonal stripes
PORTRAIT_STRIPE_W = 5       # native px: width of each stripe
PORTRAIT_BAND_H = 14        # native px: bottom band with the shirt colour
PORTRAIT_BAND_LINE = 2      # native px: secondary colour line over that band
PORTRAIT_HEAD_TOP = 6       # native px from the card top to the head
# The colour rim is made by shifting the silhouette 1 px each way.
RIM_OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1))
SCALE_DECIMALS = 2         # decimals of the scale in the cache key
IDLE_PHASE_SHIFT = 0.5     # sway offset between the two players


def celebrate_pose(t):
  """(boot angle, head hop) of a celebrating player: kicks and hops."""
  return (-layout.CELEBRATE_KICK_ANGLE
          + layout.CELEBRATE_KICK_ANGLE
          * math.sin(t * layout.CELEBRATE_KICK_HZ),
          -int(abs(math.sin(t * layout.CELEBRATE_HOP_HZ))
               * layout.CELEBRATE_HOP_PX))


def idle_pose(t, i=0):
  """(boot angle, head hop) of an idle player; 'i' is the player."""
  phase = (t * layout.IDLE_BOB_HZ + i * IDLE_PHASE_SHIFT) % 2
  return 0, (-1 if phase < 1 else 0)


def _rot(vx, vy, deg):
  """Rotation on screen (y down), same sense as pygame.transform.rotate."""
  a = math.radians(deg)
  return (vx * math.cos(a) + vy * math.sin(a),
          -vx * math.sin(a) + vy * math.cos(a))


def _read_meta():
  path = os.path.join(SPRITE_DIR, "sprites.json")
  with open(path, encoding="utf-8") as fh:
    return json.load(fh)


def _load(name):
  return pygame.image.load(os.path.join(SPRITE_DIR, name)).convert_alpha()


def _flip(img):
  return pygame.transform.flip(img, True, False)


def _silhouette(canvas, color):
  return pygame.mask.from_surface(canvas, MASK_THRESHOLD).to_surface(
      setcolor=color, unsetcolor=(0, 0, 0, 0))


def _with_rim(canvas, rim):
  sil = _silhouette(canvas, (*rim, palette.OPAQUE))
  out = pygame.Surface(CANVAS, pygame.SRCALPHA)
  for dx, dy in RIM_OFFSETS:
    out.blit(sil, (dx, dy))
  out.blit(canvas, (0, 0))
  return out


def _stripes(card, color, nw, nh):
  stripe = PORTRAIT_STRIPE_W
  for x in range(-nh, nw, PORTRAIT_STRIPE_EVERY):
    pygame.draw.polygon(card, color, [
        (x, nh), (x + stripe, nh), (x + stripe + nh, 0), (x + nh, 0)])


def _light(color, share, white_share):
  white = palette.MAX_CHANNEL
  return tuple(min(white, int(v * share + white * white_share))
               for v in color)


class CharacterSprites:
  """Cache heads, boots, portraits and custom player sprites.

  Player sprites are composed surfaces, not pygame.sprite.Sprite instances.
  """

  def __init__(self):
    self.meta = _read_meta()
    self.heads = {}
    for cid, info in self.meta["heads"].items():
      self._load_head(cid, info["file"])
    self.boot_angles = sorted(self.meta["boot"]["angles"])
    self.boots = {}
    for ang in self.boot_angles:
      self._load_boot(ang)
    self.cache = {}
    self.portraits = {}
    self.minis = {}
    self._layout = {}

  def _load_head(self, cid, name):
    img = _load(name)
    self.heads[(cid, -1)] = img
    self.heads[(cid, 1)] = _flip(img)

  def _load_boot(self, ang):
    frame = self.meta["boot"]["frames"][str(ang)]
    img = _load(frame["file"])
    px, py = frame["pivot"]
    self.boots[(ang, -1)] = (img, (px, py))
    self.boots[(ang, 1)] = (_flip(img), (img.get_width() - px, py))

  # ------------------------------------------------------------ geometry
  def _frame_angle(self, ang):
    return min(self.boot_angles, key=lambda a: abs(a - ang))

  def layout(self, cid):
    """Native positions (looking to the left) relative to the sole."""
    if cid not in self._layout:
      self._layout[cid] = self._measure(cid)
    return self._layout[cid]

  def _measure(self, cid):
    info = self.meta["heads"][cid]
    head_c = (0.0, -config.PlayerSpec.HEAD_OFFSET_Y / retro.PX)
    ax, ay = info["anchor"]
    head_tl = (head_c[0] - ax, head_c[1] - ay)
    bx = info["boot_pivot"][0]
    rest_img, (_, rpy) = self.boots[(0, -1)]
    # The ankle at rest stays where the original drew it, but with the
    # sole on the floor.
    p0 = (head_tl[0] + bx, -(rest_img.get_height() - rpy))
    hip = (head_c[0] + HIP[0], head_c[1] + HIP[1])
    return {"head_c": head_c, "head_tl": head_tl, "anchor": (ax, ay),
            "hip": hip, "r0": (p0[0] - hip[0], p0[1] - hip[1])}

  # ------------------------------------------------------------ composition
  def compose(self, cid, facing, leg_angle=0.0, bob=0, rim=None,
              frozen=False):
    """NATIVE surface of the whole player (with rim) and sole position."""
    f = 1 if facing >= 0 else -1
    ang = self._frame_angle(leg_angle)
    key = (cid, f, ang, int(bob), rim, frozen)
    hit = self.cache.get(key)
    if hit:
      return hit
    canvas = self._draw_player(cid, f, ang, bob, rim, frozen)
    if len(self.cache) > CACHE_LIMIT:
      self.cache.clear()
    self.cache[key] = (canvas, ORIGIN)
    return self.cache[key]

  def _draw_player(self, cid, f, ang, bob, rim, frozen):
    canvas = self._draw_body(cid, f, ang, bob)
    if frozen:
      canvas.blit(_silhouette(canvas, ICE_TINT), (0, 0))
    return _with_rim(canvas, rim) if rim else canvas

  def _draw_body(self, cid, f, ang, bob):
    lay = self.layout(cid)
    canvas = pygame.Surface(CANVAS, pygame.SRCALPHA)
    head = self.heads[(cid, f)]
    head_pos = self._head_position(lay, head, f, bob)
    boot, boot_pos = self._boot_frame(lay, f, ang, bob)
    front = ang <= FRONT_ANGLE
    if not front:
      canvas.blit(boot, boot_pos)
    canvas.blit(head, (round(head_pos[0]), round(head_pos[1])))
    if front:
      canvas.blit(boot, boot_pos)
    return canvas

  def _head_position(self, lay, head, f, bob):
    ox, oy = ORIGIN
    hx = (lay["head_tl"][0] if f == -1
          else -(lay["head_tl"][0] + head.get_width()))
    return (ox + hx, oy + lay["head_tl"][1] + bob)

  def _boot_frame(self, lay, f, ang, bob):
    """Boot image (mirrored for the right) and its top-left corner."""
    ox, oy = ORIGIN
    rx, ry = _rot(lay["r0"][0], lay["r0"][1], ang)
    hip_x = lay["hip"][0] + rx
    pivot = (ox + (hip_x if f == -1 else -hip_x),
             oy + lay["hip"][1] + ry + bob * 0.5)
    boot, (bpx, bpy) = self.boots[(ang, f)]
    return boot, (round(pivot[0] - bpx), round(pivot[1] - bpy))

  def player(self, cid, facing, leg_angle=0.0, bob=0, rim=None,
             frozen=False, scale=1.0):
    """Logical surface (x2) and the sole position inside it."""
    native, (ox, oy) = self.compose(cid, facing, leg_angle, bob, rim,
                                    frozen)
    k = retro.PX * scale
    key = ("big", cid, 1 if facing >= 0 else -1,
           self._frame_angle(leg_angle), int(bob), rim, frozen,
           round(scale, SCALE_DECIMALS))
    if key not in self.cache:
      w, h = native.get_size()
      self.cache[key] = pygame.transform.scale(
          native, (max(1, round(w * k)), max(1, round(h * k))))
    return self.cache[key], (ox * k, oy * k)

  # ------------------------------------------------------------ portraits
  def head(self, cid, facing=-1):
    """Native head image looking to the given side."""
    return self.heads[(cid, 1 if facing >= 0 else -1)]

  def mini_head(self, cid, scale=1, facing=-1):
    """Head scaled by an integer factor (cached)."""
    key = (cid, scale, facing)
    if key not in self.minis:
      h = self.head(cid, facing)
      self.minis[key] = pygame.transform.scale(
          h, (h.get_width() * scale, h.get_height() * scale))
    return self.minis[key]

  def portrait(self, cid, w=PORTRAIT_SIZE[0], h=PORTRAIT_SIZE[1]):
    """Retro card: stripes with the shirt colours and the head."""
    key = (cid, w, h)
    if key not in self.portraits:
      self.portraits[key] = self._draw_portrait(cid, w, h)
    return self.portraits[key]

  def _draw_portrait(self, cid, w, h):
    c1, c2 = characters.CHARACTERS_BY_ID[cid]["colors"]
    nw, nh = w // retro.PX, h // retro.PX
    card = pygame.Surface((nw, nh))
    card.fill(_light(c1, PORTRAIT_SHIRT_SHARE, PORTRAIT_WHITE_SHARE))
    light2 = _light(c2, PORTRAIT_STRIPE_SHARE, PORTRAIT_STRIPE_WHITE)
    _stripes(card, light2, nw, nh)
    band_top = nh - PORTRAIT_BAND_H
    pygame.draw.rect(card, c1, (0, band_top, nw, PORTRAIT_BAND_H))
    pygame.draw.rect(card, c2, (0, band_top, nw, PORTRAIT_BAND_LINE))
    head = self.heads[(cid, -1)]
    card.blit(head, ((nw - head.get_width()) // 2, PORTRAIT_HEAD_TOP))
    return pygame.transform.scale(card, (nw * retro.PX, nh * retro.PX))

  def warm(self, cid):
    """Precomputes the most used frames (avoids hiccups in the match)."""
    for f in (-1, 1):
      for ang in self.boot_angles:
        self.compose(cid, f, ang)
