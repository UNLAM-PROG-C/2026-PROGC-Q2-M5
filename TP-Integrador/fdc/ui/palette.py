"""Paleta de colores: clara y clásica, estilo juego retro de estadio de día."""

INK = (43, 45, 66)            # contornos y textos oscuros
INK_SOFT = (84, 90, 120)    # textos secundarios, ayudas
WHITE = (255, 255, 255)       # blanco puro (textos sobre fondos oscuros, brillos)
CREAM = (255, 248, 231)       # paneles
CREAM_DARK = (236, 222, 190)  # paneles en sombra, botones desactivados
PAPER = (250, 244, 226)       # papel (fondos de tarjetas)

SKY_TOP = (150, 205, 238)     # cielo arriba
SKY_BOTTOM = (214, 238, 250)  # cielo cerca del horizonte
CLOUD = (250, 252, 255)       # nubes
CLOUD_SHADE = (222, 236, 246) # sombra de las nubes

STRUCT = (226, 231, 236)      # estructura del estadio
STRUCT_SHADE = (190, 199, 209)  # estructura del estadio a media sombra
STRUCT_DARK = (142, 153, 166) # estructura del estadio en sombra (y marco del tablero)
ROOF = (238, 241, 244)        # techo de las tribunas

SEAT_RED = (226, 150, 150)    # butacas rojas
SEAT_RED_DARK = (201, 120, 124)# butacas rojas en sombra
SEAT_BLUE = (160, 190, 226)   # butacas celestes

GRASS_A = (142, 206, 96)      # césped: franja clara
GRASS_B = (128, 194, 84)      # césped: franja oscura
GRASS_DARK = (104, 172, 70)   # césped en sombra (bordes, matas)
GRASS_FRONT = (118, 184, 76)  # césped del frente de la cancha
LINE = (246, 252, 240)        # líneas de cal

GOLD = (255, 210, 63)         # dorado: títulos, botón elegido
GOLD_DARK = (222, 160, 30)    # dorado en sombra
ORANGE = (245, 140, 50)       # naranja (avisos)
RED = (228, 87, 70)           # rojo: errores, alertas
GREEN = (80, 180, 100)        # verde: listo, conectado
BLUE = (70, 130, 220)         # azul: rival en la sala, datos
PURPLE = (150, 100, 210)      # violeta
SOFT_RED = (255, 120, 120)    # rojo suave: avisos de algo rechazado

LED_BG = (34, 36, 44)         # fondo del tablero LED
LED_OFF = (58, 54, 50)        # punto LED apagado
LED_ON = (255, 196, 70)       # punto LED encendido
LED_ON_2 = (255, 120, 80)     # punto LED de alerta (últimos segundos, gol de oro)

SHADOW = (0, 0, 0)            # sombras
ERROR_PANEL = (255, 236, 232)  # fondo rosado de los carteles de error

RGB_CHANNELS = 3              # canales de un color sin transparencia (rojo, verde, azul)
MAX_CHANNEL = 255             # valor máximo de un canal de color (rojo, verde, azul o alfa)
OPAQUE = MAX_CHANNEL          # alfa de un píxel totalmente opaco
