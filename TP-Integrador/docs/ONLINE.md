# Modo online (1 contra 1 en salas): diseño y preparación

Esta versión es **local** (dos personas, un teclado). El online **no está implementado todavía**, pero el código ya está organizado para agregarlo sin rehacer el juego. Este documento explica qué quedó preparado y cómo seguir.

## Reglas acordadas

1. Al entrar, cada persona escribe su **nombre de usuario**. No hay cuentas.
2. Se puede **crear una sala libre o con contraseña**.
3. Todos ven la **lista de salas** con el nombre de quien la creó, y pueden unirse. Si la sala tiene contraseña, hay que escribirla.
4. Una sala es siempre **1 contra 1**.
5. Con 2 personas en la sala, cada una **elige su personaje** (pueden repetirlo) y confirma.
6. El sistema **asigna los lados automáticamente** (izquierda o derecha) y empieza el partido.
7. Se juega desde un **navegador**, en dos casas distintas, contra un servidor propio (NAS) con dominio.

## Qué ya está preparado en el código

| Pieza | Dónde | Por qué sirve para el online |
|---|---|---|
| Simulación pura y autoritativa | `fdc/sim/match.py` | No sabe de ventanas ni de colas: recibe controles, avanza a paso fijo y devuelve estados y eventos. El servidor puede correr **una por sala** sin cambios. |
| Proceso de simulación | `fdc/sim/process.py` | El mismo patrón (un proceso por partido, con colas) sirve en el servidor: **un proceso por sala en juego**. Así cada sala usa su propio núcleo de la NAS y una sala colgada no afecta a las demás. |
| Protocolo por mensajes | `fdc/protocol.py` | Controles, órdenes, estados y eventos ya son diccionarios simples. Llevan identificador de partido (`match`), número de actualización (`seq`), identificador de evento (`eid`) y confirmaciones (`ack`). Se pueden mandar como JSON por WebSocket. |
| Controles con contadores | `PressCounter` | Por red se pierden o se juntan paquetes. Como saltos y patadas viajan como contadores acumulados, la última foto que llega alcanza para no perder pulsaciones. |
| Contrato de enlace | `fdc/link.py` (`MatchLink`) | Las pantallas sólo usan `start`, `send_command`, `send_input`, `poll`, `check_health` y `stop`. Hoy lo implementa `SimLink` (proceso local). Un `NetLink` (WebSocket) implementaría lo mismo y el resto de la interfaz no cambia. |
| **Salas (ya implementado y probado)** | `fdc/online/lobby.py`, `tests/test_lobby.py` | Nombre de usuario, crear sala libre o con contraseña, lista de salas con su creador, unirse, límite de 2, elegir personaje, confirmar, lados al azar, revancha y desconexiones. Es lógica pura: recibe un mensaje de una conexión y devuelve qué mandar y a quién. |

### Mensajes de las salas (`Lobby.handle(conexión, mensaje)`)

| Cliente → servidor | Respuesta o aviso |
|---|---|
| `{"type": "hello", "username": "Ale"}` | `welcome` y `rooms`, o `error` (`nombre_invalido` o `nombre_en_uso`) |
| `{"type": "list_rooms"}` | `rooms`: sala, nombre, creador, si es privada, jugadores y estado. Nunca incluye la contraseña. |
| `{"type": "create_room", "name": "Picadito", "password": "opcional"}` | `room` a quien la creó, más `rooms` actualizado a quienes miran la lista |
| `{"type": "join_room", "room": 3, "password": "..."}` | `room` a ambos, o `error` (`sala_llena`, `clave_incorrecta` o `sala_inexistente`) |
| `{"type": "choose_character", "character": "messi"}` | `room` actualizado a ambos |
| `{"type": "ready"}` | Cuando confirman los dos: `match_start` a cada uno, con `players` (lado, usuario, personaje) y `you` (su lado) |
| `{"type": "leave_room"}` o conexión cortada | `opponent_left` a quien queda, que pasa a ser el dueño de la sala |

Las contraseñas de sala se guardan como hash PBKDF2 con sal y se comparan en tiempo constante. No son cuentas de usuario: sólo protegen la entrada a la sala.

## Arquitectura propuesta

```
 Casa A: navegador ─┐                        NAS (Docker)
                    │   https / wss   ┌────────────────────────────────────────────┐
                    ├──── dominio ───►│ proxy inverso (TLS, Let's Encrypt)         │
 Casa B: navegador ─┘                 │   /     -> archivos del cliente web        │
                                      │   /ws   -> servidor del juego (asyncio)    │
                                      │             ├─ Lobby (salas)               │
                                      │             ├─ sala 1 -> proceso Match     │
                                      │             └─ sala 2 -> proceso Match     │
                                      └────────────────────────────────────────────┘
```

**Servidor.** Python con `asyncio` y la librería `websockets` (o `aiohttp`), en un contenedor Docker en la NAS.
- **Conexiones:** un bucle de eventos las atiende y pasa cada mensaje a `Lobby.handle`.
- **Partido:** con el `match_start`, lanza el proceso de simulación de esa sala (`simulation_main`, con las mismas colas).
- **Controles:** los recibe de cada navegador (`input`). Como el servidor sabe qué lado tiene cada conexión, los traduce al jugador 0 o 1.
- **Estados y eventos:** los reenvía a los dos navegadores. Los estados se pueden bajar a unos 30 por segundo para ahorrar ancho de banda; la física sigue a 120 Hz.
- **Cierre:** cuando llega `match_end`, llama a `Lobby.finish_match` (revancha) y cierra el proceso de la sala con el mismo cierre coordinado que ya usa `SimLink.stop()`.

**Cliente web.** Hay dos caminos:
1. **pygbag** (pygame compilado a WebAssembly). Reutiliza las pantallas, los sprites y el dibujo actuales. Hay que:
   - hacer asíncrono el bucle principal (`await asyncio.sleep(0)` en cada cuadro);
   - reemplazar `SimLink` por un `NetLink` que use el WebSocket del navegador;
   - agregar pantallas nuevas de nombre, lista de salas y sala.

   En el navegador no hay `multiprocessing`, pero tampoco hace falta, porque la simulación corre en el servidor.
2. **Cliente JavaScript con Canvas.** Es más trabajo de interfaz, pero no depende de pygbag. Usaría los mismos sprites (`assets/personajes/*.png`) y los mismos mensajes JSON.

Recomendación: empezar con un prototipo en pygbag, porque se aprovecha casi toda la interfaz.

**Cuidados de red**
- **Nunca usar `pickle` por la red:** permite ejecutar código ajeno. Por la red va JSON, y el servidor valida cada mensaje.
- **Autoridad del servidor:** decide todo (posiciones, goles, poderes, azar), igual que hoy la simulación. Así un cliente no puede hacer trampa.
- **Latencia:** entre dos casas es normal tener entre 30 y 100 ms. Conviene que el cliente web **interpole** entre los dos últimos estados (unos 100 ms de colchón). Es sólo presentación y no cambia la regla de que el servidor decide.
- **Pausa:** en el online no conviene la pausa libre. Se puede reemplazar por "pedir pausa y que el rival acepte", o quitarla.
- **Desconexiones:** esperar unos 10 s a que la persona vuelva a entrar. Si no vuelve, dar el partido por terminado. El `watchdog` de controles que ya existe detecta cuando dejan de llegar controles.

**Puesta en marcha en la NAS**
- **Contenedor:** Docker con `python:3.13-slim`, el servidor y los archivos del cliente web, con reinicio automático.
- **Proxy inverso:** puede ser el de la propia NAS, Nginx Proxy Manager, Caddy o Traefik. Debe tener certificado de Let's Encrypt para el dominio y soportar la actualización a WebSocket en `/ws`.
- **Router:** redirigir el puerto 443 a la NAS. Si la IP pública cambia, usar DNS dinámico.
- **Registros y límites:** mantener los registros por proceso (como hoy) y agregar límites de mensajes por conexión y de salas por IP.

## Próximos pasos sugeridos

1. Servidor WebSocket mínimo que use `Lobby`, con pruebas que simulen conexiones.
2. Ejecutor de sala: puente entre la conexión y el proceso `simulation_main` de cada sala, con el lado asignado a cada conexión.
3. `NetLink` en el cliente, más las pantallas de usuario, lista de salas (con candado para las privadas) y sala (personajes y lado asignado).
4. Versión web con pygbag y despliegue en la NAS con el dominio.
