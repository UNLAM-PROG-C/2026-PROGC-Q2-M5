"""Automatic rival of the tournament.

It plays "like one more person": it looks at the latest match state (the
same dictionary the interface draws) and produces the same presses as the
keyboard (left, right, jump, kick). It does not touch the simulation and has
no physical advantages: the difficulty comes from human things (reaction
time, mistakes, jump aim and the decision to defend).

It does not depend on pygame or processes: it could also be an online rival.
"""
import dataclasses
import math
import random

from fdc import config
from fdc import protocol

# --- how it decides (distances are in head radii "R", so they hold the same
#     if the player is grown or shrunk)
# The reaction time varies between 80 % and 125 % of the level's one.
REACTION_JITTER = (0.8, 1.25)
# s: to place itself, it looks where the ball will be after this time.
BALL_LOOKAHEAD = 0.15
# px: the ball got between it and its goal if it passed it by more than this.
BEHIND_MARGIN = 8
# px/s: ball going to its goal faster than this = danger.
DANGER_SPEED = 150
BACK_GAP = 1.9          # R: to go back it stands this far behind the ball
# To cover the goal it stands at this share of the ball-goal path...
COVER_SHARE = 0.35
COVER_GAP = 0.6         # R: ...and at least this far in front of the line
# R: to attack it stands this far behind the ball (it pushes it).
ATTACK_GAP = 0.7
STOP_TOLERANCE = 0.2    # R: closer than this to its target, it stays still
# R: ball lower than the head by this much = "low ball".
LOW_BALL_MARGIN = 0.3
# R: going back with a low ball this close, it jumps over it.
HOP_DISTANCE = 2.6
# R: highest point above the head it tries to reach jumping.
JUMP_REACH = 4.2
JUMP_TIMING_SLACK = 0.05  # s of margin to jump right when the ball arrives
# R: ball falling this close (in x) = it tries a header.
HEADER_RANGE = 1.2
KICK_RANGE_X = 0.25     # R: extra horizontal margin to decide to kick
KICK_RANGE_Y = 0.5      # R: extra vertical margin to decide to kick

# One level per tournament stage (0 = first stage ... 5 = final).
LEVELS = (
    {"name": "Muy fácil", "reaction": 0.34, "error": 0.20, "jump": 0.30,
     "kick": 0.55, "defend": 0.25},
    {"name": "Fácil", "reaction": 0.27, "error": 0.15, "jump": 0.45,
     "kick": 0.70, "defend": 0.40},
    {"name": "Normal", "reaction": 0.21, "error": 0.11, "jump": 0.60,
     "kick": 0.80, "defend": 0.55},
    {"name": "Difícil", "reaction": 0.16, "error": 0.07, "jump": 0.75,
     "kick": 0.90, "defend": 0.70},
    {"name": "Muy difícil", "reaction": 0.12, "error": 0.04, "jump": 0.88,
     "kick": 0.97, "defend": 0.85},
    {"name": "Leyenda", "reaction": 0.09, "error": 0.02, "jump": 0.96,
     "kick": 1.00, "defend": 0.95},
)


@dataclasses.dataclass
class _Situation:
  """What the bot sees in one decision."""
  me: dict
  rival: dict
  ball: dict
  direction: int      # 1 if it attacks to the right, -1 to the left
  scale: float
  radius: float       # head radius R of the bot, already scaled
  mouth: float        # x of its own goal line
  head_top: float     # y of the top of its head


class Bot:
  """Produces keyboard-like controls from the latest match state."""

  def __init__(self, slot, level, seed=None):
    self.slot = slot                       # 0 = left, 1 = right
    self.cfg = LEVELS[max(0, min(level, len(LEVELS) - 1))]
    self.rng = random.Random(seed)
    self.timer = 0.0
    self.move = 0
    self.want_jump = False
    self.want_kick = False
    self.jumps = 0             # cumulative counters, like the keyboard
    self.kicks = 0
    self._prev_jump = False
    self._prev_kick = False

  def controls(self, st, dt):
    """[left, right, jumps, kicks] from the latest state."""
    if (st is None or st.get("phase") != protocol.PHASE_PLAYING
            or st.get("paused")):
      self.move, self.want_jump, self.want_kick = 0, False, False
    else:
      self._tick(st, dt)
    if self.want_jump and not self._prev_jump:
      self.jumps += 1
    if self.want_kick and not self._prev_kick:
      self.kicks += 1
    self._prev_jump, self._prev_kick = self.want_jump, self.want_kick
    return [self.move < 0, self.move > 0, self.jumps, self.kicks]

  def _tick(self, st, dt):
    """Decides once per "reaction time" (with some variation)."""
    self.timer -= dt
    if self.timer <= 0:
      self.timer = (self.cfg["reaction"]
                    * self.rng.uniform(*REACTION_JITTER))
      self._think(st)

  # ------------------------------------------------------------- decision
  def _think(self, st):
    sit = self._situation(st)
    behind = (sit.direction * (sit.me["x"] - sit.ball["x"])
              > BEHIND_MARGIN)      # the ball got between me and my goal
    self.move = self._move(sit, behind)
    self.want_jump = self._jump(sit, behind)
    self.want_kick = self._kick(sit)
    if self.rng.random() < self.cfg["error"]:       # human mistakes
      self.move = self.rng.choice((-1, 0, 1))
      self.want_jump = False

  def _situation(self, st):
    me = st["players"][self.slot]
    scale = me["scale"]
    mouth = (config.Arena.GOAL_DEPTH if self.slot == 0
             else config.Arena.WIDTH - config.Arena.GOAL_DEPTH)
    return _Situation(
        me=me, rival=st["players"][1 - self.slot], ball=st["ball"],
        direction=1 if self.slot == 0 else -1, scale=scale,
        radius=config.PlayerSpec.HEAD_RADIUS * scale, mouth=mouth,
        head_top=me["y"] - config.PlayerSpec.HEIGHT * scale)

  # ---------------------------------------------------------- where to go
  def _move(self, sit, behind):
    """-1, 0 or 1: the direction to walk to the chosen spot."""
    dx = self._target(sit, behind) - sit.me["x"]
    if abs(dx) < sit.radius * STOP_TOLERANCE:
      return 0
    return 1 if dx > 0 else -1

  def _target(self, sit, behind):
    d, ball, radius = sit.direction, sit.ball, sit.radius
    if behind:                         # go back behind the ball
      return ball["x"] - d * radius * BACK_GAP
    if _danger(sit) and self.rng.random() < self.cfg["defend"]:
      return sit.mouth + d * (abs(ball["x"] - sit.mouth) * COVER_SHARE
                              + radius * COVER_GAP)   # cover the goal
    ahead_x = ball["x"] + ball["vx"] * BALL_LOOKAHEAD
    return ahead_x - d * radius * ATTACK_GAP   # push to the rival goal

  # ---------------------------------------------------------------- jumps
  def _jump(self, sit, behind):
    """Computes when the ball arrives (with the aim of the level)."""
    me, ball = sit.me, sit.ball
    can_jump = me["ground"] and not me["frozen"]
    if behind and can_jump and _low_ball_near(sit):
      # Going back with the ball close and low: jump over it instead
      # of pushing it into the own goal.
      return self.rng.random() < 0.5 + self.cfg["defend"] * 0.5
    if not can_jump:
      return False
    coming = (abs(ball["vx"]) > 1
              and (ball["x"] - me["x"]) * ball["vx"] < 0)
    if coming:
      return self._jump_to_meet(sit)
    return self._header(sit)

  def _jump_to_meet(self, sit):
    """Jumps if the ball will pass within reach right now."""
    me, ball = sit.me, sit.ball
    tt = abs(ball["x"] - me["x"]) / abs(ball["vx"])
    yy = (ball["y"] + ball["vy"] * tt
          + 0.5 * config.BallSpec.GRAVITY * tt * tt)
    need = sit.head_top - yy + ball["r"] * 0.5
    if not (0 < need < sit.radius * JUMP_REACH
            and yy < config.Arena.FLOOR_Y - ball["r"]):
      return False
    return (tt <= _rise_time(need) + JUMP_TIMING_SLACK
            and self.rng.random() < self.cfg["jump"])

  def _header(self, sit):
    """Ball falling right above: try a header."""
    me, ball = sit.me, sit.ball
    return (abs(ball["x"] - me["x"]) < sit.radius * HEADER_RANGE
            and (sit.head_top - sit.radius * JUMP_REACH < ball["y"]
                 < sit.head_top)
            and ball["vy"] > 0 and self.rng.random() < self.cfg["jump"])

  # ---------------------------------------------------------------- kicks
  def _kick(self, sit):
    """Only if it faces the rival goal and has the ball in front."""
    me, ball, d, scale = sit.me, sit.ball, sit.direction, sit.scale
    foot_x = me["x"] + d * config.PlayerSpec.KICK_REACH_X * scale
    foot_y = me["y"] - config.PlayerSpec.KICK_REACH_Y * scale
    reach = config.PlayerSpec.KICK_RADIUS * scale + ball["r"]
    return (me["facing"] == d and not me["no_kick"]
            and abs(ball["x"] - foot_x) < reach + sit.radius * KICK_RANGE_X
            and abs(ball["y"] - foot_y) < reach + sit.radius * KICK_RANGE_Y
            and self.rng.random() < self.cfg["kick"])


def _danger(sit):
  """The ball comes to my goal, or it is on my half closer to the rival."""
  d, ball, me, rival = sit.direction, sit.ball, sit.me, sit.rival
  if ball["vx"] * d < -DANGER_SPEED:
    return True
  my_half = d * (ball["x"] - config.Arena.WIDTH / 2) < 0
  return my_half and (abs(rival["x"] - ball["x"])
                      < abs(me["x"] - ball["x"]))


def _low_ball_near(sit):
  """The ball is low (below the head) and close to the bot."""
  low = sit.ball["y"] > sit.head_top + sit.radius * LOW_BALL_MARGIN
  near = abs(sit.ball["x"] - sit.me["x"]) < sit.radius * HOP_DISTANCE
  return low and near


def _rise_time(height):
  """Seconds a jump takes to rise `height` px (or to its top)."""
  speed, gravity = config.PlayerSpec.JUMP_SPEED, config.PlayerSpec.GRAVITY
  disc = speed * speed - 2 * gravity * height
  if disc > 0:
    return (speed - math.sqrt(disc)) / gravity
  return speed / gravity
