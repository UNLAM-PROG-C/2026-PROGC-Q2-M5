# Futbol De Cabeza

## Finalidad

Futbol De Cabeza es un juego de fútbol de cabeza 2D en pixel art: los jugadores saltan, cabecean y patean, y la pelota activa poderes al tocar los objetos de la cancha.
Se puede jugar de a dos en el mismo teclado, contra la computadora en Mundialito o mano a mano online por salas.
Lo hicimos como TP integrador de Programación Concurrente (UNLaM, Grupo 5) para mostrar cómo se comunican y se sincronizan los procesos.
También implementamos efectos visuales en CUDA y medimos su rendimiento frente a la versión en CPU.

## Lenguajes y versiones

El juego de escritorio y el servidor están escritos en **Python 3.12**. Los [kernels de los efectos](fdc/gpu/kernels.cu) están escritos en **CUDA C**.

## Frameworks, bibliotecas y herramientas

| Componente | Versión declarada | Uso |
| --- | --- | --- |
| pygame | `2.6.1` | Ventana, teclado, dibujo y sonido del juego. |
| NumPy | `2.5.4` | Procesamiento de los efectos visuales en CPU. |
| PyCUDA | `2026.1` (opcional) | Carga y lanza los kernels, y transfiere datos entre CPU y GPU. |
| `multiprocessing` | Biblioteca estándar de Python 3.12 | Procesos de simulación, colas de mensajes y señal de cierre. |
| `asyncio` | Biblioteca estándar de Python 3.12 | Atención concurrente de conexiones y coordinación de salas en el servidor. |
| `websockets` | `17.1` | Conexión WebSocket del cliente de escritorio y del servidor. |
| Docker | Sin versión de motor fijada; imagen base `python:3.12-slim` | Construye y ejecuta el contenedor del servidor. |
| Docker Compose | Sin versión fijada; se usa `docker compose` | Configura el servicio, las redes y los chequeos de estado del servidor. |
| PyInstaller | `6.22.3` en los requisitos de build | Arma los ejecutables de Windows y el paquete `.app` de macOS. |

Las versiones salen de [`requirements.txt`](requirements.txt), los [requisitos opcionales y de build](tools/requirements/) y la [configuración del servidor](deploy/).

## Requisitos y restricciones por descarga

| Descarga | Sistema probado | Hardware y restricciones |
| --- | --- | --- |
| Windows GPU | Windows 11 Pro (build 26200) y Windows 10 22H2 (build 19045) | Requiere una NVIDIA compatible con CUDA y un driver compatible con el paquete; no hace falta instalar el CUDA Toolkit para jugar. Pruebas: RTX 5090 con Ryzen 9 9950X3D y 32 GB de RAM; RTX 3080 con Core i7-7700K y 16 GiB de RAM. |
| Windows CPU | Windows 11 Pro y Windows 10 22H2 en las pruebas de rendimiento en CPU | No requiere NVIDIA ni CUDA. Los dos equipos de la fila anterior son referencias de rendimiento, no requisitos mínimos. |
| Mac CPU | macOS 26.6.1 en Apple Silicon (`arm64`) | Probado en un Apple M3 Max. El paquete no usa CUDA y no es para Mac Intel. |

El [`fatbin`](fdc/gpu/kernels.fatbin) trae código para `sm_75`, `sm_80`, `sm_86`, `sm_89`, `sm_90`, `sm_100` y `sm_120`; el [build](tools/build_kernels.py) también incorpora PTX para `compute_120`. `sm_75` (Turing) es la arquitectura más antigua incluida, no una GPU mínima probada.

Si jugás en CPU, elegí **SIN EFECTOS** (`F10` para alternar). En el [benchmark de FPS](docs/benchmarks/bench_fps/RESULTADOS.md), a 1280 × 720 y sin tope de cuadros ni ventana visible, este modo dio 1739,5 FPS en el Ryzen 9 9950X3D, 789,5 en el Core i7-7700K y 669,7 en la notebook de referencia (Core i7-8565U, 16 GB de RAM, Ubuntu 26.04). Son cifras del banco de pruebas, no FPS en pantalla. En CPU con **FULL**, los tres equipos quedaron por debajo de 30 FPS en todos los casos medidos.

## Navegador

No aplica: el juego se descarga y se ejecuta como aplicación de escritorio. No corre en el navegador.

## Servidor online

El servidor público corre en Docker en un NAS con Linux. El cliente de escritorio se comunica por WebSocket sobre TCP, con mensajes JSON. El servidor comprueba la versión del protocolo al conectar: `PROTOCOL_VERSION = 2`. Los detalles están en [Modo online](docs/ONLINE.md) y en la [configuración de Docker](deploy/README.md).

**[Página del juego](https://futbol.timecore.com.ar/) · [Descargas de escritorio](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest)**

## Jugar

| Sistema | Descarga | Cómo abrirlo |
| --- | --- | --- |
| Windows con NVIDIA compatible | [Windows GPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest/download/FutbolDeCabeza-windows-gpu.zip) | Descomprimí el ZIP completo y abrí `FutbolDeCabeza-windows-gpu.exe`. Requiere un driver NVIDIA compatible; los kernels ya vienen compilados. |
| Windows sin NVIDIA | [Windows CPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/latest/download/FutbolDeCabeza-windows-cpu.zip) | Descomprimí el ZIP completo y abrí `FutbolDeCabeza-windows-cpu.exe`; no requiere CUDA. |
| Mac con Apple Silicon (arm64) | [Mac CPU](https://github.com/alejandroruiz9/futbol-de-cabeza/releases/download/v1.0.10/FutbolDeCabeza-mac-arm64.zip) | Descomprimí el ZIP y abrí `FutbolDeCabeza.app`. |
| Linux o Mac Intel | Sin binario en estas descargas | Usá los pasos desde el código de abajo. |

Para empezar, elegí **Jugar → Multijugador → Local**. J1 usa `A`/`D` para moverse, `W` para saltar y `Espacio` para patear; J2 usa `←`/`→`, `↑` y `P`. `F3` muestra los procesos; `F2`, el rendimiento; `F10` alterna **SIN EFECTOS** y **FULL**. En **Presentación** (`--presentation`), jugá sin reloj y activá los seis efectos con `1`–`6`: `1` congela a J2 y `2` enciende la pelota, que quema al primero que la toque. `0` apaga los efectos manuales; el hielo y el fuego vencen solos. Presentación no cambia la calidad (eso lo hace `F10`): en **SIN EFECTOS** quedan `1` Hielo, `2` Fuego, `4` Confusión y `5` Apagón; `3` Repetición y `6` Noche son solo de **FULL**, y la leyenda no los muestra.

### Desde el código (Windows, macOS y Linux)

Usá **Python 3.12** y abrí una terminal en la carpeta que contiene `main.py`. Estos comandos arrancan en CPU, sin depender de CUDA. El entorno `.venv` es local al proyecto y no necesita activación.

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --backend cpu
```

**macOS y Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py --backend cpu
```

- **Online desde el código:** instalá también [los requisitos online](tools/requirements/requirements-online.txt) con el mismo intérprete (`-m pip install -r tools/requirements/requirements-online.txt`). Para una prueba local de red, arrancá el servidor con `-m deploy.server` con ese intérprete y abrí los dos clientes con `--server ws://127.0.0.1:8765/ws` y perfiles distintos. Las descargas ya traen una dirección de servidor configurada. Más detalles en [Modo online](docs/ONLINE.md).
- **Efectos en CPU:** agregá `--calidad full` o presioná `F10`. Para usar CUDA desde el código, necesitás una GPU NVIDIA compatible, su driver y las [dependencias GPU](tools/requirements/requirements-gpu.txt); arrancá con `--backend auto` para usar CUDA cuando inicialice o pasar a NumPy si no está disponible.

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
La comparación con locks en CPU y la prueba de conteo sin atómicas están en [los resultados de sincronización](docs/benchmarks/bench_sync/RESULTADOS.md).

Consultá también [los FPS por efecto](docs/benchmarks/bench_fps/RESULTADOS.md).

## Estructura del repositorio

| Ruta | Contenido |
| --- | --- |
| `main.py`, `requirements.txt` | Entrada del juego y dependencias base. |
| [`fdc/`](fdc/) | Simulación, interfaz, red y efectos CPU/CUDA. |
| [`assets/`](assets/) | Recursos gráficos y de audio. |
| [`deploy/`](deploy/) | Lanzador del servidor, [Dockerfile y Compose](deploy/README.md). |
| [`docs/`](docs/) | Guías, [diseño visual](docs/guia-visual.md) y benchmarks reproducibles. |
| [`tests/`](tests/) | Pruebas de simulación, red, interfaz y estilo. |
| [`tools/`](tools/) | Instaladores [Windows](tools/windows/), empaquetado [Mac](tools/packaging/mac/), utilidades de build/GPU y dependencias auxiliares. |
| `.dockerignore`, `.gitattributes`, `.gitignore` | Contexto de imagen, finales de línea y exclusiones locales. |
