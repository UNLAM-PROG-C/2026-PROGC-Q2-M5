# Cómo funciona la concurrencia en Futbol De Cabeza

Este documento explica **todo lo que corre al mismo tiempo** en el juego: la versión de escritorio, el servidor online y la versión de navegador. También explica cómo se comunican esas partes y cómo se sincronizan.

---

## 1. Respuesta corta

**¿Se usa concurrencia?** Sí, en tres formas distintas, cada una donde corresponde:

| Mecanismo | Dónde | Para qué |
|---|---|---|
| **Procesos** (`multiprocessing`, contexto `spawn`) | Escritorio: interfaz + simulación. Servidor: un proceso de simulación **por sala**. | Separar la simulación (la autoridad del partido) de la interfaz o del servidor. Cada proceso tiene su propia memoria y corre en paralelo real, en otro núcleo. |
| **Tareas asíncronas** (`asyncio`) | Servidor online. | Atender muchas conexiones a la vez con **un solo hilo**: cada conexión, cada sala y cada plazo es una tarea que se turna con las demás cuando espera. |
| **Hilos** (`threading`) | Pocos y puntuales (ver la sección 5). | Esperar algo bloqueante (la red, lanzar o cerrar un proceso) sin frenar al resto. |

**¿Se usan hilos?** Sí, pero no son la base del diseño. La interfaz y la simulación **no comparten memoria**: se hablan por **mensajes** en colas acotadas. Por eso no hacen falta locks para proteger datos compartidos, porque no hay datos compartidos. Los hilos que existen tienen una tarea concreta: esperar la red, o hacer de "cinta transportadora" de las colas de `multiprocessing`.

**En el navegador no hay concurrencia real.** Ahí no se pueden crear procesos ni hilos: todo corre en el hilo de la página, por turnos. Lo que se demuestra en el TP es la versión de escritorio y el servidor.

---

## 2. Mapa general

```
 VERSIÓN DE ESCRITORIO (main.py)                         SERVIDOR ONLINE (servidor.py, en la NAS)
 ┌──────────────────────────────┐                        ┌────────────────────────────────────────────────┐
 │ PROCESO 1: interfaz (pygame) │                        │ PROCESO SERVIDOR: un hilo con el bucle asyncio │
 │  hilo principal: ventana,    │   4 colas acotadas     │  ├ por conexión: tarea lectora + tarea escritora│
 │  eventos, dibujo, sonido     │◄──────────────────────►│  ├ Lobby (salas) — sólo lo toca este bucle      │
 │  + Event de cierre           │   + Event de cierre    │  ├ por sala: tarea "puente" a 60 Hz ───┐        │
 └──────────────────────────────┘                        │  └ hilos del ejecutor (lanzar/cerrar)  │        │
 ┌──────────────────────────────┐                        └────────────────────────────────────────┼────────┘
 │ PROCESO 2: simulación        │                              4 colas + Event (lo mismo que en el escritorio)
 │  física 120 Hz, goles,       │                        ┌────────────────────────────────────────┴────────┐
 │  poderes, azar               │                        │ PROCESO SALA 1: simulación │ PROCESO SALA 2 ... │
 └──────────────────────────────┘                        └─────────────────────────────────────────────────┘
                                                                   ▲ WebSocket (JSON)   ▲
                                                         ┌─────────┴──────┐    ┌────────┴───────┐
                                                         │ navegador casa A│    │ navegador casa B│
                                                         │ (un solo hilo)  │    │ (un solo hilo)  │
                                                         └────────────────┘    └────────────────┘
```

**Una sola simulación, en tres lugares.** La lógica de la simulación es una sola (`fdc/sim/core.py`). Cambia sólo cómo viajan los mensajes:

| Dónde corre | Clase | Transporte |
|---|---|---|
| Escritorio y salas del servidor | `SimulationServer` (`fdc/sim/process.py`) | Proceso propio, con colas de `multiprocessing` |
| Navegador (modos locales) | `InlineSimulation` (`fdc/sim/inline.py`) | Listas en memoria, dentro de la página |

---

## 3. Conceptos (para tener a mano en la defensa)

- **Proceso:** un programa en ejecución con **su propia memoria**. Dos procesos no ven las variables del otro: para hablarse necesitan un canal, como una cola o un pipe. Con `spawn`, el proceso hijo arranca un intérprete de Python nuevo e importa sólo lo que necesita. Por eso la simulación ni siquiera carga pygame (el mensaje READY lo informa).
- **Hilo:** una línea de ejecución **dentro** de un proceso. Comparte la memoria con los otros hilos de ese proceso. En Python, el GIL hace que sólo un hilo ejecute código Python por vez, pero un hilo bloqueado esperando la red o un disco no frena a los demás.
- **Tarea asíncrona (`asyncio`):** una función que, cuando tiene que esperar (`await`), le cede el turno a otra. Todas corren en **un mismo hilo**: hay concurrencia (muchas cosas en curso) pero no paralelismo. Como sólo se cambia de tarea en los `await`, entre dos `await` nadie más toca los datos y no hacen falta locks.
- **Cola acotada:** un canal productor → consumidor con capacidad máxima. Cuando se llena, hay que **decidir qué hacer**: esperar, descartar lo nuevo o descartar lo viejo. Esa decisión es la **política** de cada cola (sección 4.2).
- **`multiprocessing.Event`:** una bandera compartida entre procesos. `set()` la levanta y `wait(t)` duerme hasta que se levante o pasen `t` segundos, sin espera activa.

---

## 4. Versión de escritorio: dos procesos

### 4.1 Quién hace qué

| Proceso | Hilo principal | Nunca hace |
|---|---|---|
| **Interfaz** (`fdc/ui/app.py`) | Ventana, eventos de teclado y mouse, pantallas, dibujo a 60 cuadros por segundo, sonido. Manda **órdenes** y **controles**; recibe **estados** y **eventos**. | Calcular física, goles o poderes. |
| **Simulación** (`fdc/sim/process.py`) | Física con paso fijo de 1/120 s, reloj, goles, poderes, bombas, azar. Publica un estado cada 2 pasos (60 por segundo). | Abrir ventanas, cargar pygame o tocar el audio. |

### 4.2 Las cuatro colas y su política

| Cola | Sentido | Tamaño | Política si está llena | Por qué así |
|---|---|---|---|---|
| `cmd_q` (órdenes) | UI → SIM | 64 | `put` **con tiempo límite** (1 s). Si no entra, es un **error visible**; nunca se descarta en silencio. | Iniciar, pausar o reiniciar no se pueden perder. |
| `input_q` (controles) | UI → SIM | 4 | `put_nowait`: si está llena, **se descarta esa foto**. | La foto siguiente trae lo mismo. Saltos y patadas viajan como **contadores acumulados** (`PressCounter`), así que ninguna pulsación se pierde. |
| `state_q` (estados) | SIM → UI | 3 | **Se descarta el más viejo** y entra el nuevo ("el último gana"). | La pantalla sólo necesita el estado más reciente. |
| `event_q` (eventos y ACK) | SIM → UI | 512 | Confiables (goles, poderes, ACK, error, BYE): se reintenta hasta entregarlos. Cosméticos (rebotes, sonidos de patada): se descartan y se cuentan. | Un gol no se puede perder; un sonido sí. |

Además, un `multiprocessing.Event` (`stop_event`) pide el cierre.

### 4.3 Los dos bucles

**Interfaz**, en cada cuadro (`App.frame`):
1. Lee los eventos de pygame (teclas, mouse, foco).
2. Retira **sin bloquear** (`get_nowait`) lo que llegó de la simulación: hasta 400 eventos y el último estado.
3. Controla la salud de la simulación: si el proceso está vivo, si llegaron las confirmaciones (ACK) a tiempo y si informó un error.
4. Actualiza la pantalla y manda la foto de controles. Esa foto sirve también de **latido**.
5. Dibuja y **duerme** hasta el próximo cuadro (`FrameLimiter`, con `time.sleep`).

**Simulación** (`SimulationServer.run`):
- **Sin partido, en pausa o con el partido terminado:** espera **bloqueante** en la cola de órdenes con tiempo límite (`cmd_q.get(timeout=0.05)`). No gasta CPU.
- **En juego:** aplica órdenes y la última foto de controles, avanza los pasos que correspondan (como máximo 6 de una vez si se atrasó) y duerme con `stop_event.wait(resto)`. Esa espera además se despierta **al instante** si la interfaz pide cerrar.

No hay espera activa en ningún lado: ningún bucle pregunta "¿llegó algo?" sin dormir entre medio. Tampoco se usan `Queue.empty()` ni `qsize()` para sincronizar, porque entre la consulta y la acción la respuesta puede cambiar.

### 4.4 Sincronización (cómo se ponen de acuerdo)

| Mecanismo | Qué resuelve |
|---|---|
| **READY** | La interfaz muestra el menú recién cuando la simulación avisa que está lista, sin bloquear la ventana mientras tanto. |
| **ACK con `cid`** | Cada orden lleva un número y la simulación confirma ese número. La pausa se muestra recién con la confirmación. Si una confirmación no llega en 3 s, aparece un error visible. |
| **Número de partido (`match`)** | Al reiniciar o hacer una revancha cambia el número, y la interfaz descarta estados y eventos del partido anterior (`StateFilter`). |
| **Número de actualización (`seq`)** | Se ignora un estado más viejo que el último dibujado. |
| **Id de evento (`eid`)** | Cada evento se procesa una sola vez (`EventDeduper`). |
| **Contadores de pulsaciones** | Aunque se pierdan fotos de controles, la diferencia entre contadores dice cuántos saltos o patadas hubo (`PressCounter`). |
| **Watchdog** | Si la interfaz deja de mandar controles 0,6 s (por ejemplo, porque se está arrastrando la ventana), la simulación **pausa sola**. |
| **Proceso padre vivo** | La simulación controla cada 0,5 s que la interfaz siga viva. Si murió, termina sola: nunca queda huérfana. |
| **Cierre coordinado** (`SimLink.stop`) | Orden `shutdown` + `Event`, se drenan las colas hasta el BYE (como mucho 2 s), `join` con tiempo límite, y recién como recuperación excepcional `terminate()` y `kill()`. |

---

## 5. Todos los hilos que existen (y por qué)

| Hilo | Dónde | Lo crea | Función |
|---|---|---|---|
| Principal de la interfaz | Escritorio | Python | Bucle de pygame. pygame exige manejar los eventos en el hilo que creó la ventana. |
| Principal de la simulación | Proceso de simulación | Python | El bucle de física. |
| **Alimentador de cola** (`QueueFeederThread`) | En cada proceso que **pone** en una cola de `multiprocessing` | `multiprocessing` (automático) | Pasa los mensajes del búfer local al pipe que une los procesos. Por eso `put` no bloquea mientras se escribe en el pipe. Hay uno por cola que se escribe: en la UI para `cmd_q` e `input_q`, en la simulación para `state_q` y `event_q`. |
| Principal del servidor | Servidor | Python | El bucle `asyncio`: todas las conexiones, el `Lobby` y los puentes de las salas. |
| **Ejecutor** (`ThreadPoolExecutor` de `asyncio`) | Servidor | `run_in_executor` / `asyncio.to_thread` | Lanzar y cerrar procesos de sala (`SimLink.start` y `SimLink.stop` pueden tardar), y leer los archivos de la página. Así el bucle no se congela para el resto. |
| **Lector de red** (`fdc-red`) | Escritorio jugando online | `ThreadTransport` (`fdc/online/client.py`) | Queda bloqueado esperando mensajes del servidor (sin gastar CPU) y los deja en una cola acotada de 512. La interfaz la vacía sin bloquear en cada cuadro. |
| Hilo interno de `websockets` | Escritorio jugando online | La librería `websockets` (cliente sincrónico) | Recibe los marcos de la conexión y responde los pings. |
| Audio de SDL | Proceso de la interfaz | SDL, al iniciar `pygame.mixer` | Mezcla y reproduce los sonidos sin trabar el dibujo. No lo controla el juego. |

No hay hilos en el navegador ni en la lógica del juego.

---

## 6. Online: el servidor

### 6.1 Por qué `asyncio` y no un hilo por conexión

Un servidor de salas pasa casi todo el tiempo **esperando**: mensajes de los jugadores, el próximo ciclo o que vuelva alguien que se desconectó. Con `asyncio`, cada espera es un `await` y el único hilo atiende lo que esté listo. Ventajas:

- **Sin locks:** el `Lobby` (usuarios y salas) y las sesiones sólo los toca el bucle. Una tarea no puede quedar a mitad de una modificación cuando corre otra, porque el cambio de tarea sólo ocurre en los `await`.
- **Escala bien:** cientos de conexiones esperando no cuestan un hilo cada una.
- **Lo bloqueante, afuera:** lanzar o cerrar un proceso va a un hilo del ejecutor, y el bucle sigue atendiendo.

### 6.2 Tareas que corren en el servidor

| Tarea | Cuántas | Qué hace |
|---|---|---|
| `handler` (lectora) | Una por conexión | Recibe JSON, lo **valida** (formato, tipo, campos, tamaño máximo 2 KB, como mucho 150 mensajes por segundo) y lo enruta: salas al `Lobby`, controles y pedidos al puente de la sala. |
| `_write_loop` (escritora) | Una por conexión | Duerme en un `asyncio.Event` hasta que haya algo para mandar. Los mensajes confiables salen en orden. Los estados son **reemplazables**: si el navegador va lento, se manda sólo el último. Si se acumulan más de 400 confiables, el cliente no está leyendo y se corta su conexión, así un cliente lento no frena a nadie. |
| `RoomRunner._pump` (puente) | Una por sala en juego | Ciclo de 60 Hz: retira lo que mandó el proceso de la sala (sin bloquear), junta los controles de los dos jugadores y se los manda, reenvía los eventos y **30 estados por segundo**, y lleva la pausa pedida (los dos "listo" o 30 s). |
| `_expire_later` (plazo) | Una por jugador desconectado | Duerme 30 s. Si la persona no volvió, el partido se da por abandonado (gana el que se quedó) y se libera su lugar. |

### 6.3 Un proceso por sala

Cada sala en juego tiene su **propio proceso de simulación**, el mismo de la versión de escritorio (`SimLink` + `simulation_main`), con las mismas colas, ACK, número de partido, watchdog y cierre coordinado.

- **Aislamiento:** si una sala se traba o falla, las demás siguen jugando.
- **Paralelismo real:** cada sala puede usar otro núcleo de la NAS.
- **Autoridad:** el proceso de la sala decide todo. Los navegadores sólo mandan controles y pedidos.

### 6.4 Sincronización propia del online

| Mecanismo | Qué resuelve |
|---|---|
| **Sesión con token** | Si se corta la red (o se recarga la página), el cliente vuelve a entrar con su token y recupera su sala y su partido. |
| **Plazo de 30 s** | Mientras alguien está desconectado, el partido queda en pausa para los dos. Si vuelve, sigue; si no, gana el que se quedó. |
| **Pausa pedida** | La pide cualquiera, pero la simulación la activa recién **después del próximo gol** (`request_pause_after_goal`). Termina con los dos "listo" o a los 30 s. El puente lleva la cuenta de por qué está en pausa (`hold`) y reanuda sólo cuando ya no queda ningún motivo (ni la pausa pedida ni una desconexión). |
| **Keepalive** | El servidor manda un ping cada 5 s y corta la conexión si no recibe respuesta en 10 s. Así detecta conexiones muertas. |
| **Etiquetas de jugador** | Los nombres se pueden repetir. Cada persona conectada recibe una etiqueta única ("Ale #4821"), calculada a partir de su perfil. |
| **JSON validado, nunca `pickle`** | Un mensaje de la red no puede ejecutar código en el servidor. |

### 6.5 Recorrido de un control, de la tecla a la pantalla

```
 navegador A                servidor (bucle asyncio)                proceso de la sala
 tecla ─► foto {p:[...]} ─► handler: valida, guarda  ─────────────► (el puente la manda
          (si cambió, o        inputs[lado] = foto                     cada 1/60 s por input_q)
           cada 0,25 s)                                              física 120 Hz
                                                                     estado ─► state_q
 dibuja suavizado ◄──────── writer de A ◄── puente: último estado ◄──────┘
 (interpolación)            writer de B ◄── 30 por segundo, el mismo texto para los dos
```

---

## 7. Online: los clientes

**Escritorio** (`ThreadTransport`):

- **Recepción:** un hilo lector bloqueado en la red deja los mensajes en una `queue.Queue` acotada (512). Si se llena, el hilo espera, y eso frena la recepción, no la interfaz.
- **Interfaz:** en cada cuadro retira lo que haya (`get_nowait`) y procesa los mensajes **de a uno**. Si un mensaje cambia de pantalla, los siguientes ya los recibe la pantalla nueva y no se pierde ninguno.
- **Envío:** se manda desde el hilo principal. La librería permite enviar desde un hilo mientras otro recibe.

**Navegador** (`BrowserTransport`): un solo hilo.

- **Recepción:** el WebSocket de JavaScript avisa con un callback cuando llega un mensaje, y el callback lo agrega a un arreglo.
- **Lectura:** Python retira ese arreglo una vez por cuadro.
- **Sin locks:** JavaScript tiene un único hilo y nunca interrumpe a Python a mitad de algo. El callback corre **entre** cuadros.

---

## 8. Versión de navegador: un solo hilo, por turnos

En el navegador (pygbag, Python compilado a WebAssembly) **no existen** `multiprocessing` ni hilos. Lo que hay es concurrencia **cooperativa** con el navegador:

```
 requestAnimationFrame del navegador (≈ 60 por segundo)
   └─► App.frame(): eventos ─► simulación local o mensajes de red ─► lógica ─► dibujo
   └─► await asyncio.sleep(0)  ◄── le devuelve el control al navegador
         (ahí el navegador procesa clics, teclas y llegadas del WebSocket, y pinta)
```

- **Modos locales** (Mundialito y local de dos): usan `InlineLink`, que cumple el mismo contrato que el enlace al proceso (`SimLink`): órdenes con ACK, fotos de controles con contadores y estados con número. En cada cuadro aplica las órdenes y la última foto, y avanza la física con paso fijo de 1/120 s hasta el momento actual (como mucho 6 pasos, igual que el proceso). Corre en el mismo hilo: si la página se traba, la simulación se traba con ella, y por eso ahí no hace falta watchdog.
- **Online:** la simulación está en el proceso de la sala, en el servidor. El navegador sólo dibuja y manda controles.

---

## 9. Comunicación y sincronización

| | Comunicación (qué viaja) | Sincronización (cómo se ponen de acuerdo) |
|---|---|---|
| **Escritorio** | 4 colas: órdenes, controles, estados, eventos | READY, ACK con `cid`, número de partido, `seq`, `eid`, `Event` de cierre, watchdog, control del padre vivo, `join` con tiempo límite |
| **Servidor ↔ sala** | Las mismas 4 colas (`SimLink`) | Lo mismo. Además, el puente reanuda sólo cuando no queda ningún motivo de pausa (`hold`). |
| **Servidor ↔ navegador** | WebSocket con JSON | Sesión con token, plazo de 30 s, keepalive (ping cada 5 s, corte si no responde en 10), `match`, `seq` y `eid` en los mensajes, pausa con "listo" o 30 s |
| **Dentro del servidor** | Llamadas a funciones en el mismo hilo | Un solo dueño de los datos (el bucle), `asyncio.Event` para despertar a cada escritora |
| **Cliente de escritorio** | Cola acotada hilo lector → interfaz | `get_nowait` por cuadro, orden FIFO |

---

## 10. Problemas clásicos de concurrencia y cómo se evitan

| Problema | Cómo se evita acá |
|---|---|
| **Condición de carrera** (dos a la vez modificando lo mismo) | No hay memoria compartida entre procesos, sólo mensajes. En el servidor, los datos los toca un único hilo (el bucle). Las colas de `multiprocessing` y `queue.Queue` ya son seguras entre procesos e hilos. |
| **Interbloqueo** (dos esperándose para siempre) | Ninguna espera es infinita: `put` y `get` con tiempo límite, `join` con tiempo límite y drenaje de la cola de eventos al cerrar. El drenaje evita que el hilo alimentador de la simulación quede trabado esperando que alguien lea. |
| **Espera activa** (gastar CPU preguntando) | Se duerme siempre: `time.sleep` por cuadro, `stop_event.wait`, `get` bloqueante con tiempo límite, `await` en el servidor. |
| **Mensajes viejos o mezclados** | Número de partido y `seq`: se descartan estados de partidos anteriores o atrasados. |
| **Mensajes repetidos** | `eid` creciente y `EventDeduper`. |
| **Pulsaciones perdidas** | Contadores acumulados: perder una foto no pierde la pulsación. |
| **Productor más rápido que el consumidor** | Colas acotadas con política explícita: descartar lo viejo (estados), descartar lo nuevo (controles, cosméticos) o esperar con tiempo límite (órdenes). En el servidor, la cola de salida por conexión tiene límite y los estados se reemplazan. |
| **Procesos huérfanos** | `daemon=True`, más el control de "proceso padre vivo" en la simulación. |
| **Un cliente lento frena a todos** | Cada conexión tiene su propia tarea escritora y su propia cola. Si se atrasa demasiado, se corta sólo esa conexión. |
| **Fallas** | La simulación informa el error (`EV_ERROR`) y la interfaz lo muestra con la opción *Reintentar*, que lanza un proceso nuevo. Si falla el proceso de una sala, el servidor termina ese partido y la próxima vez lanza otro. |

---

## 11. Cómo verlo funcionando

- **Dos procesos:** `.venv/bin/python main.py --depuracion` y apretá F3. Se ven los pid de los dos procesos, que la simulación no cargó pygame, el último ACK con su tiempo de ida y vuelta, los controles reemplazados y los estados ignorados.
- **Panel del servidor (online, desde el navegador):** `/estado` muestra en vivo un proceso de simulación por sala con su pid, las tareas `asyncio` por tipo (lectoras, escritoras, keepalive, puentes de sala, plazos de reconexión), los hilos, el tráfico por segundo y el tiempo de los ACK. `/estado/completo` (con contraseña: `--clave-panel` o `FDC_CLAVE_PANEL`) agrega los jugadores y el registro de procesos. Sirve también en la NAS con el dominio. Detalles en [ONLINE.md](ONLINE.md#panel-del-servidor-para-ver-la-concurrencia-en-vivo).
- **F3 en un partido online:** muestra el pid del servidor y el del proceso de simulación de la sala, los estados y controles por segundo y el último ACK.
- **En la terminal:** `ps -ef | grep multiprocessing` muestra el proceso de simulación (y en el servidor, uno por sala en juego).
- **Registros:** `logs/fdc.log` (escritorio) y `logs/servidor.log` (servidor). Ahí se ve cuándo se lanza y se cierra cada proceso, con `method: ordenado, bye: True`.
- **Pruebas automáticas:**
  - `tests/test_process.py`: procesos reales, cierre y huérfanos.
  - `tests/test_online.py`: servidor real con conexiones reales, desconexión y reconexión.
  - `tests/test_inline.py`: la simulación dentro de la página.
- **Guía paso a paso para la defensa:** sección 9 del README.

---

## 12. Dónde está cada cosa en el código

| Tema | Archivo y función |
|---|---|
| Colas, lanzamiento, salud y cierre (UI) | `fdc/ipc.py` → `SimLink.start`, `send_command`, `send_input`, `poll`, `check_health`, `stop` |
| Núcleo de la simulación | `fdc/sim/core.py` → `SimulationCore.handle_command`, `apply_inputs`, `step_once` |
| Bucle del proceso de simulación | `fdc/sim/process.py` → `SimulationServer.run`, `_idle`, `put_state`, `put_reliable` |
| Simulación en el navegador | `fdc/sim/inline.py` → `InlineLink.poll`, `_advance` |
| Protocolo (contadores, filtros, deduplicación) | `fdc/protocol.py` → `PressCounter`, `StateFilter`, `EventDeduper` |
| Servidor: conexiones y salas | `fdc/online/server.py` → `GameServer.handler`, `route`, `_connection_lost`, `_expire_later` |
| Servidor: cola de salida | `fdc/online/server.py` → `Session.send_text`, `_write_loop` |
| Servidor: puente con la sala | `fdc/online/server.py` → `RoomRunner.tick`, `request_pause`, `player_away`, `forfeit` |
| Servidor: panel y datos de la sala (F3) | `fdc/online/server.py` → `GameServer.panel_data`, `_stats_loop`, `RoomRunner.room_info`; página `fdc/online/panel.html` |
| Salas (lógica pura) | `fdc/online/lobby.py` → `Lobby.handle` |
| Cliente de red | `fdc/online/client.py` → `ThreadTransport`, `BrowserTransport`, `NetClient.poll` |
| Bucle de la interfaz | `fdc/ui/app.py` → `App.frame`, `run`, `run_async`, `FrameLimiter` |
