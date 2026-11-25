# bench_sync: mecanismos de sincronización sobre un histograma

Benchmark aparte del juego (no importa nada de `fdc/`). Resuelve el mismo
problema que el efecto noche, un histograma de luminancia de 256 bins sobre
un cuadro RGB, con distintos mecanismos de sincronización:

| Clave | Dónde | Mecanismo |
|---|---|---|
| `a_global` | GPU | `atomicAdd` en memoria global (como el kernel del juego) |
| `b_shared` | GPU | histograma privado por bloque en `__shared__` + merge global |
| `d_lock` | CPU | 8 hilos, un `threading.Lock` compartido por incremento |
| `e_private` | CPU | 8 hilos con histograma local y merge al final |
| `f_bincount` | CPU | `numpy.bincount` en un hilo (referencia) |
| `race` | ambos | sin atómico en GPU, `+=` sin lock en hilos y en procesos |

Archivos: `kernels.cu` (kernels), `frames.py` (cuadros y referencia),
`gpu_bench.py` (PyCUDA, 5 pasos), `cpu_bench.py`, `race_cpu.py`,
`run_all.py` (corre todo y guarda `results.json`).

## Cómo correrlo (PC con GPU, Windows)

Desde la raíz del repo, con el entorno de PyCUDA del juego instalado en `.venv`:

```powershell
.\.venv\Scripts\python.exe docs\benchmarks\bench_sync\run_all.py
```

Imprime una línea JSON por caso (720p y 1080p, escena uniforme y escena
oscura) y guarda `results.json`. Cada resultado se compara con
`numpy.bincount`: `ok` indica si el histograma es exacto. Tarda alrededor de
un minuto. Los resultados analizados están en `RESULTADOS.md`.
