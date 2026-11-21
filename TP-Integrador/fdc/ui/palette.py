"""Colour palette: light and classic, retro game in a stadium by day."""

INK = (43, 45, 66)            # dark outlines and texts
INK_SOFT = (84, 90, 120)      # secondary texts, hints
HUD_BACKGROUND = (35, 37, 47) # #23252F: shortcut chips
HUD_TEXT = (246, 231, 193)    # #F6E7C1: text on the HUD chips
WHITE = (255, 255, 255)       # pure white (texts on dark, highlights)
CREAM = (255, 248, 231)       # panels
CREAM_DARK = (236, 222, 190)  # shaded panels, disabled buttons
PAPER = (250, 244, 226)       # paper (card backgrounds)

SKY_TOP = (142, 201, 242)     # #8EC9F2: sky at the top (never burnt white)
SKY_BOTTOM = (220, 235, 247)  # #DCEBF7: sky near the horizon
CLOUD = (250, 252, 255)       # clouds
CLOUD_SHADE = (222, 236, 246)  # shade of the clouds

STRUCT = (226, 231, 236)      # stadium structure
STRUCT_SHADE = (190, 199, 209)  # stadium structure in half shade
# Stadium structure in shade (and the scoreboard frame).
STRUCT_DARK = (142, 153, 166)
ROOF = (238, 241, 244)        # roof of the stands

SEAT_DARK = (43, 43, 53)      # #2B2B35: floor of a row of seats
SEAT_DEEP = (28, 28, 38)      # #1C1C26: its dark front
SEAT_EDGE = (84, 84, 95)      # #54545F: lit edge of the step
SEAT_BLUE = (160, 190, 226)   # light blue seats

GRASS_A = (111, 191, 74)      # #6FBF4A: grass, light stripe
GRASS_B = (92, 170, 60)       # #5CAA3C: grass, dark stripe
GRASS_DARK = (78, 146, 50)    # shaded grass (edges, tufts)
GRASS_FRONT = (86, 160, 56)   # grass at the front of the pitch
LINE = (242, 245, 240)        # #F2F5F0: chalk lines

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
