"""Colour palette: light and classic, retro game in a stadium by day."""

INK = (43, 45, 66)            # dark outlines and texts
INK_SOFT = (84, 90, 120)      # secondary texts, hints
WHITE = (255, 255, 255)       # pure white (texts on dark, highlights)
CREAM = (255, 248, 231)       # panels
CREAM_DARK = (236, 222, 190)  # shaded panels, disabled buttons
PAPER = (250, 244, 226)       # paper (card backgrounds)

SKY_TOP = (150, 205, 238)     # sky at the top
SKY_BOTTOM = (214, 238, 250)  # sky near the horizon
CLOUD = (250, 252, 255)       # clouds
CLOUD_SHADE = (222, 236, 246)  # shade of the clouds

STRUCT = (226, 231, 236)      # stadium structure
STRUCT_SHADE = (190, 199, 209)  # stadium structure in half shade
# Stadium structure in shade (and the scoreboard frame).
STRUCT_DARK = (142, 153, 166)
ROOF = (238, 241, 244)        # roof of the stands

SEAT_RED = (226, 150, 150)    # red seats
SEAT_RED_DARK = (201, 120, 124)  # red seats in shade
SEAT_BLUE = (160, 190, 226)   # light blue seats

GRASS_A = (142, 206, 96)      # grass: light stripe
GRASS_B = (128, 194, 84)      # grass: dark stripe
GRASS_DARK = (104, 172, 70)   # shaded grass (edges, tufts)
GRASS_FRONT = (118, 184, 76)  # grass at the front of the pitch
LINE = (246, 252, 240)        # chalk lines

GOLD = (255, 210, 63)         # gold: titles, selected button
GOLD_DARK = (222, 160, 30)    # gold in shade
ORANGE = (245, 140, 50)       # orange (warnings)
RED = (228, 87, 70)           # red: errors, alerts
GREEN = (80, 180, 100)        # green: ready, connected
BLUE = (70, 130, 220)         # blue: rival in the room, data
PURPLE = (150, 100, 210)      # purple
SOFT_RED = (255, 120, 120)    # soft red: something was rejected

LED_BG = (34, 36, 44)         # background of the LED scoreboard
LED_OFF = (58, 54, 50)        # LED dot off
LED_ON = (255, 196, 70)       # LED dot on
LED_ON_2 = (255, 120, 80)     # alert LED dot (last seconds, golden goal)

SHADOW = (0, 0, 0)            # shadows
ERROR_PANEL = (255, 236, 232)  # pink background of error signs

RGB_CHANNELS = 3              # channels of a colour without alpha (r, g, b)
MAX_CHANNEL = 255             # top value of a colour channel (r, g, b or a)
OPAQUE = MAX_CHANNEL          # alpha of a fully opaque pixel
