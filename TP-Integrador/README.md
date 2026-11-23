# Futbol De Cabeza

Juego de fútbol 2D en pixel art: dos cabezones saltan, cabecean y patean, y la pelota activa poderes al tocar los objetos de la cancha. Hay tres modos de escritorio: **dos personas en el mismo teclado**, **Mundialito contra la computadora** y **1 contra 1 online por salas**. Es el trabajo integrador de **Programación Concurrente (UNLaM)**.

**[Página del juego](https://futbol.timecore.com.ar/) · [Descargas de escritorio](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest)**

## Jugar

| Sistema | Descarga | Cómo abrirlo |
| --- | --- | --- |
| Windows con NVIDIA compatible | [Windows GPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest/download/FutbolDeCabeza-windows-gpu.zip) | Descomprimí el ZIP completo y abrí `FutbolDeCabeza-windows-gpu.exe`. Requiere un driver NVIDIA compatible; los kernels ya vienen compilados. |
| Windows sin NVIDIA | [Windows CPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest/download/FutbolDeCabeza-windows-cpu.zip) | Descomprimí el ZIP completo y abrí `FutbolDeCabeza-windows-cpu.exe`; no requiere CUDA. |
| Mac con Apple Silicon (arm64) | [Mac CPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest/download/FutbolDeCabeza-mac-arm64.zip) | Descomprimí el ZIP y abrí `FutbolDeCabeza.app`. |
| Linux o Mac Intel | Sin binario en estas descargas | Usá los pasos desde el código de abajo. |

Para empezar, elegí **Jugar → Multijugador → Local**. J1 usa `A`/`D` para moverse, `W` para saltar y `Espacio` para patear; J2 usa `←`/`→`, `↑` y `P`. `F3` muestra los procesos; `F2`, el rendimiento; `F10` alterna **SIN EFECTOS** y **FULL**. En **Presentación** (`--presentation`), jugá sin reloj y activá los seis efectos con `1`–`6`: `1` congela a J2 y `2` enciende la pelota, que quema al primero que la toque. `0` apaga los efectos manuales; el hielo y el fuego vencen solos.

### Desde el código (Windows, macOS y Linux)

Usá **Python 3.13** y abrí una terminal en la carpeta que contiene `main.py`. Estos comandos arrancan en CPU, sin depender de CUDA. El entorno `.venv` es local al proyecto y no necesita activación.

**Windows (PowerShell):**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --backend cpu
```

**macOS y Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py --backend cpu
```

- **Online desde el código:** instalá también `requirements-online.txt` con el mismo intérprete (`-m pip install -r requirements-online.txt`). Para una prueba local de red, arrancá `server.py` con ese intérprete y abrí los dos clientes con `--server ws://127.0.0.1:8765/ws` y perfiles distintos. Las descargas ya traen una dirección de servidor configurada. Más detalles en [Modo online](docs/ONLINE.md).
- **Efectos en CPU:** agregá `--calidad full` o presioná `F10`. Para usar CUDA desde el código, necesitás una GPU NVIDIA compatible, su driver y las [dependencias GPU](requirements-gpu.txt); arrancá con `--backend auto` para usar CUDA cuando inicialice o pasar a NumPy si no está disponible.

## Arquitectura: concurrencia y GPU

```text
LOCAL
[Ventana Pygame] ── órdenes + controles ──► [Proceso de simulación]
                 ◄─ estados + eventos ──────
                 Cuatro colas acotadas + señal de cierre

ONLINE
[Clientes] ◄─ WebSocket/JSON ─► [Servidor asyncio] ◄─ colas ─► [Proceso por sala]

IMAGEN (en cada cliente, local u online)
[Cuadro Pygame] → [Filtros CUDA o NumPy, si FULL] → [Marcador + pantalla]
```

- **Concurrencia:** la ventana lee el teclado y dibuja; la simulación mantiene la única cancha oficial y calcula física, goles y poderes. En local son dos procesos con memoria separada, conectados por [`SimLink`](fdc/ipc.py). Las órdenes llevan confirmación, las fotos un número de partido y secuencia, y un `Event` coordina el cierre. En online, un hilo de cliente recibe de la red; el servidor alterna tareas de conexión y delega cada sala activa a un proceso que usa el mismo [núcleo de simulación](fdc/sim/core.py). El cliente puede suavizar el movimiento, pero no decide el resultado.
- **Paralelismo GPU:** los [kernels CUDA](fdc/gpu/kernels.cu) reparten el posprocesado visual entre hilos (por píxel o por partícula, según el efecto). Los histogramas usan operaciones atómicas cuando varios hilos suman al mismo bin. Sin CUDA, FULL calcula los filtros con NumPy; SIN EFECTOS conserva el juego, los poderes y el marcador sin posprocesado.

## Benchmark CPU vs. GPU

Medianas a **1280 × 720** en el equipo con **NVIDIA GeForce RTX 5090**: 50 corridas por caso después de 5 de calentamiento. El total GPU incluye reservar, subir datos, ejecutar, bajar el resultado y liberar. La aceleración total es tiempo NumPy dividido por tiempo GPU total.

| Operación | CPU NumPy (ms) | Sólo kernel (ms) | GPU total (ms) | Aceleración total |
| --- | ---: | ---: | ---: | ---: |
| Gris | 4,991 | 0,0338 | 0,905 | 5,5× |
| Hielo | 50,217 | 0,0507 | 1,281 | 39,2× |
| Focos | 30,660 | 0,0314 | 1,085 | 28,2× |
| Repetición CRT | 42,112 | 0,0412 | 1,522 | 27,7× |
| Histograma de Noche | 5,988 | 0,1460 | 1,590 | 3,8× |

Son mediciones de operaciones aisladas, **no FPS ni tiempos del partido entero**. Por ejemplo, hielo a 1080p pasó de 120,193 a 1,940 ms (61,9× en el ciclo completo). En Noche la medición GPU termina al descargar los conteos y el máximo; no incluye el resumen que sí calcula la referencia CPU. Acelerar el kernel no elimina las transferencias: por eso importa el total.

En el histograma aislado a 1080p uniforme, contar por bloque en memoria compartida redujo el tiempo de kernel en la RTX 5090 de **0,2869 a 0,0148 ms (19,4×)**.
Con los cinco pasos, el tiempo pasó de **1,053 a 0,766 ms (1,37×)**; mover los datos sigue costando.
La comparación con locks en CPU y la prueba de conteo sin atómicas están en [los resultados de sincronización](bench_sync/RESULTADOS.md).
