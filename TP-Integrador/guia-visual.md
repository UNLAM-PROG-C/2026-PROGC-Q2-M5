# Guía visual — Fútbol de Cabeza

Objetivo: juego 2D moderno, nítido, con paleta contenida. Orden de prioridad de lectura:
**pelota > jugadores > HUD > carteles > tribuna > cielo**. Lo de abajo en la lista nunca debe ganarle visualmente a lo de arriba.

## Paleta (hex)

| Rol | Hex | Uso |
|---|---|---|
| Cancha clara / oscura | `#6FBF4A` / `#5CAA3C` | franjas del césped (hoy rondan `#7CCB4B`, bajar un poco el brillo) |
| Líneas | `#F2F5F0` | líneas de cancha, red de arcos (opacidad ≤ 0.8) |
| Equipo 1 (Messi) | `#F28C28` | jugador, marcador, bandera |
| Equipo 2 (Maradona) | `#E0458F` | jugador, marcador, bandera |
| Tribuna camiseta 1 | `#A8683A` | más apagada que `#F28C28` |
| Tribuna camiseta 2 | `#9E4D70` | más apagada que `#E0458F` |
| Grada (piso/frente/borde) | `#2B2B35` / `#1C1C26` / `#54545F` | |
| HUD fondo / texto | `#23252F` / `#F6E7C1` | marcador, paneles |
| Hielo | `#8FD8FF` | solo poder Hielo |
| Cielo | `#8EC9F2` → `#DCEBF7` | nunca blanco puro |

Regla: 2 colores de equipo + neutros fríos oscuros + césped. Nada más saturado que los equipos. La tribuna usa los mismos tonos de equipo pero a ~75 % de saturación y ~70 % de brillo.

## Reglas de glow / blur / saturación

- El bloom es para **gol y poderes**, no para el partido normal. En juego normal: glow casi apagado.
- Nada de glow sobre carteles de publicidad ni líneas de cancha: hoy los carteles se ven lavados/borrosos en FULL.
- Bordes nítidos: sin blur global. Solo halo chico alrededor de fuentes de luz reales (pelota con poder, chispas).
- **Ningún efecto toca la tribuna ni los carteles**: los focos, el anillo del gol y el calor viven abajo de `PITCH_TOP` (504 px, primera fila de césped). La tribuna se queda quieta y nítida.
- Hielo: bloque celeste facetado con contorno de tinta. En pantalla compartida, el material se aplica solo al bloque; si el jugador congelado tiene una vista propia, también se tiñe esa vista.
- Jugador quemado: se oscurece un poco (tinte `#BE9682` por multiplicación) y queda entre dos capas de llamas nítidas, con un contador arriba. En FULL, además, salen **pocas brasas chicas** (2 px a 4 px) desde los pies: nada que sature ni tape al jugador.
- Cielo blanco quemado = prohibido (distrae y rompe el contraste del HUD). De noche el cielo conserva el ambiente: no toma la ganancia de la autoexposición.
- Ambos modos dibujan a resolución completa. SIN EFECTOS deja el render original de pygame; FULL aplica el postproceso completo.

Valores objetivo de `fdc/config.py` (clase `Gpu`):

| Constante | Hoy | Objetivo |
|---|---|---|
| `GLOW_THRESHOLD` | 0.62 | **0.85** (solo lo muy brillante) |
| `GLOW_STRENGTH` | 0.65 | **0.25** normal; 0.6 solo en gol/poder |
| `GLOW_RADIUS` | 3 | 2 |
| `EXPOSURE` | 1.08 | 1.0 |
| `VIGNETTE` | 0.35 | 0.25 |
| `ICE_STRENGTH` | 0.30 | **0.60** (tinte visible en una miniatura) |
| `ICE_EDGES` | 0.5 | **1.0** |
| `HEAT_AMP` | 2.5 | 1.0 (ondas de calor deforman la tribuna entera; dejar solo en Fuego) |
| `FIRE_AMP` | 9 | 14 px (distorsión de la pelota encendida) |
| `NIGHT_AMBIENT` | 0.25 | 0.18 (más contraste entre los focos) |
| `NIGHT_RADIUS` | 420 | 300 px |
| `CROWD_SHADE_TOP` | 0.62 | 0.5 (tribuna más oscura = cancha primero) |
| `CROWD_FILL` | 78 | 62 (más grada vacía, menos pared) |
| `CROWD_SHIRTS` | (0.70,0.42,0.22),(0.62,0.30,0.44) | equivalentes de `#A8683A`,`#9E4D70`: (0.66,0.41,0.23),(0.62,0.30,0.44) |
| `CROWD_FLAGS` | 17 | 28 (menos banderas, más legibles) |

Ronda 3 (valores ya aplicados):

| Constante | Antes | Ahora |
|---|---:|---:|
| `FREEZE_RADIUS` | 200 | **110** (el foco no llega a la tribuna) |
| `FREEZE_GAIN` (nueva) | — | **0.22** (foco multiplicativo, tope 0.25) |
| `ICE_PULSE` | 0.35 | **0.15** |
| `PITCH_TOP` (nueva) | — | **504** (primera fila de césped) |

## Qué bajar o sacar
1. Glow en partido normal (ver tabla).
2. Distorsión de calor sobre la tribuna fuera del poder Fuego.
3. Capturar el hielo lejos del saque y con un jugador cerca de una línea.
4. Cielo quemado: oscurecer degradé superior.
