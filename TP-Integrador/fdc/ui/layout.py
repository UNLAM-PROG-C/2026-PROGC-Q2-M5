"""Common interface measures (px in the 1280 x 720 logical resolution).

Each screen defines its own positions at the top of its class; here are
the ones repeated everywhere: screen centre, font sizes, veils, blink
rhythms and the standard shape of buttons and panels.
"""
from fdc import config

# --- screen
SCREEN_W = config.LOGICAL_WIDTH    # px: logical screen width
SCREEN_H = config.LOGICAL_HEIGHT   # px: logical screen height
CENTER_X = SCREEN_W // 2           # px: horizontal centre
CENTER_Y = SCREEN_H // 2           # px: vertical centre
SCREEN_MARGIN = 16                 # px: general margin to the screen edges

# --- font sizes (the pixel art font is drawn at scale = size / 8)
FONT_SMALL = 16                    # hints, footers, tables
FONT_TEXT = 24                     # buttons and normal texts
FONT_LARGE = 32                    # big notices and box titles
FONT_TITLE_S = 40                  # titles of signs
FONT_TITLE = 48                    # screen titles
FONT_TITLE_L = 56                  # main titles
FONT_TITLE_XL = 64                 # menu titles
FONT_BANNER = 72                   # huge signs ("VS", golden goal)
FONT_GOAL = 80                     # "¡GOOOL!"
FONT_COUNTDOWN = 96                # countdown numbers
FONT_GO = 104                      # "¡YA!"
FONT_GIANT = 120                   # question mark of the missing rival

# --- light veils over the stadium (opacity from 0 to 255)
VEIL_MENU = 70                     # main menu: almost the whole stadium shows
VEIL_SUBMENU = 90                  # submenus
VEIL_RESULT = 100                  # result screens
VEIL_PROFILE = 110                 # name screen
VEIL_OVERLAY = 120                 # signs over the match and choice screens
VEIL_ONLINE = 130                  # online entry
VEIL_LIST = 140                    # lists and forms (rooms, controls)
VEIL_BOOT = 150                    # boot and powers legend
VEIL_ERROR = 170                   # error screens

# --- animation
BLINK_HZ = 3                       # blinks per second of the ► button cursor
BOB_HZ = 4                         # hops per second of the selected button
BOB_PX = 2                         # px the selected button rises on each hop
CARET_HZ = 2.5                     # blinks per second of the text caret
IDLE_BOB_HZ = 1.6                  # sway of idle characters (times per second)
CELEBRATE_KICK_HZ = 14             # kicks per second of a celebrating player
CELEBRATE_HOP_HZ = 7               # hops per second of a celebrating player
CELEBRATE_KICK_ANGLE = 50          # degrees the boot sweeps when celebrating
CELEBRATE_HOP_PX = 6               # px of the celebration hops

# --- standard buttons, panels and boxes
BUTTON_H = 56                      # px: height of a menu button
BUTTON_SMALL_H = 44                # px: height of small buttons (◄ ►, Volver)
ARROW_BUTTON_W = 52                # px: width of the ◄ and ► buttons
CURSOR_GAP = 22                    # px between the ► cursor and the button
SHADOW_OFFSET = 6                  # px: hard shadow of cards and boards
FRAME_LINE = 4                     # px: dark frame of cards and boards
TEXT_LINE_H = 22                   # px between lines of small text
TEXT_LINE_H_BIG = 30               # px between lines of normal text
