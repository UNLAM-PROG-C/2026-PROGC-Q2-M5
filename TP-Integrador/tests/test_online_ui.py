"""Real online interface (no window) against a real server.

The person drives the desktop application; the rival is a test client
connected to the same server.
"""
import os
import unittest

try:
  import websockets  # pylint: disable=unused-import
except ImportError:  # the local game does not need it: skipped without it
  raise unittest.SkipTest(
      "websockets is missing (pip install -r requirements-online.txt)"
  ) from None

import driver  # sets the dummy SDL before pygame is imported
import online_helpers
import pygame

from fdc import protocol
from fdc.online import wire
from fdc.ui import online_screens
from fdc.ui import screens

SHOTS = os.environ.get("FDC_SHOTS")
MATCH_LENGTH = 30.0     # s of the online match
BOOT_WAIT = 25          # s until the menu
STEP_WAIT = 5           # s for most conditions
LONG_WAIT = 10          # s for the room list, match start and result
PLAY_WAIT = 15          # s until the match is in play
MIN_MOVE = 40           # px a held key must move the player
EXIT_FRAMES = 30        # frames after leaving the online mode
# Keys from the main menu to the online entry.
ONLINE_KEYS = (pygame.K_RETURN, pygame.K_s, pygame.K_RETURN, pygame.K_s,
               pygame.K_RETURN)


class OnlineUITest(unittest.TestCase):
  def setUp(self):
    # Stopped after tearDown (cleanups run last).
    self.srv = self.enterContext(online_helpers.ServerThread(
        duration=MATCH_LENGTH, seed=3))
    self.app = driver.make_app(test_mode=False, seed=None,
                               server_url=self.srv.url, profile_name="Ale")
    self.d = driver.Driver(self.app, SHOTS)
    self.rival = None

  def tearDown(self):
    if self.rival is not None:
      self.rival.close()
    self.app.running = False
    self.app.shutdown()

  def until_screen(self, cls, timeout, what):
    self.d.until(lambda: isinstance(self.d.screen(), cls), timeout, what)

  def test_full_online_flow(self):
    d = self.d
    self.until_screen(screens.MenuScreen, BOOT_WAIT, "menu")
    for key in ONLINE_KEYS:
      d.tap(key)                       # play -> multiplayer -> online
    # It goes in with the profile name (it is not asked again).
    self.until_screen(online_screens.RoomsScreen, LONG_WAIT, "room list")
    self.assertEqual(self.app.net.username, "Ale")
    self.assertTrue(self.app.net.display.startswith("Ale #"))
    self.check_create_screen()
    self.check_private_room()
    ms = self.check_room_and_start()
    self.check_move_and_pause(ms)
    self.check_forfeit_and_leave(ms)

  def check_create_screen(self):
    """Opens the create room form and goes back to the list."""
    self.d.tap(pygame.K_c)
    self.assertIsInstance(self.d.screen(), online_screens.CreateRoomScreen)
    self.d.tap(pygame.K_ESCAPE)
    self.assertIsInstance(self.d.screen(), online_screens.RoomsScreen)

  def check_private_room(self):
    d = self.d
    # The same name as mine: the tag tells us apart.
    self.rival = online_helpers.Client(self.srv.url, "Ale")
    d.each_frame = self.rival.pump
    self.rival.send({"type": wire.CREATE_ROOM, "name": "Picadito",
                     "password": "1234"})
    d.until(lambda: self.app.net.rooms, STEP_WAIT, "room in the list")
    d.shot("online_2_rooms")
    d.tap(pygame.K_RETURN)          # private room: asks the password
    self.assertIsNotNone(d.screen().prompt)
    d.post(pygame.TEXTINPUT, text="1234")
    d.tap(pygame.K_RETURN)
    self.until_screen(online_screens.RoomScreen, STEP_WAIT, "room")

  def check_room_and_start(self):
    d = self.d
    self.rival.send({"type": wire.CHOOSE_CHARACTER, "character": "pele"})
    self.rival.send({"type": wire.READY})
    d.until(lambda: any(m["ready"] for m in self.app.net.room["members"]),
            STEP_WAIT, "rival ready")
    d.tap(pygame.K_d)                    # change of character
    d.frames(3)
    d.shot("online_3_room")
    d.tap(pygame.K_SPACE)                # ready!
    return self.match_screen()

  def match_screen(self):
    d = self.d
    self.until_screen(online_screens.OnlineMatchScreen, LONG_WAIT, "match")
    ms = d.screen()
    self.assertEqual(ms.names[ms.you], self.app.net.display)
    self.assertNotEqual(ms.names[0], ms.names[1])
    d.until(lambda: ms.state is not None
            and ms.state["phase"] == protocol.PHASE_PLAYING,
            PLAY_WAIT, "play")
    return ms

  def check_move_and_pause(self, ms):
    d = self.d
    # I move: the server simulation decides the position.
    me = ms.you
    x0 = ms.state["players"][me]["x"]
    key = pygame.K_RIGHT if me == 0 else pygame.K_LEFT
    d.down(key)
    d.seconds(0.5)
    d.up(key)
    d.seconds(0.2)
    self.assertGreater(abs(ms.state["players"][me]["x"] - x0), MIN_MOVE)
    self.check_requested_pause(ms)

  def check_requested_pause(self, ms):
    d = self.d
    # Requested pause: shown below the scoreboard, the play goes on.
    d.tap(pygame.K_ESCAPE)
    note = f"{self.app.net.display} pidió la pausa"
    d.until(lambda: ms.renderer.center_note == note, STEP_WAIT,
            "pause notice")
    self.assertFalse(ms.state["paused"])
    d.shot("online_4_match")

  def check_forfeit_and_leave(self, ms):
    d = self.d
    # The rival leaves: I win by forfeit.
    self.rival.send({"type": wire.ABANDON})
    self.until_screen(online_screens.OnlineResultScreen, LONG_WAIT,
                      "result")
    res = d.screen()
    self.assertEqual((res.over["reason"], res.winner),
                     (wire.END_FORFEIT, ms.you))
    d.frames(5)
    d.shot("online_5_result")
    self.check_leave()

  def check_leave(self):
    d = self.d
    back = screens.BackButton.RECT.center
    d.post(pygame.MOUSEBUTTONDOWN, pos=back, button=1)
    self.until_screen(online_screens.RoomsScreen, STEP_WAIT,
                      "back to the list")
    # Back from the list leaves the online mode (it does not enter
    # again by itself).
    d.post(pygame.MOUSEBUTTONDOWN, pos=back, button=1)
    d.frames(EXIT_FRAMES)
    self.assertIsInstance(d.screen(), screens.MultiplayerMenuScreen)
    self.assertIsNone(self.app.net)


if __name__ == "__main__":
  unittest.main()
