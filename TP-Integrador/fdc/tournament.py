"""Tournament ("Mundialito"): one player against the other 6 characters.

Rules:
  * one stage per rival (random order); the difficulty grows on each one;
  * the player only moves on by winning; draws go to a golden goal;
  * losing ends the tournament and reports the final place
    (losing stage 1 = 7th place ... losing the final = 2nd place);
  * winning the 6 stages wins the World Cup (1st place).
"""
import random

from fdc import config

# Stage names shown on screen.
STAGES = ("Fecha 1", "Fecha 2", "Fecha 3", "Cuartos de final", "Semifinal",
          "Final")
GROUP_STAGES = 3          # the first three stages are the group stage

IN_PROGRESS = "in_progress"
ELIMINATED = "eliminated"
CHAMPION = "champion"

HUMAN_SLOT = 1            # the person plays on the right
BOT_SLOT = 0              # the computer plays on the left


class Tournament:
    """Progress of one tournament: rivals, results and status."""

    def __init__(self, player, rng=None):
        if player not in config.CHARACTER_IDS:
            raise ValueError(f"unknown character: {player}")
        rng = rng or random.Random()
        self.player = player
        self.rivals = [c for c in config.CHARACTER_IDS if c != player]
        rng.shuffle(self.rivals)
        self.stage = 0
        # (stage, rival, my goals, rival goals)
        self.results = []
        self.status = IN_PROGRESS

    @property
    def finished(self):
        return self.status != IN_PROGRESS

    @property
    def stage_name(self):
        return STAGES[min(self.stage, len(STAGES) - 1)]

    @property
    def rival(self):
        return self.rivals[min(self.stage, len(self.rivals) - 1)]

    @property
    def level(self):
        """Rival difficulty: grows with each stage (0..5)."""
        return self.stage

    @property
    def position(self):
        """Final place (None while the tournament goes on)."""
        if self.status == CHAMPION:
            return 1
        if self.status == ELIMINATED:
            return len(STAGES) + 1 - self.stage
        return None

    def record(self, my_goals, rival_goals):
        """Records the result of the current match. Returns True if won."""
        if self.finished:
            raise RuntimeError("the tournament is already over")
        won = my_goals > rival_goals
        self.results.append((self.stage_name, self.rival, my_goals,
                             rival_goals))
        if won:
            self.stage += 1
            if self.stage == len(STAGES):
                self.status = CHAMPION
        else:
            self.status = ELIMINATED
        return won


def ordinal(n):
    """Spanish ordinal shown on screen (1 -> "1.º")."""
    return f"{n}.º"
