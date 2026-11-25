# FPS por efecto: GPU vs CPU

Medido el 2026-11-23. La RTX 5090 y la notebook se midieron con la 1.0.9
(`9384ce7`, rama `estilo`); la RTX 3080, con el paquete GPU de Windows 1.0.10.

## Hardware

| | PC (columna principal) | Notebook (referencia) |
|---|---|---|
| CPU | AMD Ryzen 9 9950X3D 16-Core (16 núcleos / 32 hilos) | Intel Core i7-8565U @ 1.80 GHz (4 / 8) |
| GPU | NVIDIA GeForce RTX 5090, 32 GB, driver 610.88 (32.0.16.1088) | sin GPU NVIDIA (no se mide GPU) |
| RAM | 32 GB (31,2 GB visibles) | 16 GB |
| SO | Windows 11 Pro 10.0.26200 | Ubuntu 26.04 |
| Python / pygame | 3.12.10 / pygame 2.6.1 | 3.14.9 / pygame-ce 2.5.8 |

## Resultados

Ventana de 1280x720 (la de siempre) en todas las corridas. FPS **sin el tope
de 60**: promedio de unos 10 s por fila, y entre paréntesis el 1% bajo
(p1) y el mínimo.

| Efecto (FULL) | PC GPU | PC CPU | GPU/CPU | Notebook CPU |
|---|---|---|---|---|
| Sin efecto | 183,4 (142,8 / 127,3) | 21,1 (20,2 / 19,4) | 8,7x | 10,3 (8,8 / 8,4) |
| Hielo | 166,9 (131,9 / 121,5) | 17,7 (16,9 / 16,9) | 9,4x | 10,6 (9,0 / 8,5) |
| Fuego | 135,1 (102,0 / 75,6) | 6,2 (5,9 / 5,9) | 21,8x | 3,5 (2,9 / 2,9) |
| Repetición | 198,1 (164,2 / 133,2) | 12,7 (11,9 / 11,8) | 15,6x | 7,9 (6,4 / 6,4) |
| Confusión | 135,8 (101,1 / 88,5) | 7,2 (6,6 / 6,6) | 18,9x | 3,8 (3,3 / 3,3) |
| Apagón | 144,5 (110,2 / 91,7) | 7,1 (6,9 / 6,9) | 20,4x | 3,6 (3,1 / 3,1) |
| Noche | 128,6 (113,5 / 88,7) | 5,6 (5,5 / 5,5) | 23,0x | 3,3 (2,7 / 2,7) |
| **CPU en SIN EFECTOS** | | **1739,5** (1400,8 / 782,2) | | **669,7** (447,0 / 195,4) |

## Conclusión

- Con efectos, la GPU es entre **8,7x** (sin efecto activo) y **23x** (Noche)
  más rápida que la CPU en la misma PC. Los efectos pesados (fuego,
  confusión, apagón, noche) van de 19x a 23x.
- El backend CPU en FULL **queda por debajo de 30 FPS en todas las filas**,
  incluso con un Ryzen 9 9950X3D: entre 5,6 y 21,1 FPS. En la notebook
  baja a entre 3,3 y 10,6 FPS. Nunca llega a 60.
- En SIN EFECTOS la CPU da 1740 FPS en la PC y 670 en la notebook, muy por
  encima de 60. Por eso se recomienda jugar en CPU en SIN EFECTOS: los datos
  lo sostienen.

## Método

- Script: `docs/benchmarks/bench_fps/bench_fps.py BACKEND CALIDAD SEGUNDOS SALIDA.json`, la
  misma técnica de `presentacion_gpu.py` (1.0.7): la App real en modo
  Presentación (`--presentation --seed 7 --overlay off --no-audio`), manejada
  con `tests/driver.py` (SDL `dummy`, sin ventana visible) y con
  `clock.sleep = False`, para que `App.frame()` corra sin el tope de 60.
- Por fila: se aprieta la tecla del efecto (1 a 6) y se renderiza 10 s,
  midiendo cada frame con `perf_counter`. Si el efecto se termina (hielo y
  repetición duran 6 s), se vuelve a apretar. Entre filas, `0` y se espera a
  que la cadena no tenga ningún efecto activo, así una fila no arrastra la
  anterior.
- En las corridas de 1.0.9 el efecto estuvo activo en el 97% al 100% de los
  frames de cada fila (`active_share` en los JSON). Confusión y apagón
  muestran unos pocos frames sin efecto en la cadena: son el arranque y
  el renovado de la tecla.
- p1 = FPS del percentil 99 del tiempo de frame; mínimo = el frame más lento.
- Backend `gpu` = PyCUDA con `kernels.fatbin`; backend `cpu` = la versión
  numpy de los mismos efectos (`--backend cpu`).
- SDL `dummy` no presenta en pantalla ni usa vsync; los FPS con ventana
  visible no se midieron. En la 5090 la repetición en GPU da más que «sin
  efecto» porque muestra frames guardados en vez de dibujar el partido.
- Datos crudos: `pc-gpu-full.json`, `pc-cpu-full.json`,
  `pc-cpu-sin-efectos.json`, `notebook-cpu-full.json` y
  `notebook-cpu-sin-efectos.json`. La tabla sale de `docs/benchmarks/bench_fps/table.py`.

## Segunda PC: RTX 3080 (1.0.10)

**Hardware:** Intel Core i7-7700K @ 4,20 GHz (4 núcleos / 8 hilos), NVIDIA
GeForce RTX 3080 de 10 GiB (10 240 MiB), driver 591.74, 16 GiB RAM
(2 × 8 GiB a 2133 MT/s), Windows 10 Pro for Workstations 10.0.19045.6332.

Mismo arnés de Presentación: SDL `dummy` a 1280×720, sin límite de 60 y
10 s por fila, un efecto por vez. Se verificó el SHA-256 del ZIP publicado.
El `.exe` original pasó `--help`; para medir se usó una copia local con el
punto de entrada instrumentado, sin modificar los módulos del juego, sus
bibliotecas ni el `kernels.fatbin` del ZIP. Python 3.12.10, pygame 2.6.1 y
SDL 2.28.4 incluidos en el paquete; no se instaló Python ni Git en la PC.
CUDA comprobado en `sm_86`, sin fallback a CPU. El efecto estuvo activo en
el 99,4–99,8% de los frames en GPU y en el 94,1–98,2% en CPU.

| Efecto (FULL) | RTX 3080 GPU | i7-7700K CPU | GPU/CPU |
|---|---|---|---|
| Sin efecto | 55,3 (45,9 / 40,3) | 9,0 (7,6 / 7,6) | 6,1x |
| Hielo | 47,0 (34,3 / 31,3) | 7,6 (6,3 / 6,3) | 6,2x |
| Fuego | 36,3 (26,6 / 19,8) | 2,8 (2,6 / 2,6) | 13,0x |
| Repetición | 60,9 (47,7 / 26,2) | 5,5 (5,0 / 5,0) | 11,1x |
| Confusión | 37,0 (28,5 / 21,7) | 3,3 (2,8 / 2,8) | 11,2x |
| Apagón | 38,8 (27,5 / 20,8) | 3,2 (2,7 / 2,7) | 12,1x |
| Noche | 36,6 (29,0 / 22,2) | 2,4 (2,2 / 2,2) | 15,3x |
| **CPU en SIN EFECTOS** | | **789,5** (602,3 / 247,1) | |

- En GPU FULL, la PC con la 5090 rindió **3,3–3,7×** más según la fila.
  Es una comparación entre dos equipos y versiones, no un diferencial
  medido cambiando solo la placa de video.
- El i7-7700K dio **2,4–9,0 FPS** en CPU FULL; en CPU SIN EFECTOS dio
  **789,5 FPS**, contra **1739,5 FPS** del 9950X3D en la misma prueba.

Datos crudos: `pc3080-gpu-full.json`, `pc3080-cpu-full.json` y
`pc3080-cpu-sin-efectos.json`. En SIN EFECTOS solo corresponde la fila sin
un efecto activo; no se intentan medir efectos deshabilitados.
