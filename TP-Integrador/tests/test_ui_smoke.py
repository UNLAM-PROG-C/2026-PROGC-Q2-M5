"""Smoke test of the real interface, without a visible window (SDL "dummy").

It goes through: boot -> menu -> selection -> match (controls, test powers,
confirmed pause, focus loss, restart) -> result -> rematch -> menu ->
coordinated shutdown. It uses the real simulation process.
"""
import unittest

import driver  # sets the dummy SDL before pygame is imported
import pygame

from fdc import config
from fdc import profile
from fdc import protocol
from fdc import tournament
from fdc.ui import match_screens
from fdc.ui import online_screens
from fdc.ui import profile_screen
from fdc.ui import screens
from fdc.ui import tournament_screens

BOOT_WAIT = 20          # s until the menu
PLAY_WAIT = 8           # s until the match is in play
STEP_WAIT = 5           # s for the other conditions
PAUSE_WAIT = 3          # s for a pause to be confirmed
RESULT_WAIT = 25        # s until the end of a short match
TOURNAMENT_END = 60     # s until the end of a golden goal match
MIN_MOVE = 40           # px a held key must move a player
TWO_KEYS_MOVE = 60      # px after holding both key sets
LAST_PLACE = 7          # place of who loses the first match
ERASE = 3               # backspaces to delete the old name


def playing(ms):
    return (ms.state is not None
            and ms.state["phase"] == protocol.PHASE_PLAYING)


class UISmokeTest(unittest.TestCase):
    def start(self, **kw):
        self.closed = False
        self.app = driver.make_app(**kw)
        self.d = driver.Driver(self.app)
        self.d.until(lambda: isinstance(self.d.screen(), screens.MenuScreen),
                     BOOT_WAIT, "menu")

    def tearDown(self):
        if not self.closed:
            self.app.shutdown()

    def close(self):
        """Shuts the app down (tearDown does not do it again)."""
        self.closed = True
        self.app.shutdown()

    def taps(self, *keys):
        for key in keys:
            self.d.tap(key)

    def is_screen(self, cls):
        self.assertIsInstance(self.d.screen(), cls)

    def wait_pause(self, ms, what="pause"):
        self.d.until(lambda: ms.pause_state == "paused", PAUSE_WAIT, what)

    def test_full_flow(self):
        self.start(test_mode=True, seed=5, duration=8)
        self.check_menus()
        ms = self.check_same_characters()
        self.check_walk_and_jump(ms)
        self.check_test_power_and_pause(ms)
        self.check_focus_and_restart(ms)
        self.check_result_and_menu()
        self.d.post(pygame.QUIT)
        self.assertFalse(self.app.running)
        self.close()
        report = self.app.link.shutdown_report
        self.assertEqual(report["method"], "orderly")
        self.assertTrue(report["bye"])

    def check_menus(self):
        self.taps(pygame.K_s, pygame.K_RETURN)
        self.is_screen(screens.ControlsScreen)
        self.taps(pygame.K_ESCAPE, pygame.K_s, pygame.K_s, pygame.K_RETURN)
        self.is_screen(screens.LegendScreen)
        self.check_submenus()

    def check_submenus(self):
        self.taps(pygame.K_ESCAPE, pygame.K_RETURN)          # play
        self.is_screen(screens.PlayMenuScreen)
        self.taps(pygame.K_s, pygame.K_RETURN)                # multiplayer
        self.is_screen(screens.MultiplayerMenuScreen)
        self.taps(pygame.K_s, pygame.K_RETURN)                # online
        self.is_screen(online_screens.OnlineHomeScreen)
        self.taps(pygame.K_ESCAPE)                # back without connecting
        self.is_screen(screens.MultiplayerMenuScreen)
        self.assertIsNone(self.app.net)
        self.taps(pygame.K_RETURN)                # local: the usual game
        self.is_screen(match_screens.SelectScreen)

    def check_same_characters(self):
        """Both choose the SAME character (allowed)."""
        d = self.d
        d.screen().cursor = [0, 0]
        self.taps(pygame.K_SPACE, pygame.K_p)
        d.until(lambda: isinstance(d.screen(), match_screens.MatchScreen),
                STEP_WAIT, "match")
        ms = d.screen()
        self.assertEqual(ms.chars, ["messi", "messi"])
        d.until(lambda: playing(ms), PLAY_WAIT, "play")
        return ms

    def check_walk_and_jump(self, ms):
        d = self.d
        # P1 walks right: the simulation decides the position.
        x0 = ms.state["players"][0]["x"]
        d.down(pygame.K_d)
        d.seconds(0.4)
        d.up(pygame.K_d)
        d.seconds(0.1)
        self.assertGreater(ms.state["players"][0]["x"], x0 + MIN_MOVE)
        # A short jump (one single press) is not lost.
        d.tap(pygame.K_w, 0)
        d.until(lambda: not ms.state["players"][0]["ground"], 1, "jump")

    def check_test_power_and_pause(self, ms):
        d = self.d
        ms.test_sel = config.POWER_IDS.index("shrink")       # power to P2
        d.tap(pygame.K_F9)
        d.until(lambda: any(e["target"] == "p1" for e in ms.state["effects"]),
                2, "effect")
        self.check_pause(ms)

    def check_pause(self, ms):
        d = self.d
        d.down(pygame.K_ESCAPE)
        # The pause shows only with the ACK (it may come in the same frame).
        self.assertIn(ms.pause_state, ("requested", "paused"))
        d.up(pygame.K_ESCAPE)
        self.wait_pause(ms, "pause confirmation")
        c1 = ms.state["clock"]
        d.seconds(0.6)
        self.assertEqual(ms.state["clock"], c1)   # the clock does not run
        d.tap(pygame.K_ESCAPE)
        d.until(lambda: ms.pause_state is None, PAUSE_WAIT, "resume")

    def check_focus_and_restart(self, ms):
        d = self.d
        # Focus loss: keys are released and a pause is asked.
        d.until(lambda: playing(ms), 4, "play after the countdown")
        d.down(pygame.K_a)
        self.assertTrue(self.app.input.held[0]["left"])
        d.post(pygame.WINDOWFOCUSLOST)
        self.assertFalse(self.app.input.held[0]["left"])
        self.wait_pause(ms, "focus pause")
        self.check_restart(ms)

    def check_restart(self, ms):
        """Restart: a new match, no effects, old states ignored."""
        d = self.d
        old = ms.match_id
        self.taps(pygame.K_s, pygame.K_RETURN)
        d.until(lambda: ms.state is not None and ms.state["match"] != old, 4,
                "restart")
        self.assertEqual(ms.state["effects"], [])
        self.assertEqual(ms.state["score"], [0, 0])

    def check_result_and_menu(self):
        d = self.d
        # Short match until the end.
        d.until(lambda: isinstance(d.screen(), match_screens.ResultScreen),
                RESULT_WAIT, "result")
        d.tap(pygame.K_RETURN)                              # rematch
        self.is_screen(match_screens.MatchScreen)
        self.assertEqual(d.screen().chars, ["messi", "messi"])
        d.until(lambda: d.screen().state is not None, STEP_WAIT, "rematch")
        d.tap(pygame.K_ESCAPE)
        self.wait_pause(d.screen())
        self.taps(pygame.K_s, pygame.K_s, pygame.K_RETURN)
        self.is_screen(screens.MenuScreen)
        self.assertIsNone(self.app.link.error)

    def test_tournament_flow(self):
        self.start(test_mode=True, seed=3, duration=3)
        t = self.pick_character()
        self.d.tap(pygame.K_RETURN)                        # play stage 1
        self.check_both_key_sets(self.d.screen(), t)
        self.check_first_result()
        self.check_abandon()
        self.close()
        self.assertEqual(self.app.link.shutdown_report["method"], "orderly")

    def pick_character(self):
        """Play > tournament, choose one: the others are the rivals."""
        self.taps(pygame.K_RETURN, pygame.K_RETURN)        # play, tournament
        self.is_screen(tournament_screens.PickScreen)
        self.taps(pygame.K_RIGHT, pygame.K_SPACE)          # choose, confirm
        self.is_screen(tournament_screens.HubScreen)
        t = self.app.tournament
        self.assertEqual(sorted(t.rivals + [t.player]),
                         sorted(config.CHARACTER_IDS))
        return t

    def check_both_key_sets(self, ms, t):
        """The person drives the right side with either key set."""
        d = self.d
        self.assertIsInstance(ms, tournament_screens.TournamentMatchScreen)
        self.assertEqual(ms.chars[tournament.HUMAN_SLOT], t.player)
        d.until(lambda: playing(ms), PLAY_WAIT, "play")
        x0 = ms.state["players"][tournament.HUMAN_SLOT]["x"]
        for key in (pygame.K_LEFT, pygame.K_a):
            d.down(key)
            d.seconds(0.3)
            d.up(key)
        d.seconds(0.1)
        self.assertLess(ms.state["players"][tournament.HUMAN_SLOT]["x"],
                        x0 - TWO_KEYS_MOVE)

    def check_first_result(self):
        self.d.until(lambda: isinstance(
            self.d.screen(), tournament_screens.TournamentResultScreen),
                     TOURNAMENT_END, "end of the match")
        rs = self.d.screen()
        self.assertEqual(len(rs.t_.results), 1)
        _, _, mine, theirs = rs.t_.results[0]
        self.assertNotEqual(mine, theirs)          # golden goal: no draws
        if rs.won:
            self.check_progress_kept()
            return
        # Eliminated: it must start again.
        self.assertIsNone(self.app.tournament)
        self.assertEqual(rs.t_.position, LAST_PLACE)

    def check_progress_kept(self):
        self.assertEqual(self.app.tournament.status, tournament.IN_PROGRESS)
        self.taps(pygame.K_s, pygame.K_RETURN)   # main menu: progress kept
        self.is_screen(screens.MenuScreen)
        # Play > tournament: back to the bracket.
        self.taps(pygame.K_RETURN, pygame.K_RETURN)
        self.is_screen(tournament_screens.HubScreen)
        self.assertEqual(self.app.tournament.stage, 1)

    def check_abandon(self):
        """Quitting from the pause of a match drops the tournament."""
        d = self.d
        if not isinstance(d.screen(), tournament_screens.HubScreen):
            self.taps(pygame.K_RETURN, pygame.K_SPACE)     # start again
        d.tap(pygame.K_RETURN)                             # play the stage
        ms = d.screen()
        d.until(lambda: ms.state is not None, STEP_WAIT, "state")
        d.tap(pygame.K_ESCAPE)
        self.wait_pause(ms)
        self.taps(pygame.K_s, pygame.K_RETURN)             # quit tournament
        self.is_screen(screens.MenuScreen)
        self.assertIsNone(self.app.tournament)

    def click_back(self):
        self.d.post(pygame.MOUSEBUTTONDOWN, pos=screens.BackButton.RECT.center,
                    button=1)
        self.d.frames(2)

    def test_back_buttons(self):
        self.start(test_mode=False, seed=2)
        for screen_cls, expected in (
                (screens.ControlsScreen, screens.MenuScreen),
                (screens.LegendScreen, screens.MenuScreen),
                (match_screens.SelectScreen, screens.MultiplayerMenuScreen),
                (tournament_screens.PickScreen, screens.PlayMenuScreen)):
            self.app.switch(screen_cls(self.app))
            self.d.frames(2)
            self.click_back()
            self.assertIsInstance(self.d.screen(), expected,
                                  screen_cls.__name__)
        self.check_bracket_back()
        self.check_match_back()

    def check_bracket_back(self):
        """Tournament bracket: going back keeps the progress."""
        self.app.switch(tournament_screens.PickScreen(self.app))
        self.d.tap(pygame.K_SPACE)
        self.is_screen(tournament_screens.HubScreen)
        self.click_back()
        self.is_screen(screens.PlayMenuScreen)
        self.assertIsNotNone(self.app.tournament)

    def check_match_back(self):
        """In the match, the corner button asks for the pause."""
        self.app.switch(match_screens.MatchScreen(self.app, ["messi", "pele"]))
        ms = self.d.screen()
        self.d.until(lambda: ms.state is not None, STEP_WAIT, "state")
        self.click_back()
        self.wait_pause(ms, "button pause")

    def test_crash_shows_error_screen_and_retry(self):
        self.start(test_mode=True, seed=1)
        d = self.d
        self.app.switch(match_screens.MatchScreen(self.app, ["pele", "henry"]))
        ms = d.screen()
        d.until(lambda: ms.state is not None, STEP_WAIT, "state")
        d.tap(pygame.K_F12)                       # failure caused in the SIM
        self.check_retry()

    def check_retry(self):
        d = self.d
        d.until(lambda: isinstance(d.screen(), screens.ErrorScreen),
                STEP_WAIT, "error screen")
        self.assertIn("error", self.app.link.error.lower())
        d.tap(pygame.K_RETURN)                    # retry: a new process
        d.until(lambda: isinstance(d.screen(), screens.MenuScreen),
                BOOT_WAIT, "menu after retrying")
        self.assertIsNone(self.app.link.error)
        self.assertTrue(self.app.link.alive)


class ProfileTest(unittest.TestCase):
    def setUp(self):
        # First time: no saved name.
        self.app = driver.make_app(test_mode=False, seed=1, profile_name=None)
        self.d = driver.Driver(self.app)

    def tearDown(self):
        self.app.running = False
        self.app.shutdown()

    def is_screen(self, cls):
        self.assertIsInstance(self.d.screen(), cls)

    def test_name_is_asked_once_at_start(self):
        d = self.d
        d.until(lambda: isinstance(d.screen(), profile_screen.ProfileScreen),
                BOOT_WAIT, "name screen")
        # The first time there is nowhere to go back to.
        self.assertFalse(d.screen().back_button.visible)
        d.tap(pygame.K_RETURN)                          # empty: no change
        self.is_screen(profile_screen.ProfileScreen)
        d.post(pygame.TEXTINPUT, text="Ale")
        d.tap(pygame.K_RETURN)
        self.is_screen(screens.MenuScreen)
        saved = profile.load(self.app.profile_path)     # kept for next time
        self.assertEqual(saved.name, "Ale")
        self.check_rename(saved.player_id)

    def check_rename(self, pid):
        """Changing the name from the menu keeps the same player."""
        d = self.d
        d.tap(pygame.K_n)
        self.is_screen(profile_screen.ProfileScreen)
        self.assertTrue(d.screen().back_button.visible)
        for _ in range(ERASE):
            d.tap(pygame.K_BACKSPACE)
        d.post(pygame.TEXTINPUT, text="Alan")
        d.tap(pygame.K_RETURN)
        self.is_screen(screens.MenuScreen)
        renamed = profile.load(self.app.profile_path)
        self.assertEqual((renamed.name, renamed.player_id), ("Alan", pid))


if __name__ == "__main__":
    unittest.main()
