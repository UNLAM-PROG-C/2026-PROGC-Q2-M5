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
  no hay CUDA y arranca SIN EFECTOS. Para ver todos los efectos con numpy,
  usá `--calidad full`.

## Demo automática (`--demo`)

```powershell
py main.py --demo --calidad full
```

- 7 segmentos de `--demo-seconds` (por defecto 10 s): sin efectos, hielo,
  apagón, confusión, fuego, noche con autoexposición y repetición con look de
  TV vieja. Al terminar se queda en la pantalla `FIN DE LA DEMO` (Esc sale).
- Semilla fija (`DEMO_SEED = 2026`): mismos goles y mismas jugadas en cada
  máquina. `--seed 7` la cambia.
- `--demo-backends cpu|gpu|both` (por defecto `both`): con `both` mide el mismo
  segmento primero en GPU y después en numpy, y escribe las dos filas.
- `--demo-frame-clock`: el director avanza con 1/60 s fijo en vez del reloj
  real. Para ver los efectos sin el panel, usá `--overlay off`.
- `F1` muestra la ayuda, `F10` alterna SIN EFECTOS y FULL, `Tab` salta al
  siguiente segmento y `Esc` sale. `F4` alterna CPU/GPU con la cadena activa.
  **N** alterna la noche durante un partido.

## Overlay de rendimiento (F2)

`F2` cicla `apagado → compacto → completo → pasos CUDA`. También
`--overlay off|compact|full|steps`; `--demo` arranca con el panel completo.

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
py main.py --demo --calidad full --measure-csv mediciones/demo_universidad.csv
py tools\report_table.py
```

`tools\report_table.py` arma la tabla Markdown (FPS, work, p95, fx y speedup
GPU/numpy) con todos los CSV de `mediciones/` y la imprime y la guarda.

## Benchmark de kernels y capturas

```powershell
py tools\bench_gpu.py --reps 20 --blocks
py tools\benchmark_cpu_gpu.py
```

`bench_gpu.py` mide gris, halo y CRT. El benchmark por etapas mide `k_gray`,
`ice` (bordes y aplicación), `k_spotlights`, `k_crt` y `k_luma_hist`, con
medianas de reserva, subida, cómputo, descarga y liberación. Recompilá el
fatbin con `py tools\build_kernels.py` si cambió `fdc/gpu/kernels.cu`.

Para capturas usá `--demo --calidad full --overlay off`: dejá pasar al menos
3 s de cada segmento y esperá a que no haya cuenta regresiva ni cartel de
saque. En fuego buscá la pelota sobre el pasto y cerca de una línea. En hielo
buscá un jugador cerca de una línea o del círculo central.

La prueba de aislamiento del servidor y de la simulación no necesita GPU:

```powershell
py -m unittest discover -s tests -p test_gpu_isolation.py -v
```
