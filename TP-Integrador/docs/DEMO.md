# Demo en la universidad (efectos GPU/numpy)

Esta sección cubre la muestra: cómo instalarlo en la notebook sin NVIDIA, cómo
correr la demo reproducible, qué teclas hay y cómo medir lo que se proyecta.

## Instalación rápida

En la PC de Alejandro (Windows, PowerShell, sin `python` en el PATH):

```powershell
cd C:\Users\aleja\AI\proyectos\futbol-de-cabeza-gpu\original\futbolDeCabeza
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

- `instalar-cpu.bat` hace eso mismo (y también `requirements-dev.txt`).
- `instalar-gpu.bat` agrega `requirements-gpu.txt` (pycuda, numpy con CUDA).
- Si el `Activate.ps1` está bloqueado: `Set-ExecutionPolicy -Scope Process Bypass`.
- **Notebook sin NVIDIA:** no hace falta tocar nada. `--backend auto` detecta que
  no hay CUDA y corre con numpy; el overlay muestra `CPU` y el nivel de calidad
  (Q0..Q3) que elija solo. La demo también corre así: `py main.py --demo`.

## Demo automática (`--demo`)

```powershell
py main.py --demo
```

- 10 segmentos de `--demo-seconds` (por defecto 10 s): sin efectos, hielo,
  apagón, confusión, fuego, noche, onda + estela, repetición con look de TV
  vieja, VAR y mapa de calor. Al terminar se queda en la pantalla `FIN DE LA
  DEMO` (Esc sale); para que termine sola y devuelva la tabla, correr
  `py tools\run_demo.py`.
- Semilla fija (`DEMO_SEED = 2026`): mismos goles y mismas jugadas en cada
  máquina. `--seed 7` la cambia.
- `--demo-backends cpu|gpu|both` (por defecto `both`): con `both` mide el mismo
  segmento primero en GPU y después en numpy, y escribe las dos filas.
- `--demo-frame-clock`: avanza con 1/60 s fijo en vez del reloj real. Sirve para
  capturas repetibles (`tools/record_frames.py` lo usa).
- `Tab` salta al segmento siguiente, `Espacio` pausa, `Esc` sale.

## Overlay de rendimiento (F2)

`F2` cicla `apagado → compacto → completo`. También `--overlay off|compact|full`
y `--demo` arranca en `full`.

Muestra: backend (`GPU (CUDA)` o `CPU`), FPS reales y capacidad
(`1000 / work_ms`), bloque/grilla/hilos/sobrantes, resolución procesada y de
ventana, si es sesión remota, efectos activos y el costo de cada etapa en ms.

- Texto de 22 px o más sobre panel negro semitransparente: se lee en proyector.
- Se reconstruye 4 veces por segundo (`OVERLAY_REFRESH = 0.25`), así no ensucia
  la medición.
- La ventana arranca en 1280x720 (`--window 1600x900` para cambiarla) y **nunca**
  toma pantalla exclusiva, salvo `--fullscreen`. En escritorio remoto conviene
  dejarla así: con pantalla exclusiva Windows cambia la resolución del cliente.

## Mediciones (`mediciones/*.csv`)

Cada segmento deja una fila con backend, efecto, resolución, FPS, `work_ms`
(p95 incluido) y `fx_ms`. También `demo_<fecha>_<host>_frames.csv` si se pide
`--measure-frames` (una fila por cuadro).

```powershell
py main.py --demo --measure-csv mediciones/demo_universidad.csv
py tools\report_table.py
```

`tools\report_table.py` arma la tabla Markdown (FPS, work, p95, fx y speedup
GPU/numpy) con todos los CSV de `mediciones/` y la imprime y la guarda.

## Benchmark de kernels y capturas

```powershell
py tools\bench_gpu.py --reps 20 --blocks        # kernels sueltos, GPU vs numpy
py tools\record_frames.py                       # frames/frame_NN_*.png
py tools\pack_colab.py                          # colab_pack.zip para Colab
```

- `bench_gpu.py` mide `gray`, `sobel`, `glow_composite`, `crt` y `var_look` a
  1280x720 (y `--resolutions 640x360,1280x720,1920x1080`), escribe
  `mediciones/bench_<fecha>.csv` e imprime la tabla con el speedup. `--blocks`
  barre bloques 8x8, 16x16, 32x8, 32x32; `--nsys` intenta `nsys profile`.
- `record_frames.py` corre la demo con reloj fijo y guarda un PNG por segmento
  (1280x720, con cartel y overlay) en `frames/`.
- `pack_colab.py` arma `colab_pack.zip` (fuentes, kernels, herramientas,
  notebook y frames) y avisa si pasa el límite de subida de Colab.

## Notebook / Colab

`notebooks/gpu_efectos_colab.ipynb`: sube `colab_pack.zip`, lo descomprime,
instala `pycuda` y corre el benchmark en la GPU de Colab; sirve para comparar
con la RTX local cuando en la notebook no hay NVIDIA.

## Dos instancias online (GPU + CPU)

`tools/online_two_apps.py` levanta el servidor real en un puerto libre y
arranca dos clientes de verdad (menús, sala, partido) sin ventana, uno con
`--backend gpu` y otro con `--backend cpu`. Los dos se dan listos, juegan
unos segundos con hielo y estela forzados y dejan una captura cada uno.

```powershell
py tools\online_two_apps.py --seconds 8 --duration 25
py -m unittest tests.test_gpu_isolation -v
```

- Cada cliente imprime `mode`, frames, píxeles que se movió, `fx` medio y
  máximo, y los efectos activos; termina con `OK` si los dos jugaron.
- `--shots` cambia la carpeta de las capturas (`frames\` por defecto).
- La prueba de aislamiento verifica que `fdc/sim`, `fdc/ipc` y `fdc/online`
  no importan `numpy`, `pygame`, `pycuda` ni `fdc.gpu`, ni en el código ni en
  un intérprete limpio.
