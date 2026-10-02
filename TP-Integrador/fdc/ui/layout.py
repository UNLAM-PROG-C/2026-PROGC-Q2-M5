"""Medidas comunes de la interfaz (px en la resolución lógica de 1280 x 720).

Cada pantalla define al principio de su clase sus propias posiciones; acá van
las que se repiten en todas: centro de la pantalla, tamaños de letra, velos,
ritmos de parpadeo y la forma estándar de los botones y paneles.
"""
from ..config import LOGICAL_HEIGHT, LOGICAL_WIDTH

# --- pantalla
SCREEN_W = LOGICAL_WIDTH           # px: ancho de la pantalla lógica
SCREEN_H = LOGICAL_HEIGHT          # px: alto de la pantalla lógica
CENTER_X = SCREEN_W // 2           # px: centro horizontal
CENTER_Y = SCREEN_H // 2           # px: centro vertical
SCREEN_MARGIN = 16                 # px: margen general contra los bordes de la pantalla

# --- tamaños de letra (la fuente pixel art se dibuja a escala = tamaño / 8)
FONT_SMALL = 16                    # ayudas, pies de página, tablas
FONT_TEXT = 24                     # botones y textos normales
FONT_LARGE = 32                    # avisos grandes y títulos de recuadros
FONT_TITLE_S = 40                  # títulos de carteles
FONT_TITLE = 48                    # títulos de pantalla
FONT_TITLE_L = 56                  # títulos principales
FONT_TITLE_XL = 64                 # títulos de menú
FONT_BANNER = 72                   # carteles enormes ("VS", gol de oro)
FONT_GOAL = 80                     # "¡GOOOL!"
FONT_COUNTDOWN = 96                # números de la cuenta regresiva
FONT_GO = 104                      # "¡YA!"
FONT_GIANT = 120                   # signo de pregunta del rival que falta

# --- velos claros sobre el estadio (opacidad de 0 a 255)
VEIL_MENU = 70                     # menú principal: el estadio se ve casi entero
VEIL_SUBMENU = 90                  # submenús
VEIL_RESULT = 100                  # pantallas de resultado
VEIL_PROFILE = 110                 # pantalla del nombre
VEIL_OVERLAY = 120                 # carteles sobre el partido y pantallas de elección
VEIL_ONLINE = 130                  # entrada al online
VEIL_LIST = 140                    # listas y formularios (salas, controles)
VEIL_BOOT = 150                    # arranque y leyenda de poderes
VEIL_ERROR = 170                   # pantallas de error

# --- animación
BLINK_HZ = 3                       # parpadeos por segundo del cursor ► de los botones
BOB_HZ = 4                         # saltitos por segundo del botón elegido
BOB_PX = 2                         # px que sube el botón elegido en cada saltito
CARET_HZ = 2.5                     # parpadeos por segundo del cursor de texto
IDLE_BOB_HZ = 1.6                  # balanceo de los personajes quietos (veces por segundo)
CELEBRATE_KICK_HZ = 14             # patadas por segundo del personaje que festeja
CELEBRATE_HOP_HZ = 7               # saltitos por segundo del personaje que festeja
CELEBRATE_KICK_ANGLE = 50          # grados que barre el botín al festejar
CELEBRATE_HOP_PX = 6               # px de los saltitos al festejar

# --- botones, paneles y recuadros estándar
BUTTON_H = 56                      # px: alto de un botón de menú
BUTTON_SMALL_H = 44                # px: alto de los botones chicos (◄ ►, Volver)
ARROW_BUTTON_W = 52                # px: ancho de los botones ◄ y ►
CURSOR_GAP = 22                    # px entre el cursor ► y el borde izquierdo del botón
SHADOW_OFFSET = 6                  # px: corrimiento de la sombra dura de tarjetas y tableros
FRAME_LINE = 4                     # px: grosor del marco negro de tarjetas y tableros
TEXT_LINE_H = 22                   # px entre renglones de texto chico
TEXT_LINE_H_BIG = 30               # px entre renglones de texto normal
