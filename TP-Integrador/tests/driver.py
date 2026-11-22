"""Driver of the interface without a visible window (SDL "dummy").

The UI smoke tests use it: it starts the real application (with its real
simulation process) and drives it with synthetic keyboard events.
"""
import os
import tempfile
import time
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# pylint: disable=wrong-import-position
import pygame  # noqa: E402

import helpers  # noqa: E402,F401  pylint: disable=unused-import
from fdc import profile  # noqa: E402
from fdc.ui import app as game  # noqa: E402

# No server unless the test starts one (never a real one).
NO_SERVER = "ws://127.0.0.1:1/ws"
DEFAULT_TIMEOUT = 10.0      # s to wait for a condition


class _TestApp(game.App):
  """Keep SDL dummy independent of scaled renderer support."""

  def _display_flags(self):
    if pygame.display.get_driver() == "dummy":
      return 0
    return super()._display_flags()


def profile_file(name="Prueba", player_id=None):
  """Temporary profile for the tests (the user one is never touched).
    With name=None the file stays empty: the game asks for the name."""
  folder = tempfile.mkdtemp(prefix="fdc-profile-")
  path = os.path.join(folder, "profile.json")
  if name:
    profile.save(profile.Profile(name, player_id), path)
  return path


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def make_app(test_mode=True, seed=5, duration=None, server_url=None,
             profile_name="Prueba", quality_mode="sin-efectos"):
  """The real App with test options.

    The smoke tests play whole matches inside a time limit, so they run in
    the plain render; the rendering tests cover FULL separately.
    """
  opts = types.SimpleNamespace(
      test_mode=test_mode, seed=seed, no_audio=False, fullscreen=False,
      debug_panel=True, duration=duration,
      server_url=server_url or NO_SERVER,
      profile_path=profile_file(profile_name),
      quality_mode=quality_mode)
  return _TestApp(opts)


def _key_event(etype, key):
  return pygame.event.Event(etype, key=key, mod=0, unicode="", scancode=0)


class Driver:
  """Runs frames of the app and posts synthetic events."""

  def __init__(self, app, shots_dir=None):
    self.app = app
    self.shots_dir = shots_dir
    self.each_frame = None    # e.g. read the messages of a test rival

  def frames(self, n=1):
    for _ in range(n):
      self.app.frame()

  def until(self, cond, timeout=DEFAULT_TIMEOUT, what="condition"):
    """Runs frames until cond() is True (fails after timeout s)."""
    t0 = time.monotonic()
    while not cond():
      self.app.frame()
      if self.each_frame:
        self.each_frame()
      if time.monotonic() - t0 > timeout:
        raise AssertionError(f"timed out waiting for {what}")

  def seconds(self, s):
    t0 = time.monotonic()
    while time.monotonic() - t0 < s:
      self.app.frame()

  def down(self, key):
    pygame.event.post(_key_event(pygame.KEYDOWN, key))
    self.app.frame()

  def up(self, key):
    pygame.event.post(_key_event(pygame.KEYUP, key))
    self.app.frame()

  def tap(self, key, frames_after=2):
    self.down(key)
    self.up(key)
    self.frames(frames_after)

  def post(self, etype, **kw):
    pygame.event.post(pygame.event.Event(etype, **kw))
    self.app.frame()

  def screen(self):
    return self.app.current

  def shot(self, name):
    if self.shots_dir:
      pygame.image.save(self.app.screen,
                        os.path.join(self.shots_dir, name + ".png"))
