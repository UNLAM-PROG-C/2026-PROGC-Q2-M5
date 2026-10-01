# Modo online (1 contra 1 en salas) y versión web

Dos personas juegan desde **sus casas**, cada una en su **navegador**, contra un **servidor propio** (la NAS). La versión de escritorio también puede jugar online (*Jugar > Multijugador > Online*), útil para probar.

**La página web trae el juego completo:** el mismo menú que la versión de escritorio, con *Jugar → Mundialito* (contra la computadora), *Multijugador → Local* (dos personas en un teclado) y *Multijugador → Online*, más *Controles* y *Poderes*. Los modos locales corren enteros en el navegador de quien juega, así que no cargan al servidor. Sólo el online usa la NAS.

## Reglas

1. **Nombre de usuario:** al entrar, cada persona escribe uno (de 3 a 16 letras, números o espacios). No hay cuentas ni contraseñas de usuario. Dos personas conectadas no pueden usar el mismo nombre.
2. **Salas:** se puede **crear una sala libre o con contraseña**. La lista muestra el nombre de cada sala, quién la creó, un candado si es privada, cuántos hay (máximo 2) y su estado. Se actualiza sola.
3. **Elegir personaje:** con 2 personas en la sala, cada una elige personaje (pueden repetirlo) y toca **¡LISTO!**. Cuando los dos están listos, el **servidor sortea los lados** y empieza el partido. Al arrancar se muestra "JUGÁS A LA IZQUIERDA" (o derecha).
4. **Partido:** son las mismas reglas que el local: 60 s, los 17 poderes y el **empate vale**. Cada persona juega con **cualquiera de las dos combinaciones de teclas**: A/W/D + Espacio o flechas + P.
5. **Pausa:** la puede pedir cualquiera (`Esc` o **II PAUSA**), sin que el otro tenga que aceptar.
   - **No corta la jugada:** se activa recién **después del próximo gol** (a favor o en contra), cuando la pelota vuelve al centro.
   - **Aviso:** mientras tanto, debajo del marcador se lee, chiquito, "*usuario* pidió la pausa".
   - **Reanudar:** con la pausa activa, el partido sigue cuando **los dos tocan "Estoy listo"** o, si no, **a los 30 s**.
6. **Desconexión:** si a alguien se le corta la conexión, el partido se pausa para los dos.
   - **Aviso:** el rival ve "*usuario* perdió la conexión" con una cuenta de **30 s**.
   - **Si vuelve a tiempo:** el partido sigue. La reconexión es automática y también funciona si se recarga la página.
   - **Si no vuelve:** **gana el que se quedó**, por abandono.
7. **Abandonar:** el botón **ABANDONAR** (con confirmación) da el partido por perdido y saca a esa persona de la sala.
8. **Revancha:** la sala **queda abierta**. *Revancha* usa los mismos personajes y **los lados se sortean de nuevo**. *Cambiar personaje* vuelve a la sala. Si el rival se fue, se puede esperar a otro.

## Arquitectura

```
 Casa A: navegador ──┐                          NAS (Windows)
   (pygbag)          │  https + wss   ┌───────────────────────────────────────────────────┐
                     ├── dominio ────►│ Caddy (TLS, Let's Encrypt) ─► servidor.py :8765    │
 Casa B: navegador ──┘                │                                │                   │
                                      │   proceso SERVIDOR (asyncio, un hilo)              │
                                      │     ├─ por conexión: tarea lectora + escritora     │
                                      │     ├─ Lobby: usuarios y salas (lógica pura)       │
                                      │     ├─ sala 1: puente 60 Hz ◄─colas─► proceso SIM  │
                                      │     └─ sala 2: puente 60 Hz ◄─colas─► proceso SIM  │
                                      └───────────────────────────────────────────────────┘
```

El servidor **sirve la página del juego** (`build/web`) y el **WebSocket `/ws`** en el mismo puerto.

### Dónde está la concurrencia

| Pieza | Mecanismo | Para qué |
|---|---|---|
| Servidor (`fdc/online/server.py`) | **Un bucle `asyncio`** en un solo hilo | Atiende todas las conexiones sin bloquearse. Sólo ese bucle toca el `Lobby` y las sesiones, así que **no hacen falta locks**. |
| Cada conexión | **Una tarea lectora y otra escritora** | La escritora vacía una cola propia. Los estados son **reemplazables** (si el navegador va lento, se manda sólo el último). El resto se entrega en orden y, si se acumulan más de 400, se corta esa conexión. Así un cliente lento no frena a nadie más. |
| Cada sala en juego | **Un proceso de simulación** (`multiprocessing`, *spawn*) | Es **el mismo** de la versión local (`simulation_main`, vía `SimLink`), con sus colas acotadas, ACK, número de partido, watchdog y `Event` de cierre. Una sala trabada no afecta a las otras, y cada una puede usar otro núcleo. |
| Puente de la sala (`RoomRunner`) | **Tarea `asyncio` a 60 Hz** | Junta los controles de los dos navegadores y los manda al proceso. Reenvía los eventos y unos **30 estados por segundo**, y lleva la pausa pedida, los "listo", el plazo de 30 s y las desconexiones. |
| Lanzar o cerrar un proceso | **Hilo del ejecutor** (`run_in_executor`) | `Process.start()` y el cierre coordinado pueden tardar: se hacen fuera del bucle para no congelar a los demás. |
| Cliente de escritorio (`ThreadTransport`) | **Hilo lector + cola acotada** | El hilo queda bloqueado en la red (no gasta CPU). La interfaz vacía la cola sin bloquear en cada cuadro. |
| Cliente web (`BrowserTransport`) | **Un solo hilo** (el navegador no tiene hilos ni procesos) | El WebSocket de JavaScript deja lo que llega en un arreglo, y Python lo retira una vez por cuadro. El bucle es asíncrono: cada cuadro le devuelve el control al navegador. |

**Modos locales en el navegador** (`fdc/sim/inline.py`). En el navegador no se pueden lanzar procesos, así que el Mundialito y el multijugador local usan `InlineLink`:

- **Mismo contrato:** el que `SimLink`, con órdenes con ACK, fotos de controles con contadores y estados con número de partido.
- **Mismo núcleo:** la simulación es la misma (`fdc/sim/core.py`).
- **Dentro de la página:** cada cuadro aplica las órdenes y la última foto de controles, y avanza la física con paso fijo de 1/120 s hasta el momento actual. La física tarda unos 8 µs por paso, así que sobra margen.

**Teclas en el navegador** (`fdc/ui/browser.py`). En Chrome, `Esc` "detiene la carga" de la página y eso congelaba el WebSocket: el partido dejaba de actualizarse justo al pedir la pausa. Ahora la página anula la acción del navegador para `Esc`, `F3` (Buscar), `Tab` (saca el foco) y las flechas (desplazan la página). El evento igual llega al juego.

**Por qué el servidor es la autoridad.** La simulación del servidor decide todo: posiciones, goles, poderes y azar. El navegador sólo manda **controles** y **pedidos** (pausa, listo, abandonar). El servidor sabe qué lado tiene cada conexión, así que nadie puede mover al otro jugador ni hacer trampa con la física.

### Mensajes (JSON por WebSocket, ver `fdc/online/wire.py`)

Por la red va **JSON**, **nunca `pickle`**, porque `pickle` permite ejecutar código ajeno. El servidor valida cada mensaje: que sea JSON, su tipo, sus campos y que los contadores sean enteros no negativos. También pone un tamaño máximo de 2 KB y un máximo de 150 mensajes por segundo por conexión.

| Cliente → servidor | Respuesta o efecto |
|---|---|
| `hello {username, token?}` | `welcome {username, token, restored}` + `rooms`, o `error` (`nombre_invalido`, `nombre_en_uso`). Con el `token` se **recupera la sesión** (sala y partido) tras un corte. |
| `list_rooms`, `create_room {name, password?}`, `join_room {room, password?}`, `leave_room` | `rooms` (lista) o `room` (detalle de la sala). Errores: `sala_llena`, `clave_incorrecta`, `sala_inexistente`, `demasiadas_salas`. |
| `choose_character {character}`, `ready {ready}` | `room` a los dos. Con ambos listos: `match_start {match, players, you}` a cada uno. |
| `input {p: [izq, der, saltos, patadas]}` | Foto de controles **reemplazable**. Saltos y patadas viajan como **contadores acumulados**, así que no se pierde ninguna pulsación aunque se pierdan fotos. Se manda sólo cuando cambia, más un latido cada 0,25 s. |
| `pause_request` / `pause_ready` | `pause_info {status: pedida/activa/ninguna, by_name, left, ready}` a los dos. |
| `abandon` | `match_over {reason: "abandono", winner, by_name}`; quien abandona vuelve a la lista. |
| `ping {t}` | `pong {t}`: la latencia que se ve arriba a la derecha y en F3. |

Del servidor también llegan:

- `state`: la foto del partido, con `match` y `seq` para descartar las viejas;
- `ev {e}`: un evento del partido (gol, poder, rebote...), con `eid` para no procesarlo dos veces;
- `opponent {connected, left}`: si el rival perdió la conexión y cuánto le queda para volver;
- `match_over {reason: "tiempo" | "abandono" | "error"}`: el final del partido.

### Latencia

- **Suavizado:** el navegador dibuja entre las dos últimas fotos (`fdc/online/interp.py`), así el movimiento se ve suave aunque lleguen 30 por segundo. Es sólo presentación.
- **Demora:** los controles tardan lo que tarda la red (entre dos casas, normalmente 20 a 80 ms). No hay predicción del lado del cliente: es lo más simple y justo, porque nadie ve una versión distinta del partido. Ver "Limitaciones" en el README.

## Probarlo en la computadora

```bash
.venv/bin/python -m pip install -r requirements-online.txt   # una sola vez: websockets y pygbag
.venv/bin/python tools/construir_web.py                      # compila el cliente web en build/web
.venv/bin/python servidor.py                                  # http://127.0.0.1:8765
```

- **Navegador:** abrí <http://127.0.0.1:8765> en **dos ventanas** (o dos navegadores), elegí nombres distintos, creá una sala con una y unite con la otra. La primera vez hay que hacer clic en la página para que arranque, porque el navegador exige un clic para habilitar el sonido.
- **`localhost`:** si se escribe `localhost:8765`, el servidor redirige a `127.0.0.1:8765`. pygbag trata a las páginas servidas desde `localhost:8...` como su propio servidor de desarrollo y busca sus paquetes en `localhost:8000`, y ahí el juego no arranca.
- **Escritorio:** `main.py` también juega online. Por defecto usa `ws://localhost:8765/ws`; se cambia con `--servidor URL` o con la variable `FDC_SERVIDOR`.
- **Opciones del servidor:**
  - `--puerto`;
  - `--host`: 127.0.0.1 para aceptar sólo conexiones locales;
  - `--duracion S`: partidos cortos para probar;
  - `--gracia S`: los segundos para volver tras un corte.
- **Estado y registros:** <http://127.0.0.1:8765/estado> muestra cuántas salas y conexiones hay. El registro queda en `logs/servidor.log`.

## Ponerlo en la NAS (Windows)

### 1. Instalar

1. Instalá **Python 3.13** desde python.org y marcá *Add python.exe to PATH*.
2. Copiá la carpeta del proyecto, o cloná el repo con `git clone`.
3. En una terminal (PowerShell), dentro de la carpeta:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-online.txt
.venv\Scripts\python tools\construir_web.py
.venv\Scripts\python servidor.py
```

- **Dependencias:** el servidor sólo necesita `websockets` (no carga pygame). `pygame` y `pygbag` hacen falta únicamente para compilar el cliente web. También se puede compilar en la Mac y copiar la carpeta `build\web`.
- **Python en el navegador:** la página descarga el intérprete (WebAssembly) del CDN de pygame-web (`pygame-web.github.io`), así que los jugadores necesitan internet. La NAS sólo sirve el juego (unos 240 KB) y el WebSocket.
- **Prueba en la red de tu casa:** desde otra compu, abrí `http://IP-DE-LA-NAS:8765`. Si no abre, permití Python en el Firewall de Windows (puerto 8765, red privada).

### 2. Que arranque solo (sin dejar una sesión abierta)

Con el **Programador de tareas** de Windows:

1. Creá una tarea con el desencadenador **Al iniciar el sistema**.
2. En *Acción*, poné el programa `C:\ruta\al\proyecto\.venv\Scripts\python.exe`, los argumentos `servidor.py --host 127.0.0.1` y *Iniciar en* `C:\ruta\al\proyecto`.
3. En *General*, marcá **Ejecutar tanto si el usuario inició sesión como si no**.
4. En *Configuración*, elegí **Si la tarea no se ejecuta, reiniciar cada 1 minuto**.

Con `--host 127.0.0.1` el juego sólo acepta conexiones de la propia NAS: desde afuera se entra únicamente por Caddy, con HTTPS.

### 3. Dominio y HTTPS

El navegador exige **HTTPS/WSS** fuera de la red local. Lo más simple es **Caddy**: un solo `.exe` que saca y renueva los certificados de Let's Encrypt automáticamente y deja pasar el WebSocket sin configuración extra.

1. **DNS:** en tu proveedor del dominio, creá un registro **A** (por ejemplo, `futbol.tudominio.com`) apuntando a la **IP pública** de tu casa. Si tu IP cambia, usá **DNS dinámico**: muchos proveedores y routers lo traen, y si no, DuckDNS o similar.
2. **Router:** redirigí los puertos **80 y 443** (TCP) a la IP de la NAS. Conviene fijarle una IP a la NAS en el router (reserva DHCP).
3. **Caddy:** bajá `caddy.exe` de caddyserver.com y creá un archivo `Caddyfile` al lado:

   ```
   futbol.tudominio.com {
       reverse_proxy 127.0.0.1:8765
   }
   ```

   Probalo con `caddy run`. Para que arranque solo, usá el mismo Programador de tareas, con el programa `caddy.exe` y los argumentos `run --config Caddyfile`.
4. **Firewall de Windows:** permití la entrada en los puertos 80 y 443 a `caddy.exe`.
5. **Listo:** las dos casas entran a `https://futbol.tudominio.com`.

**Si tu proveedor usa CGNAT** (la IP "WAN" del router no coincide con la que muestra *¿cuál es mi IP?*), abrir puertos no funciona. Hay dos salidas:

- pedirle al proveedor una IP pública;
- usar **Cloudflare Tunnel** (`cloudflared` para Windows, gratuito). El túnel sale desde la NAS hacia Cloudflare, así que no hace falta abrir puertos. Soporta WebSocket y el dominio tiene que estar en Cloudflare. En ese caso Caddy no hace falta: el túnel apunta a `http://127.0.0.1:8765`.

### 4. Actualizar

```powershell
git pull
.venv\Scripts\python tools\construir_web.py
```

Después reiniciá la tarea del servidor. Las salas viven en memoria: reiniciar el servidor las cierra.

### Docker (opcional)

Si preferís un contenedor (Docker Desktop con WSL2 en Windows): imagen `python:3.13-slim`, `pip install websockets`, copiar el proyecto y la carpeta `build/web`, `CMD ["python", "servidor.py"]` y exponer el 8765. Con la tarea programada alcanza; Docker no es necesario.
