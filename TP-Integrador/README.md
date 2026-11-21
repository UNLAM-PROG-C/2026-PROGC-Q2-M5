# Futbol De Cabeza

**Versión 1.0.3** (2026-11-21). Los zips de Windows (CPU y GPU) y la `.app` de Mac
se arman con `tools/build_exe.py` (Windows, `--mode cpu` o `--mode full`) y
`packaging/mac/build.sh` (Mac); los dos usan `tools/pyi_rth_stdout.py` y
`tools/servidor.txt.example`. Los pasos de la publicación están en
`release/NOTAS-RELEASE.md`, fuera del repositorio.

Juego 2D para dos personas, inspirado en la jugabilidad de *Sports Heads Football*: cabezones con un botín, cancha lateral, saltos, patadas, cabezazos y poderes que se activan cuando la pelota los toca. Estilo **retro en pixel art**, con paleta clara y clásica. Se juega **en el mismo teclado**, **contra la computadora** (Mundialito) u **online** desde dos casas. Todo eso también está **en el navegador**: entrando a la página del juego se elige el modo igual que en la versión de escritorio.

Es un trabajo práctico de **Programación Concurrente**. La solución usa **dos procesos** (`multiprocessing`, contexto `spawn`) que se comunican con **colas de mensajes** y se sincronizan con **confirmaciones**, **identificadores de partido** y un **`multiprocessing.Event`** de cierre. En el online, un servidor `asyncio` atiende las conexiones y lanza **un proceso de simulación por sala** (el mismo de la versión local). La lógica de la simulación es una sola (`fdc/sim/core.py`) y corre en tres lugares: el proceso de escritorio, los procesos de sala del servidor y, en el navegador (donde no hay procesos), dentro de la misma página.

> **¿Cómo funciona la concurrencia en todo el juego?** Procesos, tareas asíncronas, hilos, colas y sincronización, del escritorio al servidor y al navegador: [docs/CONCURRENCY.md](docs/CONCURRENCY.md).

> El nombre se cambia en un único lugar: `GAME_NAME` en `fdc/config.py`.

---

## 1. Cómo ejecutarlo

Se usa el entorno virtual que ya está en la carpeta (`.venv`, Python 3.13 con pygame 2.6.1). No hace falta instalar nada más. Si alguna vez hubiera que recrearlo, la única dependencia está en `requirements.txt`.

```bash
.venv/bin/python main.py
```

### Instalación y arranque (PC con GPU y notebook sin NVIDIA)

Los efectos GPU son opcionales: sin placa NVIDIA el juego corre igual con la
versión numpy (`--backend auto` lo detecta solo) y el overlay de `F2` dice
`CPU`. En la PC de Alejandro, Python se llama con `py` (no está en el PATH).

**Sin CUDA los efectos siguen.** `FDC_GPU=0` (o `--backend cpu`) sólo apaga
CUDA: la cadena se hace con numpy y **FULL se ve completo** (tribuna animada,
luces, partículas), más lento; `OPTIMIZADO` es la versión liviana y `AUTO`
baja el nivel sólo si no llega. Para apagar los efectos hay que pedirlo:
`--sin-efectos` o `FDC_EFECTOS=0` (`--no-gpu` sigue valiendo como alias).
En esta PC, con el backend numpy a 1280x720 (`py tools\bench_calidades.py`,
180 cuadros por modo): FULL ≈ 10 fps y OPTIMIZADO ≈ 140 fps; en una Mac o una
notebook sin NVIDIA FULL queda en el orden de 8 a 20 fps y la tribuna igual se
ve. Para quien necesita fluidez sin placa, OPTIMIZADO o AUTO.

**Notebook o PC sin NVIDIA (modo CPU).** Nada de CUDA ni de Visual Studio:

```powershell
cd C:\ruta\a\futbolDeCabeza
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py main.py
```

Sin activar el entorno alcanza con `.\instalar-cpu.bat` (crea el venv e
instala) y después `.\jugar.bat`. Para la demo de la facultad:
`py main.py --demo` o `.\demo.bat`.

**PC con GPU NVIDIA (efectos en CUDA).** Además de lo anterior hace falta
`pycuda`, el `nvcc` y un compilador de C++ (ver [INSTALACION.md](INSTALACION.md)):

```powershell
py -m pip install -r requirements-gpu.txt
py main.py --backend gpu --overlay compact
```

`instalar-gpu.bat` instala todo; `activar-gpu.bat` (o `. .\activar-gpu.ps1`
en PowerShell) pone `nvcc`, `cl.exe` y las DLL de CUDA en el entorno de esa
consola: **es obligatorio abrirlo antes de `py main.py` con GPU**, porque
PyCUDA compila los kernels al arrancar. Si falta el compilador, el juego no
falla: avisa la razón y sigue en CPU.

El **zip de Windows GPU** ya trae los kernels compilados
(`fdc/gpu/kernels.fatbin`, sm_75 a sm_120 y PTX): para jugar alcanza con el
driver NVIDIA, sin `nvcc` ni CUDA Toolkit. El fatbin se regenera con
`py tools\build_kernels.py` y el juego sólo lo usa si su hash coincide con
`fdc/gpu/kernels.cu` (`kernels.sha256`).

| Comando | Qué hace |
|---|---|
| `py main.py` | Juego normal (auto: GPU si hay, si no CPU) |
| `py main.py --backend gpu --overlay compact` | Fuerza GPU y muestra el panel de rendimiento |
| `py main.py --backend cpu` | Fuerza numpy (para comparar en la misma PC) |
| `py main.py --backend cpu --calidad full` | Sin CUDA y con todos los efectos por CPU |
| `py main.py --sin-efectos` | Sin efectos (el juego original; `--no-gpu` sigue valiendo) |
| `py main.py --demo` | Demo automática de 10 efectos, GPU y CPU |
| `py tools\bench_calidades.py` | fps de FULL, OPTIMIZADO y AUTO con el backend CPU |
| `py tools\captura_cpu_full.py` | Un cuadro de FULL por CPU en `capturas\cpu-full.png` |
| `py tools\run_demo.py` | La misma demo sin ventana: tabla + CSV y termina sola |
| `py -m unittest discover -s tests` | Suite completa (tests de kernels se saltean sin CUDA) |

**FULL, OPTIMIZADO o SIN EFECTOS.** El modo se elige con `--calidad
full|optimizado|sin-efectos|auto` (también vale `off`; en el juego, **F10**
recorre FULL → OPTIMIZADO → SIN EFECTOS → AUTO y F2 dice si va por GPU o
CPU). FULL muestra todos los efectos (también sin CUDA, con numpy, más
lento), OPTIMIZADO es la versión liviana y **SIN EFECTOS** juega el render de
pygame pelado, sin postproceso (lo más liviano en CPU y en la Mac). **Por
defecto, sin elegir nada:** FULL cuando el juego corre en la GPU y SIN
EFECTOS cuando cae a CPU (el zip de CPU y la app de Mac). Lo que elija el
jugador —`--calidad`, F10, el menú de opciones o una preferencia guardada—
manda sobre ese valor.

Opciones útiles:

| Opción | Efecto |
|---|---|
| `--test` | Modo de prueba: generar cualquiera de los 17 poderes a demanda y provocar un fallo en la simulación (también se activa con `FDC_TEST=1`) |
| `--seed N` | Fija la semilla del azar de la simulación (aparición y tipo de poderes, bombas) |
| `--duration S` | Duración del partido en segundos (60 por defecto). Sirve para probar el final rápido |
| `--debug` | Abre el panel F3 desde el inicio |
| `--no-audio` | Arranca sin sonido |
| `--fullscreen` | Arranca en pantalla completa (F11 la alterna) |

Ejemplo para la defensa: `.venv/bin/python main.py --test --debug --seed 7 --duration 40`

**Versión web y online** (opcional: el juego de escritorio no lo necesita):

```bash
.venv/bin/python -m pip install -r requirements-online.txt   # una vez: websockets y pygbag
.venv/bin/python tools/build_web.py                      # compila el cliente web (build/web)
.venv/bin/python server.py                                  # servidor + página en http://127.0.0.1:8765
```

- **Jugar en el navegador:** abrí <http://127.0.0.1:8765>. Está el juego completo: Mundialito, multijugador local (dos personas en un teclado) y online. Para el online, abrilo en dos navegadores; también se puede usar *Jugar > Multijugador > Online* en `main.py`.
- **Desde otra compu de tu casa:** el servidor muestra al arrancar la dirección de la red local (por ejemplo `http://192.168.0.84:8765`). La primera vez, la Mac pregunta si Python acepta conexiones entrantes: hay que permitirlo.
- **Otro servidor:** `main.py --server wss://tu-dominio/ws` (o la variable `FDC_SERVER`, o `servidor.txt` al lado del juego; ver `docs/ONLINE.md`).
- **NAS con Windows:** la guía paso a paso (instalar, arranque automático, abrir un puerto o usar un dominio con HTTPS) está en [docs/NAS_DEPLOYMENT.md](docs/NAS_DEPLOYMENT.md). El resumen de la arquitectura online está en [docs/ONLINE.md](docs/ONLINE.md).

Los personajes son los sprites en pixel art de `assets/originals/`, convertidos por `tools/import_sprites.py` a `assets/characters/` (ya incluidos). El estadio, los íconos, la fuente y los sonidos se generan por código al arrancar. Si no hay dispositivo de audio, el juego sigue en silencio.

---

## 2. Controles

| Acción | Jugador 1 | Jugador 2 |
|---|---|---|
| Moverse | `A` / `D` | `←` / `→` |
| Saltar | `W` | `↑` |
| Patear | `Espacio` | `P` |
| Pausa | `Esc` | `Esc` |

- **Menús:** `W`/`S` o `↑`/`↓` para moverse; `Enter`, `Espacio` o `P` para elegir (también con el mouse).
- **Selección de personaje:** J1 elige con `A`/`D`, confirma con `Espacio` y cancela con `W`. J2 usa `←`/`→`, confirma con `P` y cancela con `↑`. **Con el mouse**, cada jugador tiene sus botones `◄` `OK` `►` (el `OK` pasa a `CANCELAR` al confirmar). Además, clic izquierdo en una tarjeta la elige para J1 y clic derecho para J2.
- **Volver:** todas las pantallas tienen un botón **◄ VOLVER** arriba a la izquierda (también `Esc`). En el partido, ese lugar lo ocupa **II PAUSA**, que abre la pausa con sus opciones para salir.
- **Online:** cada persona juega desde su teclado con **cualquiera de las dos combinaciones** (A/W/D + Espacio o flechas + P). `Esc` o **II PAUSA** piden la pausa, que se activa después del próximo gol; **ABANDONAR** da el partido por perdido.
- **Generales:** `F3` abre el panel de depuración, `F11` alterna la pantalla completa y `M` silencia el sonido.
- **Modo de prueba:** `F5`/`F6` eligen un poder, `F7` genera el objeto, `F8`/`F9` activan el poder para el jugador de la izquierda o el de la derecha, y `F12` provoca un fallo en la simulación.

En el partido cada jugador se identifica por su **lado y su color** (naranja a la izquierda, rosa a la derecha). El tablero, los avisos y los resultados muestran sólo el nombre del personaje; si los dos eligieron el mismo, se aclara "(izq.)" o "(der.)". J1 y J2 sólo aparecen en la selección de personajes, para indicar qué teclas usa cada uno.

Las teclas se definen en `PLAYER_KEYS` (en `fdc/config.py`) y la pantalla **Controles** del juego las muestra a partir de esa configuración.

> **Limitación de hardware:** muchos teclados (sobre todo los de notebook) no registran más de 3 o 4 teclas simultáneas en ciertas combinaciones (*ghosting*). Si una combinación de J1 y J2 no responde, el límite es del teclado, no del juego. Se pueden elegir otras teclas en la configuración.

---

## 3. Modos de juego y reglas

```
Jugar
  Mundialito        1 jugador contra la computadora (no es online: se juega en tu equipo)
  Multijugador
    Local           2 personas en el mismo teclado
    Online          1 contra 1 por internet, en salas
Controles / Poderes / Salir
```

- **Nombre:** al abrir el juego por primera vez se elige el **nombre**, una sola vez y para todos los modos. Queda guardado: en la compu en `~/.futbol_de_cabeza.json` (o el archivo de la variable `FDC_PROFILE`) y en el navegador en `localStorage`. Se cambia desde el menú con el botón del nombre (arriba a la derecha) o la tecla `N`.
- **Mismo menú en todos lados:** el de la versión de escritorio y el de la página web. En la web no aparece *Salir*, porque una página no se puede cerrar sola.

### Mundialito (1 jugador)

- **Personaje:** elegís el tuyo y enfrentás a los **otros 6**, uno por partido, en orden al azar. Las etapas son Fecha 1, Fecha 2 y Fecha 3 (fase de grupos), Cuartos de final, Semifinal y Final.
- **Avance:** sólo se avanza **ganando**. Si el partido termina empatado se juega **gol de oro**: saque desde el centro y el primer gol gana.
- **Eliminación:** si perdés, se muestra tu puesto final. Perder la Fecha 1 es el 7.º puesto, y así hasta perder la Final, que es el 2.º (subcampeón). Ganando las 6 etapas, sos **campeón del mundo**.
- **Lado y teclas:** jugás a la **derecha** y valen las dos combinaciones de teclas (A/W/D + Espacio y flechas + P).
- **Dificultad:** la computadora es cada vez más difícil (de "Muy fácil" en la Fecha 1 a "Leyenda" en la Final). Tiene las mismas capacidades físicas que vos; la dificultad sale del tiempo de reacción, los errores, la puntería del salto y cuánto defiende.
- **Guardar o abandonar:** al **terminar** un partido podés ir al menú y jugar otra cosa; el Mundialito queda guardado mientras el juego esté abierto y se sigue desde *Jugar > Mundialito*. Ir al menú desde la **pausa** de un partido es **abandonar** y se pierde el progreso. En el Mundialito la pausa no tiene *Reiniciar*.
- **Cómo juega la computadora** (`fdc/bot.py`): mira el último estado del partido, igual que la pantalla, y produce las mismas pulsaciones que el teclado. No agrega procesos ni hilos, y la simulación sigue siendo la única autoridad.

### Multijugador local y reglas comunes

- **Recorrido:** menú, selección independiente de personaje (pueden elegir el mismo), confirmación de ambos y partido con cuenta regresiva de 3 s.
- **Duración:** 60 s de **tiempo efectivo**. El reloj se detiene en pausas, cuentas regresivas y celebraciones de gol.
- **Gol:** cuenta cuando la pelota **cruza por completo** la línea de gol, por debajo del travesaño y moviéndose hacia adentro. Un mismo ingreso no suma dos veces.
- **Arco:** 250 px de alto y 112 de profundidad. Un jugador puede meterse adentro, pero la pelota igual puede cruzar la línea delante suyo (esconderse al fondo no evita el gol). Saltando desde el piso, la cabeza no llega al travesaño.
- **Cabeza como piso:** se puede caer parado sobre la cabeza del rival y saltar desde ahí con más impulso (×1,3). Así se llega arriba del travesaño, que también es sólido para pararse. Si el de abajo se corre, o el de arriba camina hacia el borde, el de arriba cae: nadie queda trabado ni puede quedarse sentado sobre el rival.
- **Después de un gol:** celebración de 2,3 s, limpieza de poderes, bombas y efectos, reubicación de jugadores y pelota, borrado del último toque y cuenta regresiva de 2 s.
- **Final:** muestra ganador o empate. Ofrece *Revancha* (mismos personajes), *Elegir personajes* o *Menú principal*.
- **Personajes:** los siete tienen **las mismas capacidades y dimensiones**. Sólo cambia la apariencia, y la simulación ni siquiera usa el personaje elegido para calcular.
- **Patada:** una por pulsación, con 0,32 s de recuperación, y sale hacia donde mira el personaje (la dirección del último movimiento). Si en `PlayerSpec` se pone `FACE_MOVEMENT = False`, el personaje mira siempre al arco rival.
- **Salto:** sólo desde el suelo, sin doble salto. Hay un pequeño margen (*coyote time*) y la pulsación se recuerda 0,1 s antes de aterrizar.
- **Cabezazo:** es el contacto físico de la cabeza con la pelota. Si la cabeza va hacia la pelota, suma un empuje extra.
- **Pelota:** es "flotante": la patada sale alta (unos 205 px, a la altura de los poderes altos), cae despacio y frena en el aire. Por eso no cruza toda la cancha de un solo golpe (pica a unos 440 px). Durante 0,12 s después de patear, la pelota no choca con quien la pateó, para que no se la frene con su propia cabeza.
- **Cancha:** los travesaños son sólidos, con la punta redondeada (la esquina entre poste y travesaño). La pared del fondo hace de poste trasero, y techo y paredes mantienen la pelota en juego. Una pelota quieta sobre el travesaño rueda de a poco hacia la cancha para no quedar inalcanzable.
- **Pérdida de foco:** se liberan todas las teclas y se pide pausa.

### Multijugador online

- **Salas:** se entra con el nombre elegido al empezar (no se vuelve a pedir). Se puede crear una sala (libre o con contraseña) o unirse a una de la lista.
- **Nombres repetidos:** se permiten. A cada persona la distingue una **etiqueta** ("Ale #4821").
- **Inicio:** con 2 en la sala, eligen personaje, tocan **¡LISTO!** y el servidor **sortea los lados**.
- **Reglas del partido:** las mismas que el local (60 s, 17 poderes y el empate vale).
- **Pausa:** la pide cualquiera y se activa **después del próximo gol**. Mientras tanto se avisa "*usuario* pidió la pausa" debajo del marcador. El partido sigue cuando los dos tocan **Estoy listo**, o a los **30 s**.
- **Desconexión:** si alguien pierde la conexión, el partido se pausa y tiene **30 s** para volver (la reconexión es automática, incluso recargando la página). Si no vuelve, **gana el que se quedó**.
- **Después del partido:** la sala queda abierta para la **revancha** (lados sorteados de nuevo) o para esperar a otro rival.

El detalle está en [docs/ONLINE.md](docs/ONLINE.md).

**Regla de contactos simultáneos** (`TOUCH_PRIORITY` en `fdc/sim/match.py`): si en el mismo paso de física ambos jugadores tocan la pelota, el último toque es de quien la tocó con mayor prioridad (**patada > cabeza > botín**). Si empatan en eso, gana el impacto de mayor velocidad. Si el empate es exacto, **se conserva el último toque anterior**. Si ambos patean en el mismo paso, la pelota sale con el promedio de las dos patadas. Los rebotes en paredes, piso o postes y las bombas nunca cambian el último toque.

---

## 4. Poderes

- **Aparición:** un objeto flotante cada **2,5 a 3,5 s de juego efectivo**, nunca más de uno a la vez. Aparece en una posición alcanzable, fuera de los arcos y sin tocar travesaños ni jugadores. **La mitad aparece al ras del piso** (a la altura del centro de la pelota rodando) y la otra mitad entre el piso y unos 180 px.
- **Duración del objeto:** si nadie lo recoge, desaparece a los **8 s**.
- **Activación:** sólo cuando lo toca **la pelota**. Cada objeto se consume una única vez.
- **Receptor:** el último jugador que tocó la pelota (con cabeza, cuerpo o patada). Si todavía no hubo un toque válido, los poderes personales **no se consumen** (la pelota lo atraviesa) y los globales sí.
- **Colores:** **verde** beneficia al receptor, **rojo** lo perjudica y **violeta** modifica el partido.

| Poder | Color | Efecto | Duración |
|---|---|---|---|
| Velocidad aumentada | Verde | Velocidad del receptor ×1,35 | 6 s |
| Salto aumentado | Verde | Impulso de salto del receptor ×1,25 | 6 s |
| Congelar al rival | Verde | El rival no puede moverse, saltar ni patear | 2 s |
| Arco grande | Verde | Altura del arco rival ×1,35 | 6 s |
| Crecer | Verde | Tamaño del receptor ×1,25 | 6 s |
| Pierna propia lesionada | Rojo | El receptor no puede patear; sí moverse, saltar y cabecear | 4 s |
| Velocidad reducida | Rojo | Velocidad del receptor ×0,65 | 6 s |
| Salto reducido | Rojo | Impulso de salto del receptor ×0,75 | 6 s |
| Congelarse | Rojo | El receptor no puede moverse, saltar ni patear | 2 s |
| Arco pequeño | Rojo | Altura del arco rival ×0,75 | 6 s |
| Encogerse | Rojo | Tamaño del receptor ×0,75 | 6 s |
| Pierna rival lesionada | Verde | El rival no puede patear; sí moverse, saltar y cabecear | 4 s |
| Bombas | Violeta | Bomba en la zona central con aviso de 1 s; la explosión empuja a jugadores y pelota según la distancia | Puntual |
| Pelota con poco rebote | Violeta | Restitución ×0,45 | 6 s |
| Pelota grande | Violeta | Radio de la pelota ×1,35 | 6 s |
| Pelota con mucho rebote | Violeta | Restitución ×1,30, con tope de 0,93 y respetando la velocidad máxima | 6 s |
| Pelota pequeña | Violeta | Radio de la pelota ×0,70 | 6 s |
| Pelota de fuego | Violeta | La pelota arde y el aire tiembla; el primero que la toca, de cualquier equipo, queda quemado: no camina, no salta ni patea. Al quemarlo, la pelota se apaga | 2 s de quemadura (la pelota se apaga a los 6 s si nadie la toca) |
| Apagón | Verde | Se apagan las luces: sólo se ve alrededor del rival | 6 s |
| Confusión | Verde | El rival ve la cancha al revés y torcida | 5 s |

Todos los valores se configuran en `POWERS` y `PowerRules` (`fdc/config.py`). Las tres últimas filas son los efectos que se sortean igual que el resto y, desde la 1.0.2, **Pelota de fuego** además quema en la simulación (no es sólo imagen).

**Cómo se combinan los efectos.** Se guardan en un diccionario con clave `(objetivo, propiedad)`:

- **Mismo efecto repetido:** renueva la duración, sin multiplicar la intensidad.
- **Efecto opuesto sobre la misma propiedad y objetivo:** reemplaza al anterior. Por ejemplo, *Velocidad reducida* reemplaza a *Velocidad aumentada*.
- **Propiedades distintas:** conviven.
- **Cálculo:** los modificadores se recalculan **siempre desde los valores base**, así que al expirar un efecto no quedan errores acumulados.
- **Pausa:** congela la aparición de objetos, los fusibles de las bombas y la duración de los efectos. Todo se descuenta sólo en juego efectivo.
- **Cambios de tamaño:** tamaño de jugadores, radio de la pelota y altura de los arcos cambian **gradualmente** (0,30 a 0,45 s), y gráficos y colisiones cambian juntos. Si un jugador agrandado queda debajo de un travesaño que bajó, se lo desplaza hacia la cancha a lo sumo 8 px por paso, sin teletransportes. Una pelota que se achica sobre la línea no cuenta como gol: tiene que moverse hacia adentro.

**Qué se ve en pantalla:**

- En la cancha, el objeto con su ícono, el color de su categoría, una etiqueta corta y un anillo con el tiempo que le queda.
- En las esquinas superiores, la lista de efectos de J1 (izquierda) y de J2 (derecha), con destinatario y segundos restantes. Los efectos sobre la pelota aparecen debajo del reloj.
- Íconos sobre la cabeza del jugador afectado, y resaltado del travesaño del arco modificado.
- Un aviso central del tipo «J1: Congelar al rival (sobre J2)».
- La leyenda completa en **Menú → Poderes**.

---

## 5. Arquitectura de procesos

```
┌──────────────────────── PROCESO PRINCIPAL: interfaz ────────────────────────┐
│  hilo principal (el que crea la ventana): eventos pygame, pantallas,       │
│  dibujo, animaciones, partículas y sonido. NO calcula posiciones, goles    │
│  ni efectos: dibuja el último estado recibido.                             │
│                                                                            │
│   InputTracker ──► SimLink.send_input()     SimLink.poll() ──► pantallas   │
│   pantallas ─────► SimLink.send_command()   (get_nowait: nunca bloquea)    │
└──────────┬───────────────────────┬──────────────────▲──────────▲───────────┘
           │ cmd_q   (64)          │ input_q (4)      │ event_q  │ state_q (3)
           │ ÓRDENES confiables    │ CONTROLES        │ (512)    │ ESTADOS
           │ con cid → ACK         │ reemplazables    │ READY,   │ reemplazables
           │                       │ (contadores)     │ ACK,     │ "el último gana"
           │   stop_event: multiprocessing.Event      │ eventos  │ match + seq
           ▼                       ▼                  │ con eid, │
┌──────────────────────── PROCESO SECUNDARIO: simulación ────────┴──────────┴─┐
│  SimulationServer (fdc/sim/process.py) → Match (fdc/sim/match.py)           │
│  única autoridad sobre movimiento, colisiones, reloj, goles, poderes,       │
│  bombas y azar. Paso fijo de 1/120 s con subpasos para la pelota.           │
│  No crea ventanas ni maneja audio: ni siquiera importa pygame.              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Protocolo (`fdc/protocol.py`)

| Mensaje | Dirección | Contenido | Política |
|---|---|---|---|
| `ready` | SIM → UI | pid, versión, Hz de física, modo prueba, semilla, si cargó pygame | confiable |
| `input` | UI → SIM | `[left, right, jumps, kicks]` (izquierda, derecha y los contadores de saltos y patadas) por jugador | reemplazable |
| `start_match`, `pause`, `resume`, `restart`, `end_match`, `shutdown` | UI → SIM | `cid` (id de orden), `match` (id de partido) | confiable + ACK |
| `debug_power`, `debug_crash` | UI → SIM | sólo modo de prueba (sin `--test` se rechazan) | confiable + ACK |
| `ack` | SIM → UI | `cid`, orden, `ok`, partido, detalle | confiable |
| `state` | SIM → UI | `match`, `seq`, `tick`, fase, reloj, jugadores, pelota, arcos, objeto, bombas, efectos | reemplazable |
| `kickoff`, `goal`, `match_end`, `paused`, `power`, `power_spawn`, `power_expired`, `pickup_expired`, `bomb_armed`, `bomb_explode` | SIM → UI | `eid` único + `match` | confiable |
| `kick`, `kick_blocked`, `touch` | SIM → UI | sonidos e impactos | cosmético (descartable) |
| `error` | SIM → UI | mensaje + traceback | confiable |
| `bye` | SIM → UI | código de salida, contadores de descartes | confiable |

**Datos reemplazables y órdenes que no pueden perderse:**

- **Órdenes** (`cmd_q`): `put` con tiempo límite de 1 s. **Nunca se descartan**: si no entran, es un error visible. Cada una espera su ACK; si no llega en 3 s, se muestra un error.
- **Controles** (`input_q`): `put_nowait`. Si la cola está llena, se descarta **esa** foto, y como la siguiente trae el estado completo, no se pierde nada. **Saltos y patadas viajan como contadores acumulados**: cada `KEYDOWN` suma 1. La simulación compacta la cola quedándose con la última foto, y la diferencia de contadores le dice cuántas pulsaciones hubo. Así una pulsación breve **no desaparece** al compactar (`PressCounter`, con su prueba en `test_protocol.py`).
- **Estados** (`state_q`, tamaño 3): «el último gana». Si la cola está llena, la simulación quita el estado **más viejo** y pone el nuevo. La interfaz drena todo en cada cuadro y dibuja sólo el último válido. No hay acumulación de estados viejos.
- **Eventos** (`event_q`): los críticos (gol, poder, ACK, final…) se entregan siempre, porque la simulación reintenta mientras no se esté cerrando. Los cosméticos (sonido de rebote) se descartan si la cola está llena y se cuentan en el panel F3. Cada evento tiene un `eid` creciente y la interfaz **procesa cada uno una sola vez** (`EventDeduper`), así un sonido nunca se repite por procesar dos veces un evento.

---

## 6. Dónde está la comunicación y dónde la sincronización

**Comunicación** (intercambio de datos):

- `fdc/ipc.py`, en la clase `SimLink` (lado interfaz): `send_command`, `send_input`, `poll`.
- `fdc/sim/process.py`, en la clase `SimulationServer` (lado simulación): `drain_commands`, `drain_inputs`, `emit`, `publish_state`.

**Sincronización** (coordinación del comportamiento de ambos procesos):

| Mecanismo | Dónde | Qué garantiza |
|---|---|---|
| **READY** | `BootScreen` espera `link.ready` | No se puede jugar antes de que la simulación esté lista. La ventana sigue respondiendo mientras tanto (espera con límite de 20 s y luego error) |
| **ACK por orden (`cid`)** | `MatchScreen._on_ack`, `SimLink.pending` | La pausa **se muestra recién cuando la simulación la confirma** («Pausando… esperando confirmación»). Lo mismo pasa con continuar, iniciar y reiniciar |
| **Id de partido (`match`)** | `StateFilter.expect()` y el chequeo de `m["match"]` en `MatchScreen.on_link` | En revancha o reinicio, la interfaz pasa a esperar el partido nuevo **antes** del ACK. Los estados y eventos del partido anterior que todavía estén en tránsito se ignoran y se cuentan en F3 |
| **Número de actualización (`seq`)** | `StateFilter.accept()` | Nunca se dibuja un estado más viejo que el ya dibujado |
| **`multiprocessing.Event` de cierre** | `stop_event` | La simulación duerme con `stop_event.wait(time_left)` (lo que falta del paso), así que despierta **al instante** cuando se pide cerrar |
| **BYE + `join` con tiempo límite** | `SimLink.stop()` | Cierre coordinado (ver la sección 7) |
| **Colas acotadas** | tamaños en `config.IPC` | Contrapresión: ninguna cola crece sin límite |
| **Watchdog de controles** | `SimulationServer.run` | Si la interfaz deja de mandar controles por 0,6 s (por ejemplo, porque macOS bloquea el bucle mientras se arrastra la ventana), la simulación **se pausa sola** y lo avisa con `paused` |
| **Vigilancia del proceso padre** | `mp.parent_process().is_alive()` cada 0,5 s | Si la interfaz muere, la simulación termina sola: no quedan huérfanos (además es `daemon=True`) |

No hay esperas activas en ninguno de los dos procesos:

- **Simulación en reposo** (sin partido, en pausa o con el partido terminado): se bloquea en `cmd_q.get(timeout=0.05)`.
- **Simulación en juego:** duerme entre pasos con `stop_event.wait()`.
- **Interfaz:** duerme hasta el plazo de cada cuadro con `time.sleep` (`FrameLimiter`). No se usa `Clock.tick` porque en macOS se pasa de largo y deja unos 47 FPS.

No se usan `Queue.empty()` ni `qsize()`: para leer sin bloquear se usa `get_nowait()` y se atrapa `queue.Empty`.

Tampoco hay hilos, semáforos ni procesos decorativos: en el modo local, los únicos hilos extra son los que crea `multiprocessing.Queue` internamente (el alimentador) y los de SDL para el audio. El online agrega un hilo lector de red en el cliente de escritorio y los hilos del ejecutor en el servidor. La lista completa, con el motivo de cada uno, está en [docs/CONCURRENCY.md](docs/CONCURRENCY.md).

---

## 7. Pausa, reinicio, errores y cierre

- **Pausa:** `Esc` (o la pérdida de foco) libera las teclas y envía `pause`. La interfaz muestra «Pausando…» hasta el ACK y recién entonces habilita el menú (*Continuar*, *Reiniciar*, *Menú principal*). Mientras dura la pausa, la simulación manda un estado de latido cada 0,2 s con el reloj congelado. *Continuar* envía `resume` y la simulación hace una cuenta regresiva de 2 s. Las pulsaciones hechas durante la pausa o las cuentas regresivas se descartan a propósito.
- **Reinicio y revancha:** la interfaz genera un id de partido nuevo, empieza a filtrar por él y envía `restart` o `start_match`. La simulación crea un objeto `Match` **nuevo**, sin efectos, bombas, objetos ni último toque del anterior. Todo lo que llegue del partido viejo se ignora.
- **Errores:** si la simulación lanza una excepción, envía `error` con el traceback y termina con código 1. Si muere sin avisar (por ejemplo, con `kill -9`), la interfaz lo detecta con `is_alive()` y muestra el código de salida. Si una orden no se confirma en 3 s o el READY no llega en 20 s, también se informa. En todos los casos aparece una pantalla de error comprensible con *Reintentar* (cierra ordenadamente y lanza un proceso nuevo) o *Salir*.
- **Cierre** (desde cualquier pantalla: botón de la ventana, *Salir*, Ctrl+C en la terminal o SIGTERM):
  1. La interfaz envía la orden `shutdown` **y** activa el `stop_event`.
  2. Drena `event_q` hasta recibir `bye` (máximo 2 s) y descarta los estados pendientes. Esto es necesario porque el hilo alimentador de una cola no deja terminar al proceso hasta que alguien lea lo que puso.
  3. Espera al proceso con `join(2 s)`. **Sólo si no terminó**, usa `terminate()` y luego `kill()`, dejando registro en el log.
  4. Llama a `cancel_join_thread()` en las colas que ella misma llenó (órdenes y controles), para no colgarse al salir por mensajes que ya nadie leerá.
  5. En la simulación, `state_q.cancel_join_thread()` permite salir aunque queden estados sin leer. Esos datos son reemplazables y se descartan de forma segura.
- **Señales:** la simulación ignora SIGINT, porque Ctrl+C llega a ambos procesos y el cierre lo coordina la interfaz.

**Registro:** ambos procesos escriben en `logs/fdc.log` (cada línea indica el proceso y su pid). La última línea de un cierre normal es:
`simulation shutdown: {'method': 'orderly', 'exitcode': 0, 'bye': True, ...}`

---

## 8. Pruebas y panel F3

```bash
.venv/bin/python -m unittest discover -s tests
```

Son 108 pruebas y tardan unos 100 s. Usan `unittest`; las del online necesitan además `websockets` (`requirements-online.txt`).

| Archivo | Qué prueba |
|---|---|
| `test_protocol.py` | Contadores de pulsaciones (compactación sin pérdidas), filtro de partido y `seq`, deduplicación de eventos |
| `test_match.py` | Gol válido y un solo gol por ingreso, gol con un jugador escondido dentro del arco, pararse sobre la cabeza del rival y caerse si se corre, subirse al travesaño desde una cabeza, salto desde el piso sin tocar el travesaño, cruce parcial, pelota sobre el travesaño, pelota que se achica sobre la línea, sin atravesar travesaños ni cabezas a velocidad máxima, velocidad máxima, choques entre jugadores, último toque (incluye contactos simultáneos), una patada por pulsación, recuperación, sin doble salto, reloj congelado en pausa, cuentas regresivas y celebración, final con empate o victoria, y un partido completo con entradas aleatorias que verifica invariantes en cada paso |
| `test_powers.py` | Los 17 poderes, receptor y rival, sin último toque, expiración que vuelve a la base, reemplazo, renovación, convivencia, pausa que congela todo, aparición cada 2,5 a 3,5 s con la mitad al ras del piso y vencimiento a 8 s, congelado, lesión, tamaño gradual, bombas sin cambiar el último toque, jugador liberado sin teletransporte |
| `test_fire.py` | El poder de fuego en la simulación: el primer toque quema 2 s (no camina, no salta, no patea), apaga la pelota, el segundo toque no hace nada, a los 6 s se apaga sola y la quemadura viaja en el estado |
| `test_process.py` | **Procesos reales:** READY desde otro pid y sin pygame, iniciar, pausar (reloj congelado en los latidos), continuar, reiniciar (sólo se aceptan estados del partido nuevo, sin efectos), eventos de partidos anteriores, watchdog, cierre ordenado (`bye`, código 0), fallo informado, proceso muerto detectado, sin huérfanos si la interfaz muere, órdenes de prueba rechazadas sin `--test` |
| `test_lobby.py` | Salas del online (lógica pura, sin red): nombres repetidos con etiquetas distintas (y la misma etiqueta para el mismo perfil), sala libre o con contraseña, lista con creador, máximo 2, elegir personaje, lados automáticos, revancha y desconexión |
| `test_online.py` | **Servidor real con conexiones WebSocket reales:** nombres repetidos, salas con contraseña, mensajes inválidos, archivos de la página sin salir de su carpeta. Partido completo con estados y final, revancha, abandono (gana el que se quedó y la sala sigue abierta), corte de red con pausa y vuelta con el token, y derrota por no volver en el plazo. También prueba la lógica de la sala sin procesos (pausa pedida que espera el gol, "listo" de los dos, 30 s, desconexión durante la pausa), la pausa tras el gol en la simulación, la interpolación y la validación de mensajes |
| `test_inline.py` | La simulación dentro de la página (versión de navegador): READY, ACK, estados con número, controles con contadores, pausa con el reloj congelado, sin "ponerse al día" de golpe tras una traba, error informado sin romper la interfaz. También prueba la **app en modo navegador** sin procesos: menú sin *Salir*, Mundialito (moverse, pausa, abandonar), multijugador local con los dos jugadores moviéndose y entrada al online |
| `test_online_ui.py` | La **aplicación de escritorio** sin ventana contra un servidor real, con un rival de prueba: nombre, lista, sala privada con contraseña, elegir personaje, listo, partido (el movimiento lo decide el servidor), pausa pedida con el aviso bajo el marcador, abandono del rival y resultado |
| `test_tournament.py` | Torneo (los 6 rivales, avance, puestos al perder, campeón) y rival automático (no aprieta teclas fuera del juego, le gana a un jugador quieto, el nivel más alto le gana al más bajo). El gol de oro está en `test_match.py` |
| `test_constants.py` | La regla de **"sin números mágicos"** (ver la sección 10): recorre todo el código Python y falla si dentro de una función aparece un número que no sea 0, 1, -1, 2 o 0,5, o si una constante con números no tiene su comentario |
| `test_style.py` | El **estándar de codificación** (ver la sección 10): funciones de menos de 15 líneas, líneas de hasta 80 columnas, sangría de 4 espacios, imports de módulos y todo el código en inglés |
| `test_ui_smoke.py` | La **aplicación completa** sin ventana visible (SDL `dummy`) manejada con eventos de teclado. Recorre menú, Jugar > Multijugador > Online (pide el nombre y vuelve sin conectarse) y Local, controles, leyenda, selección del mismo personaje, movimiento, salto, poder, pausa confirmada, pérdida de foco, reinicio, final, revancha, vuelta al menú y cierre ordenado. También prueba un Mundialito (elegir, jugar con las dos combinaciones de teclas, resultado, progreso guardado al ir al menú y abandono desde la pausa), la pantalla de error y *Reintentar* | También prueba que el nombre se pide al empezar (y no se puede dejar vacío), que queda guardado y que al cambiarlo desde el menú se conserva el mismo jugador.

Durante las pruebas se ven en la salida trazas de error y avisos que son esperados:

- Las pruebas de fallo lo provocan a propósito, así que aparecen trazas de error.
- `test_process.OrphanTest` mata con SIGKILL a un proceso anfitrión. Por eso Python avisa al final `resource_tracker: ... leaked semaphore objects`: los semáforos de ese proceso no pudieron liberarse y el `resource_tracker` los libera al terminar. Es la consecuencia de simular una muerte abrupta; no ocurre en un cierre normal.

**Panel F3** (o `--debug`) muestra:

- los pid de ambos procesos, si la simulación está viva y si cargó pygame;
- la pantalla actual, el número de partido y la fase;
- la pausa según la simulación y según la interfaz;
- el número de actualización (`seq`), el `tick` y el reloj;
- el **último mensaje confirmado**, con su `cid`, resultado y tiempo de ida y vuelta, y la cantidad de órdenes sin confirmar;
- los controles enviados y los reemplazados, y los estados y eventos recibidos;
- los estados ignorados (de otro partido o viejos), los reemplazados por la simulación y los eventos cosméticos descartados;
- los FPS, el modo de prueba y la semilla;
- **en un partido online**, los datos de la sala que manda el servidor: su pid, el pid del proceso de simulación de esa sala, los estados y controles por segundo, el último ACK y la pausa.

**Panel del servidor** (online): `http://…/status` muestra en vivo los procesos de cada sala, las tareas `asyncio`, los hilos y el tráfico; `/status/full` agrega los jugadores y pide contraseña (`--panel-password` o `FDC_PANEL_PASSWORD`). Ver [docs/ONLINE.md](docs/ONLINE.md#panel-del-servidor-para-ver-la-concurrencia-en-vivo).

---

## 9. Cómo demostrar la concurrencia

1. **Dos procesos reales.** Ejecutá `.venv/bin/python main.py --test --debug --seed 7 --duration 40`. En F3 se ven dos pid distintos y «pygame cargado: no». En otra terminal, `ps -ef | grep main.py` muestra el proceso principal y el hijo `multiprocessing.spawn`.
2. **Arranque sincronizado.** La pantalla inicial dice «Esperando confirmación READY» y el menú aparece recién cuando la simulación lo confirma.
3. **Estados con número.** Al empezar el partido, F3 muestra `seq` subiendo unas 60 veces por segundo y el último confirmado `start_match #n (ok, ~20 ms)`.
4. **Pausa confirmada.** Con `Esc` aparece «Pausando… esperando confirmación» y luego el menú. En F3, `seq` sigue subiendo (los latidos) pero el **reloj no cambia**, y el último confirmado es `pause`.
5. **Pérdida de foco.** Hacé clic en otra ventana mientras un jugador camina: se pausa por foco y nadie queda caminando.
6. **Watchdog.** Arrastrá la ventana unos segundos (en macOS eso bloquea el bucle de la interfaz): la simulación se pausa sola, con «Pausa automática: la simulación dejó de recibir controles».
7. **Reinicio sin mezcla de partidos.** Desde la pausa elegí *Reiniciar*: cambia el número de partido, los efectos desaparecen y el contador de «estados ignorados de otro partido» puede subir.
8. **Compactación sin pérdidas.** Con F8 o F9 activá poderes, y probá tocar salto o patada muy rápido: cada toque produce su acción aunque la simulación se quede sólo con la última foto de controles.
9. **Falla detectada.** Con `F12`, la simulación lanza una excepción y aparece la pantalla de error con el mensaje. *Reintentar* lanza un proceso nuevo, con otro pid en F3. Otra variante: `kill -9 <pid de la simulación>` desde la terminal muestra «se detuvo inesperadamente (código -9)».
10. **Cierre coordinado.** Salí del juego y mostrá la última línea de `logs/fdc.log`: `'method': 'orderly', 'bye': True, 'exitcode': 0`.
11. **Código para mostrar:**
    - `SimLink.stop()` en `fdc/ipc.py`: el cierre;
    - `SimulationServer.run()` en `fdc/sim/process.py`: el bucle con `stop_event.wait` y el watchdog;
    - `PressCounter` y `StateFilter` en `fdc/protocol.py`.
12. **Online: un proceso por sala.** Levantá `server.py` y jugá un partido entre dos navegadores. Con `ps -ef | grep multiprocessing` aparece un proceso de simulación nuevo por cada sala en juego, y `logs/server.log` muestra cuándo se lanza y su cierre ordenado al terminar la sala.
13. **Online: desconexión.** Cerrá la pestaña de un jugador en pleno partido: el otro ve «perdió la conexión» con la cuenta de 30 s y el reloj se detiene. Si se vuelve a abrir la página a tiempo, el partido sigue; si no, gana el que se quedó.
14. **Online: pausa sin cortar la jugada.** Con `Esc`, el aviso «*usuario* pidió la pausa» aparece bajo el marcador y el partido sigue hasta el próximo gol. Recién ahí se pausa, y sigue con los dos «listo» o a los 30 s.
15. **Online: el panel del servidor.** Con dos partidos a la vez, abrí `/status`: hay dos procesos de simulación con pid distintos, una tarea lectora y una escritora por conexión y un puente por sala, todo en un solo hilo de `asyncio`. En el partido, F3 muestra el pid del proceso de esa sala y el tiempo de los ACK. Funciona igual con el dominio.
16. **Código del online para mostrar:**
    - `RoomRunner.tick()` en `fdc/online/server.py`: el puente sala ↔ proceso, los estados reemplazables, la pausa y el plazo;
    - `Session.send_text()`: la política de la cola de salida de cada conexión;
    - `ThreadTransport` en `fdc/online/client.py`: el hilo lector con su cola acotada.

---

## 10. Estructura del código

```
main.py                   entrada: argumentos, if __name__ == "__main__", freeze_support
server.py                 entrada del servidor online (salas por WebSocket + página web)
web/main.py               entrada de la versión web (pygbag): el juego completo en el navegador
fdc/config.py             nombre, resolución, teclas, física, reglas, poderes, colas (sin pygame)
fdc/protocol.py           tipos de mensaje, constructores, PressCounter, StateFilter, EventDeduper
fdc/link.py               MatchLink: contrato entre las pantallas locales y la simulación
fdc/ipc.py                SimLink (MatchLink local): proceso, colas, salud y cierre coordinado
fdc/sim/core.py           núcleo de la simulación sin transporte: órdenes y ACK, controles, pasos, estados
fdc/sim/process.py        el núcleo en su proceso: colas, bucle con stop_event.wait, watchdog, cierre
fdc/sim/inline.py         el núcleo dentro de la página (navegador): InlineLink, mismo contrato que SimLink
fdc/sim/match.py          partido: fases, reloj, goles, último toque, estado serializable
fdc/sim/physics.py        pelota, jugadores (cabeza + botín), arcos, colisiones, subpasos
fdc/sim/powers.py         objetos, efectos, reemplazo/renovación, bombas
fdc/online/lobby.py       salas del online: usuarios, salas, contraseñas, lados (lógica pura, sin red)
fdc/online/server.py      servidor asyncio (GameServer): conexiones, rutas, reconexión, página web
fdc/online/session.py     Session: un jugador conectado y su cola de salida (estados reemplazables)
fdc/online/room_runner.py RoomRunner: puente de 60 Hz entre una sala y su proceso de simulación
fdc/online/panel.py       datos del panel /status (procesos, tareas, hilos, salas, tráfico)
fdc/online/panel.html     página del panel del servidor (se actualiza sola cada segundo)
fdc/online/client.py      cliente (escritorio: hilo + cola acotada; navegador: WebSocket de JS)
fdc/online/wire.py        mensajes online en JSON: validación y compactación de estados
fdc/online/interp.py      suavizado del movimiento entre estados en el cliente online
fdc/tournament.py         torneo del Mundialito: etapas, avance, puestos, campeón
fdc/profile.py            nombre del jugador (se elige una vez) e id propio; se guarda en la compu o el navegador
fdc/bot.py                rival automático: mira el estado y genera pulsaciones (6 niveles)
fdc/ui/app.py             ventana, bucle de cuadros, eventos, foco, panel F3, cierre
fdc/ui/layout.py          medidas comunes de la interfaz: tamaños de letra, velos, ritmos, botones
fdc/ui/screens.py         arranque, menú, controles, leyenda, error, botones retro
fdc/ui/match_screens.py   selección (teclado y mouse), partido (pausa, reinicio, prueba), resultado
fdc/ui/tournament_screens.py  elección, llave del torneo, partido contra la CPU, resultado y copa
fdc/ui/online_screens.py  nombre, salas, crear sala, sala, partido online, resultado y revancha
fdc/ui/widgets.py         campos de texto y casillas retro
fdc/ui/profile_screen.py  pantalla "¿Cómo te llamás?" (al empezar y desde el menú)
fdc/ui/browser.py         en el navegador: Esc, F3, Tab y flechas no disparan acciones de la página
fdc/ui/render.py          dibujo del partido y del tablero LED a partir del estado
fdc/ui/sprites.py         jugadores en pixel art: cabeza + botín animado, contorno J1/J2, retratos
fdc/ui/characters.py      datos de los 7 personajes (nombre, selección, colores)
fdc/ui/stadium.py         estadio retro, arcos, pelota pixel art, sombras con trama
fdc/ui/pixelfont.py       fuente pixel art propia (acentos, ¡¿, flechas) y texto LED
fdc/ui/retro.py           píxeles x2, paneles y botones con bisel, pixelado
fdc/ui/palette.py         paleta clara y clásica
fdc/ui/icons.py           íconos de los 17 poderes (pixel art)
fdc/ui/fx.py              partículas cuadradas (impactos, polvo, confeti, explosiones)
fdc/ui/audio.py           sonidos sintetizados y reproducción
fdc/ui/assets.py          textos, caché y reemplazo de recursos
fdc/ui/input.py           captura de teclas y contadores de pulsaciones
tools/import_sprites.py   convierte assets/originals/*.webp en los sprites del juego
tools/build_web.py        compila el cliente web con pygbag en build/web
tools/build_exe.py        arma el juego para Windows con PyInstaller (dist/futbol-cpu, dist/futbol-full)
tools/pyi_rth_stdout.py   hook de PyInstaller: stdout/stderr sin consola (Windows --windowed y Mac)
tools/servidor.txt.example servidor online por defecto; se copia como servidor.txt al lado del juego
packaging/mac/           build.sh y FutbolDeCabeza.spec: arman FutbolDeCabeza.app y el zip de Mac
assets/originals/         sprites originales (uno por personaje, con su botín)
assets/characters/        cabezas, cuadros del botín y sprites.json (generados por el importador)
docs/ONLINE.md            modo online: reglas, arquitectura, mensajes y puesta en marcha en la NAS
docs/CONCURRENCY.md       cómo funciona la concurrencia en todo el juego (procesos, asyncio, hilos)
web/template.tmpl         pantalla de carga de la página (estadio, barra, "¡TOCÁ PARA JUGAR!")
tests/                    pruebas (unittest) y el conductor de la interfaz sin ventana
.pylintrc                 configuración oficial de pylint del estándar de Google
```

### Estándar de codificación

El código sigue la [guía de estilo de Python de Google](https://google.github.io/styleguide/pyguide.html) y las reglas de la cátedra:

- **Sangría de 4 espacios** (nunca tabulaciones) y **líneas de hasta 80 columnas**.
- **Funciones y métodos de menos de 15 líneas.** Se cuenta desde el `def` hasta la última línea; el docstring no cuenta. Las funciones largas se partieron en funciones chicas con nombre, sin cambiar lo que hacen.
- **Imports de módulos, no de nombres:** `from fdc.ui import layout` y después `layout.FONT_SMALL`. Los imports son absolutos. Los pocos imports dentro de una función tienen su motivo escrito al lado (por ejemplo, evitar un import circular entre pantallas, o que el navegador no cargue `multiprocessing`).
- **Todo el código está en inglés:** nombres, comentarios, docstrings, archivos, opciones de la línea de comandos, variables de entorno y valores del protocolo. **Lo que ve el jugador sigue en castellano** (el juego es para Argentina).
- **Sin números mágicos** (ver arriba).

Dos pruebas lo controlan en todo el proyecto: `tests/test_style.py` (las reglas de arriba) y `tests/test_constants.py` (los números). Además, `pylint` con la configuración oficial de Google (`.pylintrc`) no marca ningún aviso:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt   # una vez
.venv/bin/pylint fdc tools web tests main.py server.py
```

### Patrones de diseño

| Patrón | Dónde | Para qué |
|---|---|---|
| **Strategy** | `MatchLink` (`fdc/link.py`) con `SimLink` (`fdc/ipc.py`) e `InlineLink` (`fdc/sim/inline.py`); `ThreadTransport` y `BrowserTransport` (`fdc/online/client.py`) | Las pantallas usan el mismo contrato con la simulación en otro proceso (escritorio) o en la misma página (navegador). El cliente online cambia de transporte sin cambiar nada más. |
| **Facade** | `SimLink` y `NetClient` | Esconden todo lo de `multiprocessing` (colas, `Event`, `join`) y de la red (hilo, reconexión, token) detrás de pocos métodos: `send_command`, `send_input`, `poll`, `stop`. |
| **Command** | `SimulationCore._command_handlers` (`fdc/sim/core.py`), `Lobby._handlers` (`fdc/online/lobby.py`) | Cada orden o mensaje es un dato (`{"type": ...}`) que una tabla manda a su método. Cada orden tiene su ACK con `cid`. |
| **Template Method** | `SimulationCore` (`put_reliable`, `put_cosmetic`, `put_state`); `MatchScreen` (`extra_payload`, `controls`, `pause_items`, `on_match_over`) | El núcleo de la simulación es uno solo y cada uso define cómo salen los mensajes. El partido es uno solo y el Mundialito y el online cambian sólo esos "ganchos". |
| **State** | `App.switch` con las pantallas de `fdc/ui/*_screens.py` | Cada pantalla es un estado de la aplicación con los mismos métodos (`handle_event`, `update`, `draw`…); cada una decide cuál sigue. |
| **Observer / eventos** | `MatchScreen._on_event` con la tabla `EVENT_HANDLERS` | La simulación avisa lo que pasó (gol, poder, bomba) y la interfaz reacciona con sonido, efectos y carteles, sin que la simulación sepa nada de la pantalla. |
| **Flyweight (caché)** | `CharacterSprites`, `BallSprite`, `icons.power_icon`, `pixelfont` | Cada cuadro de un personaje, de la pelota, ícono o texto se dibuja una sola vez y se comparte. |
| **Productor-consumidor** | Las 4 colas acotadas entre la interfaz y la simulación; la cola de salida de cada `Session` | Ver la sección 6 y `docs/CONCURRENCY.md`. |
| **Jefe-trabajador** | `GameServer` con un proceso de simulación por sala | El servidor reparte cada partido a su propio proceso. |

### Constantes: sin números mágicos

Ninguna condición ni cuenta usa un número suelto como `x > 3`: cada valor es una **constante con nombre** que dice qué representa, y tiene al lado un comentario que lo explica (unidad, para qué sirve). Están en tres lugares:

- **`fdc/config.py`:** los valores del juego. Física, reglas, poderes, colas, tiempos de red y del servidor.
- **`fdc/ui/layout.py`:** las medidas que se repiten en toda la interfaz. Tamaños de letra (`FONT_SMALL`, `FONT_TITLE`…), velos (`VEIL_MENU`…), ritmos de parpadeo y la forma estándar de botones y paneles.
- **Al principio de cada módulo o de cada clase:** lo propio de esa pantalla o de ese dibujo. Por ejemplo, `ControlsScreen.ACTION_STEP` (px entre acciones), `MatchScreen.HARD_HIT_SPEED` (velocidad a la que el golpe suena al máximo), las recetas de los sonidos en `audio.py` (`SOUND_RECIPES`) o las formas de los íconos en `icons.py` (`BOLT`, `BOOT`…).

Dentro de las funciones sólo aparecen los números que no necesitan explicación: 0, 1, -1, 2 (el doble) y 0,5 (la mitad). `tests/test_constants.py` lo verifica en todo el código (`fdc/`, `tools/`, `web/` y los `.py` de la raíz): si alguien agrega un número suelto o una constante sin comentario, la prueba falla y dice el archivo y la línea.

### Gráficos: sprites y estilo retro

- **Personajes.** Salen de tus sprites (`assets/originals/<id>.webp`). `tools/import_sprites.py`:
  - separa la cabeza del botín con una línea de corte por personaje (definida en el script);
  - los reduce a pixel art nativo: 1 píxel = una celda del dibujo original, con alfa binario y colores limpios;
  - genera los cuadros del botín ya rotados (rotados en alta resolución antes de reducir, para que cada ángulo quede nítido).

  En el juego, la cabeza queda fija y **sólo se mueve el botín**. El botín cuelga de una "cadera" invisible bajo la cabeza: en reposo queda atrás, como en el dibujo original, y al patear barre en arco por delante del mentón. Los sprites miran a la izquierda; para el otro lado se espejan.
- **Todo en píxeles de 2x2.** Estadio (dibujado a 640×360 y agrandado ×2), pelota con rotación, íconos, fuente propia, tablero LED y botones con bisel. Paleta clara: cielo celeste, tribunas pastel, césped a franjas.
- **Cambiar o agregar un sprite.** Reemplazá el `.webp` en `assets/originals/`, ajustá su línea en `CUTS` dentro del importador (con `--debug` se ve el corte en rojo) y ejecutá:

```bash
.venv/bin/python tools/import_sprites.py --debug
```

- **Otros reemplazos** (si existe el archivo, se usa en lugar del generado): `assets/backgrounds/stadium.png`, `assets/sprites/ball.png`, `assets/icons/<poder>.png` y `assets/sounds/<nombre>.wav` (kick, whoosh, bounce, header, post, goal, whistle, whistle_end, select, confirm, back, power_good, power_bad, power_global, spawn, bomb_tick, explosion, beep, go, blocked, crowd).

### Valores elegidos (ajustables en `fdc/config.py`)

- **Física:** paso fijo de 120 Hz y estados a 60 Hz.
- **Jugador (cabeza + botín):** cabeza de radio 41, alto total 106. Velocidad 340 px/s, aceleración 3400 px/s² y frenado 4600 px/s². Salto de unos 128 px (desde una cabeza, unos 216 px).
- **Pelota flotante:** radio 17, gravedad 850 px/s², resistencia del aire 1,0/s, velocidad máxima 1150 px/s.
- **Patada:** potencia 920 px/s en ángulo alto (sube unos 205 px y pica a unos 440 px), recuperación de 0,32 s.
- **Arco:** 250 px de alto y 112 de profundidad.
- **Partido:** 60 s de tiempo efectivo. En el Mundialito, gol de oro si hay empate.
- **Ventana:** resolución lógica 1280 × 720, escalada con `pygame.SCALED` y píxeles nítidos.
- **Colores de jugador:** naranja para J1 y rosa para J2.

**Balance medido.** Las dimensiones y velocidades se ajustaron con simulaciones de partidos entre jugadores automáticos de prueba. Esos jugadores son una herramienta de medición que no forma parte del juego.
- **Tamaño relativo:** jugadores más chicos respecto de la cancha (más recorrido) y rápidos respecto de la pelota, para que siempre se pueda volver a defender.
- **Resistencia del aire:** hace que la pelota suba alto pero no cruce toda la cancha de un golpe. Con el arco grande pedido, bajó los goles de unos 12 a unos 7 por partido de 60 s entre esos jugadores.

Dos personas probablemente defiendan mejor que esos jugadores automáticos. Si igual se hace demasiado fácil o difícil, los números a tocar son `GOAL_HEIGHT`, `KICK_POWER`, `AIR_DRAG` y `MOVE_SPEED`.

---

## 11. Limitaciones conocidas

- **Teclado:** el *ghosting* del teclado puede impedir algunas combinaciones de J1 y J2 simultáneas (ver la sección 2).
- **Arrastrar la ventana en macOS:** congela el bucle de la interfaz. El watchdog pausa el partido a propósito, así que después hay que elegir *Continuar*.
- **Sin interpolación en el local:** la interfaz dibuja el último estado sin interpolar, porque no calcula posiciones propias. A veces un cuadro repite o saltea un estado y hay un leve tironeo ocasional. El online sí suaviza el movimiento, porque los estados llegan a 30 por segundo.
- **Simulación en Python:** si el equipo está muy cargado y la simulación se atrasa, recupera como máximo 6 pasos por vuelta: el juego se vuelve más lento en lugar de acelerarse de golpe.
- **Sprites:** tienen una sola expresión, así que los festejos, golpes y congelados se muestran con movimiento, saltitos, efectos y tintes, no con caras distintas. Los originales tienen una grilla de píxeles irregular, y al reducirlos algunos detalles finos se simplifican.
- **Audio:** es sintetizado y simple, sin música.
- **Salto aumentado:** con *Salto aumentado* se puede tocar el travesaño saltando desde el piso (es el efecto del poder).
- **Pruebas de interfaz:** usan el driver `dummy` de SDL, así que verifican el flujo y el dibujo pero **no** reemplazan jugar con un teclado real.
- **Online, latencia:**
  - **Predicción del jugador propio:** desde la 1.0.1 la pulsación se ve al instante y el servidor la corrige cuando llega su estado (reconciliación suave; si el error es grande salta). Se apaga con `--sin-prediccion` o con el botón del menú Multijugador.
  - **Demora de la red:** lo que se mueve por la predicción es sólo el jugador propio; el rival y la pelota llegan con el viaje de ida y vuelta al servidor (entre dos casas, unos 20 a 80 ms).
  - **Suavizado:** los estados del servidor llegan a 60 por segundo; la interfaz sigue dibujando 1/60 s "en el pasado".
- **Navegador:**
  - **Modos locales sin proceso aparte:** el Mundialito y el multijugador local simulan dentro de la página, porque en el navegador no hay procesos ni hilos. Es el mismo núcleo de simulación y el mismo protocolo (órdenes con ACK, fotos de controles, estados con número), pero en un solo hilo. La demostración de concurrencia es la versión de escritorio y el servidor. Si la página se traba, la simulación se traba con ella; por eso no hace falta watchdog.
  - **Primer arranque:** necesita un clic para empezar (por el audio).
  - **Intérprete:** descarga Python (WebAssembly) del CDN de pygame-web.
  - **Sin táctil:** sólo funciona con teclado y mouse, no con pantallas táctiles.
  - **Recargar:** al recargar, pide confirmación ("¿Salir del sitio?").
- **Online, servidor:**
  - **Salas en memoria:** reiniciarlo cierra las salas.
  - **Sin cuentas:** no hay ranking.
  - **Sesión por pestaña:** la sesión vive en la pestaña (`sessionStorage`). Si alguien duplica la pestaña, la copia toma el control y la original muestra "Tu sesión se abrió en otra ventana".
- **Mundialito guardado sólo en memoria:** si se cierra el juego, el torneo en curso se pierde.
- **Rival automático:** usa reglas simples (perseguir, cubrir el arco, saltar calculando la llegada de la pelota, patear de frente). Sus niveles se midieron entre computadoras; falta ajustarlos jugando contra personas.

### Verificación realizada y pendiente

**Hecho y verificado:**

- Las 108 pruebas automáticas pasan, incluidas la de constantes y la de estilo, y `pylint` con la configuración de Google no marca avisos.
- **Paso a inglés y al estándar de Google sin cambiar nada del juego:** las 42 pantallas se dibujaron antes y después y quedaron idénticas píxel por píxel. También dan exactamente lo mismo cuatro partidos simulados completos (con poderes y el rival automático), el dibujo del partido, los efectos, los sonidos, los íconos y los sprites. `tools/import_sprites.py` regenera los mismos archivos byte por byte. La versión web compilada se probó en Chrome sin ventana (nombre, menú, selección y partido local con movimiento).
- **Cambio a constantes sin cambiar nada visible:** las 40 pantallas del juego se dibujaron antes y después del cambio y quedaron idénticas píxel por píxel. Lo mismo el fondo, los 17 íconos, la pelota, el dibujo del partido con todos los poderes (224 casos), los efectos y los 21 sonidos.
- **Juego completo en un navegador real** (Chrome sin ventana, versión compilada con pygbag): menú, Mundialito contra la computadora, multijugador local con los dos jugadores a la vez y entrada al online, todo a 60 FPS.
- **Online en navegadores reales:** dos instancias de Chrome (sin ventana) jugaron contra `server.py`, con la versión web compilada con pygbag (Python 3.12 en WebAssembly) a 60 FPS. La prueba recorrió:
  - nombre, crear sala, unirse, elegir personaje, listo y lados sorteados;
  - el movimiento decidido por el servidor;
  - la pausa pedida con su aviso;
  - el abandono con el resultado;
  - un corte de red con reconexión automática;
  - una recarga de la página que vuelve al partido en unos 2 s.
- Se revisaron capturas de las pantallas nuevas: Jugar, Multijugador con el aviso de Online, elección del Mundialito, llave del torneo, partido contra la CPU con gol de oro, eliminado y campeón.
- Se recorrió el juego completo sin ventana visible y se revisaron las capturas de cada pantalla.
- La interfaz dibuja unos 59 cuadros por segundo con partido y poderes activos (driver `dummy`).
- Se ejecutó `main.py` con ventana y audio reales durante unos segundos, antes del rediseño retro: arrancó sin errores y cerró en orden. De esa ventana no se pudo tomar captura, porque la terminal no tiene permiso de grabación de pantalla.

**Pendiente de verificar con la ventana real y teclado físico:**

- Cómo se ve en tu pantalla (escalado, F11).
- La sensación de juego y el balance: patada, flote de la pelota, pararse sobre la cabeza del rival, subirse al travesaño y frecuencia de goles.
- Las teclas simultáneas, incluida la barra espaciadora.
- La pérdida de foco real.
- Cómo suenan los sonidos.
- Un partido completo entre dos personas.
- El online desde dos casas por internet, con el dominio y la NAS (hasta ahora se probó en la misma computadora).

---

## 12. Modo online

```
 navegador A ─┐  WebSocket (JSON)   ┌──────────── server.py (asyncio) ─────────────┐
              ├────────────────────►│ sesiones · salas (Lobby) · página web          │
 navegador B ─┘                     │ sala 1: puente 60 Hz ◄─colas─► proceso SIM 1   │
                                    │ sala 2: puente 60 Hz ◄─colas─► proceso SIM 2   │
                                    └────────────────────────────────────────────────┘
```

- **Una sola simulación:** la del local. El servidor lanza **un proceso de simulación por sala en juego** con `SimLink`, con las mismas colas acotadas, ACK, número de partido, watchdog y cierre coordinado. Los navegadores sólo mandan controles (con contadores de pulsaciones) y pedidos, y dibujan lo que llega.
- **Sin locks en el servidor:** un único bucle `asyncio` atiende todas las conexiones y es el único que toca las salas. Cada conexión tiene una tarea lectora y una escritora con su cola (estados reemplazables), así que un cliente lento no frena a nadie. Lo que bloquea (lanzar o cerrar un proceso) va a un hilo del ejecutor.
- **Seguridad:** por la red va JSON validado (nunca `pickle`), con tamaño y frecuencia de mensajes limitados. Las contraseñas de sala se guardan como hash con sal. El servidor decide qué jugador mueve cada conexión.
- **Navegador:** el juego completo, con la misma interfaz en pygame compilada con **pygbag** (Python en WebAssembly). Como ahí no hay procesos ni hilos:
  - **el bucle es asíncrono:** cada cuadro le devuelve el control al navegador;
  - **el online** lee el WebSocket de JavaScript una vez por cuadro;
  - **los modos locales** usan `InlineLink` (`fdc/sim/inline.py`). Cumple el mismo contrato que `SimLink`, con el mismo núcleo de simulación (`fdc/sim/core.py`), pero avanza la física dentro de la página, una vez por cuadro y con paso fijo de 1/120 s.

Reglas, catálogo de mensajes y la puesta en marcha en la NAS (Windows, dominio, HTTPS con Caddy o Cloudflare Tunnel) están en [docs/ONLINE.md](docs/ONLINE.md).

## 13. Demo en la universidad (efectos GPU/numpy)

Instalación en la notebook sin NVIDIA, demo reproducible con `--demo`, overlay de
rendimiento (F2), CSV de mediciones, benchmark de kernels, capturas y paquete de
Colab: ver [docs/DEMO.md](docs/DEMO.md).

Para comprobar que dos instancias juegan online (una con GPU y otra con
numpy) por WebSocket local, y que el servidor y la simulación no cargan
`numpy`/`pygame`/`pycuda`:

```powershell
py tools\online_two_apps.py            # deja una captura por instancia en frames\
py -m unittest tests.test_gpu_isolation -v
```
