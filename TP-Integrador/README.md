# Futbol De Cabeza

Juego 2D local para dos personas en un mismo teclado, inspirado en la jugabilidad de *Sports Heads Football*: cabezones con un botín, cancha lateral, saltos, patadas, cabezazos y poderes que se activan cuando la pelota los toca. Estilo **retro en pixel art**, con paleta clara y clásica.

Es un trabajo práctico de **Programación Concurrente**. La solución usa **dos procesos** (`multiprocessing`, contexto `spawn`) que se comunican con **colas de mensajes** y se sincronizan con **confirmaciones**, **identificadores de partido** y un **`multiprocessing.Event`** de cierre.

> El nombre se cambia en un único lugar: `GAME_NAME` en `fdc/config.py`.

---

## 1. Cómo ejecutarlo

Se usa el entorno virtual que ya está en la carpeta (`.venv`, Python 3.13 con pygame 2.6.1). No hace falta instalar nada más. Si alguna vez hubiera que recrearlo, la única dependencia está en `requirements.txt`.

```bash
.venv/bin/python main.py
```

Opciones útiles:

| Opción | Efecto |
|---|---|
| `--prueba` | Modo de prueba: generar cualquiera de los 17 poderes a demanda y provocar un fallo en la simulación (también se activa con `FDC_PRUEBA=1`) |
| `--semilla N` | Fija la semilla del azar de la simulación (aparición y tipo de poderes, bombas) |
| `--duracion S` | Duración del partido en segundos (60 por defecto). Sirve para probar el final rápido |
| `--depuracion` | Abre el panel F3 desde el inicio |
| `--sin-audio` | Arranca sin sonido |
| `--pantalla-completa` | Arranca en pantalla completa (F11 la alterna) |

Ejemplo para la defensa: `.venv/bin/python main.py --prueba --depuracion --semilla 7 --duracion 40`

Los personajes son los sprites en pixel art de `assets/originales/`, convertidos por `tools/importar_sprites.py` a `assets/personajes/` (ya incluidos). El estadio, los íconos, la fuente y los sonidos se generan por código al arrancar. Si no hay dispositivo de audio, el juego sigue en silencio.

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
- **Generales:** `F3` abre el panel de depuración, `F11` alterna la pantalla completa y `M` silencia el sonido.
- **Modo de prueba:** `F5`/`F6` eligen un poder, `F7` genera el objeto, `F8`/`F9` activan el poder para J1 o J2, y `F12` provoca un fallo en la simulación.

Las teclas se definen en `PLAYER_KEYS` (en `fdc/config.py`) y la pantalla **Controles** del juego las muestra a partir de esa configuración.

> **Limitación de hardware:** muchos teclados (sobre todo los de notebook) no registran más de 3 o 4 teclas simultáneas en ciertas combinaciones (*ghosting*). Si una combinación de J1 y J2 no responde, el límite es del teclado, no del juego. Se pueden elegir otras teclas en la configuración.

---

## 3. Reglas

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
- **Pelota:** es "flotante": la patada sale alta (unos 205 px, a la altura de los poderes), cae despacio y frena en el aire. Por eso no cruza toda la cancha de un solo golpe (pica a unos 440 px). Durante 0,12 s después de patear, la pelota no choca con quien la pateó, para que no se la frene con su propia cabeza.
- **Cancha:** los travesaños son sólidos, con la punta redondeada (la esquina entre poste y travesaño). La pared del fondo hace de poste trasero, y techo y paredes mantienen la pelota en juego. Una pelota quieta sobre el travesaño rueda de a poco hacia la cancha para no quedar inalcanzable.
- **Pérdida de foco:** se liberan todas las teclas y se pide pausa.

**Regla de contactos simultáneos** (`TOUCH_PRIORITY` en `fdc/sim/match.py`): si en el mismo paso de física ambos jugadores tocan la pelota, el último toque es de quien la tocó con mayor prioridad (**patada > cabeza > botín**). Si empatan en eso, gana el impacto de mayor velocidad. Si el empate es exacto, **se conserva el último toque anterior**. Si ambos patean en el mismo paso, la pelota sale con el promedio de las dos patadas. Los rebotes en paredes, piso o postes y las bombas nunca cambian el último toque.

---

## 4. Poderes

- **Aparición:** un objeto flotante cada **7 a 10 s de juego efectivo**, nunca más de uno a la vez. Aparece en una posición alcanzable, fuera de los arcos y sin tocar travesaños ni jugadores.
- **Duración del objeto:** si nadie lo recoge, desaparece a los **6 s**.
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

Todos los valores se configuran en `POWERS` y `PowerRules` (`fdc/config.py`).

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
| `input` | UI → SIM | `[izq, der, contador_saltos, contador_patadas]` por jugador | reemplazable |
| `start_match`, `pause`, `resume`, `restart`, `end_match`, `shutdown` | UI → SIM | `cid` (id de orden), `match` (id de partido) | confiable + ACK |
| `debug_power`, `debug_crash` | UI → SIM | sólo modo de prueba (sin `--prueba` se rechazan) | confiable + ACK |
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
| **`multiprocessing.Event` de cierre** | `stop_event` | La simulación duerme con `stop_event.wait(resto_del_paso)`, así que despierta **al instante** cuando se pide cerrar |
| **BYE + `join` con tiempo límite** | `SimLink.stop()` | Cierre coordinado (ver la sección 7) |
| **Colas acotadas** | tamaños en `config.IPC` | Contrapresión: ninguna cola crece sin límite |
| **Watchdog de controles** | `SimulationServer.run` | Si la interfaz deja de mandar controles por 0,6 s (por ejemplo, porque macOS bloquea el bucle mientras se arrastra la ventana), la simulación **se pausa sola** y lo avisa con `paused` |
| **Vigilancia del proceso padre** | `mp.parent_process().is_alive()` cada 0,5 s | Si la interfaz muere, la simulación termina sola: no quedan huérfanos (además es `daemon=True`) |

No hay esperas activas en ninguno de los dos procesos:

- **Simulación en reposo** (sin partido, en pausa o con el partido terminado): se bloquea en `cmd_q.get(timeout=0.05)`.
- **Simulación en juego:** duerme entre pasos con `stop_event.wait()`.
- **Interfaz:** duerme hasta el plazo de cada cuadro con `time.sleep` (`FrameLimiter`). No se usa `Clock.tick` porque en macOS se pasa de largo y deja unos 47 FPS.

No se usan `Queue.empty()` ni `qsize()`: para leer sin bloquear se usa `get_nowait()` y se atrapa `queue.Empty`.

Tampoco hay hilos, semáforos ni procesos decorativos: los únicos hilos extra son los que crea `multiprocessing.Queue` internamente (el alimentador) y los de SDL para el audio.

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
`cierre de la simulación: {'method': 'ordenado', 'exitcode': 0, 'bye': True, ...}`

---

## 8. Pruebas y panel F3

```bash
.venv/bin/python -m unittest discover -s tests
```

Son 66 pruebas y tardan unos 45 s. Usan sólo la biblioteca estándar (`unittest`).

| Archivo | Qué prueba |
|---|---|
| `test_protocol.py` | Contadores de pulsaciones (compactación sin pérdidas), filtro de partido y `seq`, deduplicación de eventos |
| `test_match.py` | Gol válido y un solo gol por ingreso, gol con un jugador escondido dentro del arco, pararse sobre la cabeza del rival y caerse si se corre, subirse al travesaño desde una cabeza, salto desde el piso sin tocar el travesaño, cruce parcial, pelota sobre el travesaño, pelota que se achica sobre la línea, sin atravesar travesaños ni cabezas a velocidad máxima, velocidad máxima, choques entre jugadores, último toque (incluye contactos simultáneos), una patada por pulsación, recuperación, sin doble salto, reloj congelado en pausa, cuentas regresivas y celebración, final con empate o victoria, y un partido completo con entradas aleatorias que verifica invariantes en cada paso |
| `test_powers.py` | Los 17 poderes, receptor y rival, sin último toque, expiración que vuelve a la base, reemplazo, renovación, convivencia, pausa que congela todo, aparición de 7 a 10 s y vencimiento a 6 s, congelado, lesión, tamaño gradual, bombas sin cambiar el último toque, jugador liberado sin teletransporte |
| `test_process.py` | **Procesos reales:** READY desde otro pid y sin pygame, iniciar, pausar (reloj congelado en los latidos), continuar, reiniciar (sólo se aceptan estados del partido nuevo, sin efectos), eventos de partidos anteriores, watchdog, cierre ordenado (`bye`, código 0), fallo informado, proceso muerto detectado, sin huérfanos si la interfaz muere, órdenes de prueba rechazadas sin `--prueba` |
| `test_lobby.py` | Salas del futuro online (sin red): nombre de usuario, sala libre o con contraseña, lista con creador, máximo 2, elegir personaje, lados automáticos, revancha y desconexión |
| `test_ui_smoke.py` | La **aplicación completa** sin ventana visible (SDL `dummy`) manejada con eventos de teclado. Recorre menú, controles, leyenda, selección del mismo personaje, movimiento, salto, poder, pausa confirmada, pérdida de foco, reinicio, final, revancha, vuelta al menú y cierre ordenado. También prueba la pantalla de error y *Reintentar* |

Durante las pruebas se ven en la salida trazas de error y avisos que son esperados:

- Las pruebas de fallo lo provocan a propósito, así que aparecen trazas de error.
- `test_process.OrphanTest` mata con SIGKILL a un proceso anfitrión. Por eso Python avisa al final `resource_tracker: ... leaked semaphore objects`: los semáforos de ese proceso no pudieron liberarse y el `resource_tracker` los libera al terminar. Es la consecuencia de simular una muerte abrupta; no ocurre en un cierre normal.

**Panel F3** (o `--depuracion`) muestra:

- los pid de ambos procesos, si la simulación está viva y si cargó pygame;
- la pantalla actual, el número de partido y la fase;
- la pausa según la simulación y según la interfaz;
- el número de actualización (`seq`), el `tick` y el reloj;
- el **último mensaje confirmado**, con su `cid`, resultado y tiempo de ida y vuelta, y la cantidad de órdenes sin confirmar;
- los controles enviados y los reemplazados, y los estados y eventos recibidos;
- los estados ignorados (de otro partido o viejos), los reemplazados por la simulación y los eventos cosméticos descartados;
- los FPS, el modo de prueba y la semilla.

---

## 9. Cómo demostrar la concurrencia

1. **Dos procesos reales.** Ejecutá `.venv/bin/python main.py --prueba --depuracion --semilla 7 --duracion 40`. En F3 se ven dos pid distintos y «pygame cargado: no». En otra terminal, `ps -ef | grep main.py` muestra el proceso principal y el hijo `multiprocessing.spawn`.
2. **Arranque sincronizado.** La pantalla inicial dice «Esperando confirmación READY» y el menú aparece recién cuando la simulación lo confirma.
3. **Estados con número.** Al empezar el partido, F3 muestra `seq` subiendo unas 60 veces por segundo y el último confirmado `start_match #n (ok, ~20 ms)`.
4. **Pausa confirmada.** Con `Esc` aparece «Pausando… esperando confirmación» y luego el menú. En F3, `seq` sigue subiendo (los latidos) pero el **reloj no cambia**, y el último confirmado es `pause`.
5. **Pérdida de foco.** Hacé clic en otra ventana mientras un jugador camina: se pausa por foco y nadie queda caminando.
6. **Watchdog.** Arrastrá la ventana unos segundos (en macOS eso bloquea el bucle de la interfaz): la simulación se pausa sola, con «Pausa automática: la simulación dejó de recibir controles».
7. **Reinicio sin mezcla de partidos.** Desde la pausa elegí *Reiniciar*: cambia el número de partido, los efectos desaparecen y el contador de «estados ignorados de otro partido» puede subir.
8. **Compactación sin pérdidas.** Con F8 o F9 activá poderes, y probá tocar salto o patada muy rápido: cada toque produce su acción aunque la simulación se quede sólo con la última foto de controles.
9. **Falla detectada.** Con `F12`, la simulación lanza una excepción y aparece la pantalla de error con el mensaje. *Reintentar* lanza un proceso nuevo, con otro pid en F3. Otra variante: `kill -9 <pid de la simulación>` desde la terminal muestra «se detuvo inesperadamente (código -9)».
10. **Cierre coordinado.** Salí del juego y mostrá la última línea de `logs/fdc.log`: `method: ordenado, bye: True, exitcode: 0`.
11. **Código para mostrar:**
    - `SimLink.stop()` en `fdc/ipc.py`: el cierre;
    - `SimulationServer.run()` en `fdc/sim/process.py`: el bucle con `stop_event.wait` y el watchdog;
    - `PressCounter` y `StateFilter` en `fdc/protocol.py`.

---

## 10. Estructura del código

```
main.py                   entrada: argumentos, if __name__ == "__main__", freeze_support
fdc/config.py             nombre, resolución, teclas, física, reglas, poderes, colas (sin pygame)
fdc/protocol.py           tipos de mensaje, constructores, PressCounter, StateFilter, EventDeduper
fdc/link.py               MatchLink: contrato entre la interfaz y la simulación (local u online)
fdc/ipc.py                SimLink (MatchLink local): proceso, colas, salud y cierre coordinado
fdc/sim/process.py        proceso de simulación: bucle, órdenes, watchdog, envío de estados/eventos
fdc/sim/match.py          partido: fases, reloj, goles, último toque, estado serializable
fdc/sim/physics.py        pelota, jugadores (cabeza + botín), arcos, colisiones, subpasos
fdc/sim/powers.py         objetos, efectos, reemplazo/renovación, bombas
fdc/online/lobby.py       salas del futuro online (lógica pura, sin red)
fdc/ui/app.py             ventana, bucle de cuadros, eventos, foco, panel F3, cierre
fdc/ui/screens.py         arranque, menú, controles, leyenda, error, botones retro
fdc/ui/match_screens.py   selección (teclado y mouse), partido (pausa, reinicio, prueba), resultado
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
tools/importar_sprites.py convierte assets/originales/*.webp en los sprites del juego
assets/originales/        sprites originales (uno por personaje, con su botín)
assets/personajes/        cabezas, cuadros del botín y sprites.json (generados por el importador)
docs/ONLINE.md            diseño del modo online (salas, servidor en la NAS, cliente web)
tests/                    pruebas (unittest) y el conductor de la interfaz sin ventana
```

### Gráficos: sprites y estilo retro

- **Personajes.** Salen de tus sprites (`assets/originales/<id>.webp`). `tools/importar_sprites.py`:
  - separa la cabeza del botín con una línea de corte por personaje (definida en el script);
  - los reduce a pixel art nativo: 1 píxel = una celda del dibujo original, con alfa binario y colores limpios;
  - genera los cuadros del botín ya rotados (rotados en alta resolución antes de reducir, para que cada ángulo quede nítido).

  En el juego, la cabeza queda fija y **sólo se mueve el botín**. El botín cuelga de una "cadera" invisible bajo la cabeza: en reposo queda atrás, como en el dibujo original, y al patear barre en arco por delante del mentón. Los sprites miran a la izquierda; para el otro lado se espejan.
- **Todo en píxeles de 2x2.** Estadio (dibujado a 640×360 y agrandado ×2), pelota con rotación, íconos, fuente propia, tablero LED y botones con bisel. Paleta clara: cielo celeste, tribunas pastel, césped a franjas.
- **Cambiar o agregar un sprite.** Reemplazá el `.webp` en `assets/originales/`, ajustá su línea en `CUTS` dentro del importador (con `--depurar` se ve el corte en rojo) y ejecutá:

```bash
.venv/bin/python tools/importar_sprites.py --depurar
```

- **Otros reemplazos** (si existe el archivo, se usa en lugar del generado): `assets/fondos/estadio.png`, `assets/sprites/pelota.png`, `assets/iconos/<poder>.png` y `assets/sonidos/<nombre>.wav` (kick, whoosh, bounce, header, post, goal, whistle, whistle_end, select, confirm, back, power_good, power_bad, power_global, spawn, bomb_tick, explosion, beep, go, blocked, crowd).

### Valores elegidos (ajustables en `fdc/config.py`)

- **Física:** paso fijo de 120 Hz y estados a 60 Hz.
- **Jugador (cabeza + botín):** cabeza de radio 41, alto total 106. Velocidad 340 px/s, aceleración 3400 px/s² y frenado 4600 px/s². Salto de unos 128 px (desde una cabeza, unos 216 px).
- **Pelota flotante:** radio 17, gravedad 850 px/s², resistencia del aire 1,0/s, velocidad máxima 1150 px/s.
- **Patada:** potencia 920 px/s en ángulo alto (sube unos 205 px y pica a unos 440 px), recuperación de 0,32 s.
- **Arco:** 250 px de alto y 112 de profundidad.
- **Partido:** 60 s de tiempo efectivo.
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
- **Sin interpolación:** la interfaz dibuja el último estado sin interpolar, porque no calcula posiciones propias. A veces un cuadro repite o saltea un estado y hay un leve tironeo ocasional.
- **Simulación en Python:** si el equipo está muy cargado y la simulación se atrasa, recupera como máximo 6 pasos por vuelta: el juego se vuelve más lento en lugar de acelerarse de golpe.
- **Sprites:** tienen una sola expresión, así que los festejos, golpes y congelados se muestran con movimiento, saltitos, efectos y tintes, no con caras distintas. Los originales tienen una grilla de píxeles irregular, y al reducirlos algunos detalles finos se simplifican.
- **Audio:** es sintetizado y simple, sin música.
- **Salto aumentado:** con *Salto aumentado* se puede tocar el travesaño saltando desde el piso (es el efecto del poder).
- **Pruebas de interfaz:** usan el driver `dummy` de SDL, así que verifican el flujo y el dibujo pero **no** reemplazan jugar con un teclado real.
- **Online:** todavía no está implementado (ver la sección 12).

### Verificación realizada y pendiente

**Hecho y verificado:**

- Las 66 pruebas automáticas pasan.
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

---

## 12. Preparado para el online (todavía sin red)

El pedido es jugar 1 contra 1 en salas, desde el navegador, en dos casas distintas, con un servidor en la NAS y un dominio propio. Esta versión deja lista la base:

- **`fdc/online/lobby.py` (implementado y probado):**
  - nombre de usuario al entrar;
  - crear sala libre o con contraseña (guardada como hash con sal);
  - lista de salas con el nombre del creador;
  - unirse, con un máximo de 2 personas;
  - elegir personaje (se puede repetir) y confirmar;
  - **asignación automática de lados**, revancha y desconexiones.

  Es lógica pura: recibe un mensaje de una conexión y devuelve qué mandar y a quién. Un servidor WebSocket sólo tiene que enrutar.
- **`fdc/link.py`:** la interfaz depende sólo de `MatchLink`. Hoy lo implementa `SimLink`, con un proceso local. Un `NetLink` por WebSocket lo implementaría igual, sin cambiar pantallas ni dibujo.
- **Simulación y protocolo:** ya sirven para un servidor autoritativo con un proceso de simulación por sala. Los mensajes con partido, `seq`, `eid`, ACK y controles por contadores toleran que la red junte o pierda paquetes.

El diseño completo está en [docs/ONLINE.md](docs/ONLINE.md): arquitectura, catálogo de mensajes, cliente web (pygbag o JavaScript), seguridad y despliegue en la NAS con TLS.
