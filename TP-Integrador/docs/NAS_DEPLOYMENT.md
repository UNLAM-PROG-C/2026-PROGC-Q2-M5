# Migrar a la NAS y jugar online desde dos redes distintas

Guía paso a paso para dejar **Futbol De Cabeza** funcionando en la NAS (Windows) y que se pueda jugar desde dos casas distintas, o mostrárselo a los profesores con una dirección de internet.

> Todo está pensado para Windows (rutas, procesos con `spawn`), pero **todavía no se probó en un Windows real**. Si algo falla, el error queda en `C:\FutbolDeCabeza\logs\server.log`.

---

## 0. Qué camino elegir

Para que alguien de otra red entre al juego hay cuatro caminos. La parte 1 (preparar la NAS) y la parte 2 (arranque automático) son iguales para todos.

| Camino | Costo | Dirección que usan los jugadores | ¿Abrir puertos en el router? | ¿Anda con CGNAT? | HTTPS | Para qué conviene |
|---|---|---|---|---|---|---|
| **A. Abrir un puerto** | Gratis | `ws://TU-IP-PÚBLICA:8765/ws` o `ws://algo.duckdns.org:8765/ws` | Sí (8765) | No | No | Probar ya entre dos casas |
| **B. Dominio + Cloudflare Tunnel** ⭐ | El dominio (unos USD 10 por año) | `wss://futbol.tudominio.com/ws` | **No** | **Sí** | Sí | Dejarlo andando y mostrarlo a los profes |
| **C. Dominio + puertos 80/443 + Caddy** | El dominio, o gratis con DuckDNS | `wss://futbol.tudominio.com/ws` | Sí (80 y 443) | No | Sí | Si no querés depender de Cloudflare |
| **D. Túnel de prueba sin dominio** | Gratis | `wss://palabras-al-azar.trycloudflare.com/ws` (cambia cada vez) | No | Sí | Sí | Una demo rápida |

**Recomendación:** **A** para probar hoy mismo entre dos casas, y **B** para la versión final.
- **B no abre ningún puerto de tu casa** y funciona aunque tu proveedor use CGNAT.
- **B tiene HTTPS.** Usa el puerto 443, así que anda también en redes que bloquean puertos raros como el 8765. Las de una universidad o un trabajo suelen hacerlo, y eso importa para la defensa.

**Qué es CGNAT:** muchos proveedores de internet comparten una misma IP pública entre varios clientes. En ese caso abrir un puerto en tu router no sirve, porque desde internet no se llega a tu casa. En el paso 3.1 está cómo saber si te pasa.

---

## 1. Preparar la NAS (una sola vez)

### 1.1 Instalar Python 3.13

1. Bajalo de <https://www.python.org/downloads/windows/> (*Windows installer 64-bit* de la versión 3.13).
2. En el instalador, **marcá "Add python.exe to PATH"** y dejá marcado el *py launcher*.
3. Abrí **PowerShell** y verificá:

```powershell
py -3.13 --version
```

Tiene que decir `Python 3.13.x`.

### 1.2 Instalar Git

Bajalo de <https://git-scm.com/download/win> e instalalo con las opciones por defecto. Incluye *Git Credential Manager*, que sirve para entrar a GitHub.

### 1.3 Bajar el proyecto

El repositorio es privado: al clonar se abre el navegador para que entres con **tu** cuenta de GitHub.

```powershell
cd C:\
git clone https://github.com/AlanGiardelli/Cabezones.git FutbolDeCabeza
cd C:\FutbolDeCabeza
```

En el resto de la guía se usa la carpeta `C:\FutbolDeCabeza`. Si elegís otra, cambiala en todos los comandos.

### 1.4 Entorno de Python y dependencias

```powershell
cd C:\FutbolDeCabeza
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r tools/requirements/requirements-online.txt
```

- **Servidor:** necesita sólo `websockets`.
### 1.5 Probarlo en la misma NAS

```powershell
.venv\Scripts\python -m deploy.server
```

1. Al arrancar, el servidor muestra las direcciones donde escucha, por ejemplo `http://127.0.0.1:8765` y la de tu red local (`http://192.168.0.50:8765`).
2. Si Windows pregunta si Python puede aceptar conexiones, elegí **Redes privadas** y *Permitir*.
3. Abrí <http://127.0.0.1:8765/status> para ver el panel. Para jugar, usá el cliente de escritorio con `--server ws://127.0.0.1:8765/ws`.
4. Para cortarlo: `Ctrl + C` en la ventana de PowerShell.

### 1.6 Probarlo desde otra compu de tu casa

Con el servidor andando, conectá el cliente de otra compu del mismo wifi a `ws://192.168.0.50:8765/ws` desde *Jugar → Multijugador → Online*. Si no conecta, falta la regla del firewall (paso 1.9).

### 1.7 Darle a la NAS una IP fija en tu red

El router tiene que mandar siempre al mismo equipo, así que la NAS no puede cambiar de IP.

1. En la NAS: `ipconfig /all`. Anotá la **Dirección IPv4** (por ejemplo `192.168.0.50`) y la **Dirección física** (MAC) del adaptador que usás.
2. Entrá al router. Suele ser <http://192.168.0.1> o <http://192.168.1.1>, y el usuario y la clave están en una etiqueta del router.
3. Buscá **"Reserva DHCP"**, **"IP estática"** o **"Address Reservation"**. Asociá esa MAC con esa IP.

### 1.8 Que la NAS no se suspenda

*Configuración → Sistema → Inicio/apagado y suspensión → Suspender: **Nunca*** (al menos con el equipo enchufado). También se puede desde PowerShell:

```powershell
powercfg /change standby-timeout-ac 0
```

### 1.9 Firewall de Windows (sólo para el camino A y para jugar dentro de tu red)

En PowerShell **como administrador**:

```powershell
New-NetFirewallRule -DisplayName "Futbol De Cabeza" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

Fijate también que la red de la NAS esté como **Privada**: *Configuración → Red e Internet → (tu conexión) → Propiedades → Tipo de perfil de red: Privada*.

En los caminos **B, C y D** esta regla no hace falta para jugar desde afuera, porque el túnel o Caddy se conectan al juego desde la misma NAS. Sirve sólo para jugar dentro de tu casa con la IP local.

---

## 2. Que el servidor arranque solo (Programador de tareas)

Así el juego vuelve a andar después de un corte de luz o de una actualización de Windows, sin que nadie inicie sesión.

1. Abrí el **Programador de tareas** y elegí **Crear tarea…** (no "Crear tarea básica").
2. **General:**
   - nombre: `Futbol De Cabeza - servidor`;
   - marcá **"Ejecutar tanto si el usuario inició sesión como si no"** (Windows te pide la contraseña de tu usuario; la escribís vos).
3. **Desencadenadores → Nuevo:**
   - *Iniciar la tarea:* **Al iniciar el sistema**;
   - opcional: *Retrasar la tarea durante 1 minuto*, para que la red ya esté lista.
4. **Acciones → Nueva → Iniciar un programa:**
   - *Programa:* `C:\FutbolDeCabeza\.venv\Scripts\python.exe`
   - *Agregar argumentos:*
     - camino A: `-m deploy.server`
     - caminos B, C y D: `-m deploy.server --host 127.0.0.1` (así el juego sólo acepta conexiones de la propia NAS y desde afuera se entra únicamente por el túnel o por Caddy)
   - *Iniciar en:* `C:\FutbolDeCabeza`
5. **Condiciones:** desmarcá *"Iniciar la tarea sólo si el equipo está conectado a la corriente alterna"* si la NAS es una notebook.
6. **Configuración:**
   - marcá **"Si la tarea no se ejecuta, reiniciar cada: 1 minuto"**, con 999 intentos;
   - **desmarcá "Detener la tarea si se ejecuta durante más de: 3 días"**. Si no, Windows corta el servidor a los 3 días.
7. Aceptá. Reiniciá la NAS y comprobá que <http://127.0.0.1:8765> abre sin haber ejecutado nada a mano.

**Para detenerlo o reiniciarlo:** Programador de tareas → la tarea → *Finalizar* y después *Ejecutar*.

**Registros:** `C:\FutbolDeCabeza\logs\server.log`. El archivo crece con el tiempo; se puede borrar con el servidor detenido.

### Contraseña del panel del servidor (opcional)

`/status` (vista pública, sin nombres) anda siempre. Para habilitar `/status/full`, que muestra los jugadores y el registro de procesos, definí la contraseña. En PowerShell **como administrador**:

```powershell
setx /M FDC_PANEL_PASSWORD "una-clave-larga-que-elijas"
```

Después **reiniciá la NAS**, para que la tarea vea la variable. La otra forma es agregar `--panel-password una-clave` a los argumentos de la tarea, pero así la clave queda a la vista en el Programador de tareas.

---

## 3. Camino A: abrir un puerto en el router

### 3.1 ¿Tenés IP pública o CGNAT?

1. En el router, buscá la **IP de WAN / IP de Internet** (está en la página de estado).
2. Desde cualquier equipo de tu casa, entrá a <https://ifconfig.me>. Muestra tu IP pública.
3. Compará:
   - **Son iguales:** tenés IP pública. Seguí con 3.2.
   - **Son distintas**, o la del router empieza con `100.64.` a `100.127.`, `10.`, `172.16.` a `172.31.` o `192.168.`: estás detrás de **CGNAT** (o de otro router). Abrir puertos **no va a funcionar**. Pedile al proveedor una IP pública (a veces es gratis y a veces se paga) o usá los caminos **B** o **D**.

### 3.2 Redirigir el puerto

En el router, buscá **"Reenvío de puertos"**, **"Port Forwarding"**, **"Servidor virtual"**, **"NAT"** o **"Aplicaciones"**. El nombre cambia según el modelo. Creá una regla:

| Campo | Valor |
|---|---|
| Protocolo | TCP |
| Puerto externo | 8765 |
| IP interna / destino | la IP fija de la NAS (paso 1.7), por ejemplo `192.168.0.50` |
| Puerto interno | 8765 |

Guardá. Verificá también la regla del firewall del paso 1.9.

### 3.3 Probar desde otra red

> **Importante:** probalo desde **afuera** de tu casa. Muchos routers no dejan entrar a tu propia IP pública desde adentro (falta "NAT loopback"). Desde adentro puede no abrir aunque esté todo bien.

Desde una compu en otra red (por ejemplo, conectada al hotspot del celular), configurá el cliente con `ws://TU-IP-PÚBLICA:8765/ws` y entrá al online.

### 3.4 Un nombre fijo gratis (porque la IP de tu casa cambia)

La IP pública de una casa suele cambiar cada tanto. Para no pasar una dirección nueva cada vez:

1. Entrá a <https://www.duckdns.org> con tu cuenta de Google o GitHub. Creá un subdominio (por ejemplo `futbolcabeza`, que queda `futbolcabeza.duckdns.org`) y copiá el **token** que te muestra. Es secreto: no lo compartas ni lo subas al repositorio.
2. En la NAS, creá **otra tarea** en el Programador de tareas que lo mantenga al día:
   - desencadenador: *Al iniciar el sistema*, con **repetir cada 5 minutos** por tiempo indefinido;
   - acción, *Programa:* `powershell.exe`;
   - *Argumentos* (con tu subdominio y tu token):

     ```
     -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://www.duckdns.org/update?domains=futbolcabeza&token=TU-TOKEN&ip=' | Out-Null"
     ```

3. Los jugadores configuran `ws://futbolcabeza.duckdns.org:8765/ws` en el cliente.

### 3.5 Limitaciones del camino A

- **Sin WSS:** la contraseña de una sala viaja sin cifrar. Para un TP alcanza, pero no uses una contraseña que uses en otro lado.
- **Puertos raros bloqueados:** algunas redes (universidad, trabajo, algunos wifi públicos) no dejan conectarse al puerto 8765. Para mostrarlo en la facultad conviene el camino **B**.
- **Tu IP queda a la vista:** quien entra ve la IP de tu casa.

---

## 4. Camino B: dominio comprado + Cloudflare Tunnel (recomendado)

La NAS abre una conexión **hacia** Cloudflare y los jugadores entran por Cloudflare con HTTPS. No se abre ningún puerto en el router, no importa si tenés CGNAT y tu IP no queda expuesta.

### 4.1 Comprar el dominio

- **Cloudflare Registrar** (<https://www.cloudflare.com/products/registrar/>): cobra el precio de costo y el dominio ya queda en Cloudflare. Es lo más simple.
- **Otro registrador** (Porkbun, Namecheap, etc.): después hay que pasar el dominio a Cloudflare (paso 4.2).
- **`.com.ar` en NIC Argentina** (<https://nic.ar>): es barato, pero se hace con clave fiscal. Después hay que cambiar las "delegaciones" a las de Cloudflare.

### 4.2 Poner el dominio en Cloudflare (si no lo compraste ahí)

1. Creá una cuenta en <https://dash.cloudflare.com> y elegí **Agregar un dominio** con el plan **Free**.
2. Cloudflare te da **dos nameservers** (algo como `ana.ns.cloudflare.com`).
3. En el sitio donde compraste el dominio, reemplazá los nameservers (o "delegaciones" en NIC.ar) por esos dos.
4. Esperá a que Cloudflare marque el dominio como **Activo**. Puede tardar de minutos a unas horas.

### 4.3 Crear el túnel

Los nombres de los menús de Cloudflare cambian seguido. Si no encontrás algo, buscá "Tunnels" en el buscador del panel.

1. En el panel de Cloudflare: **Networking → Tunnels → Create a tunnel**. Elegí el tipo **Cloudflared** y ponele un nombre, por ejemplo `futbol-nas`.
2. Elegí **Windows**. Cloudflare muestra:
   - un enlace para bajar e instalar `cloudflared`;
   - un comando parecido a `cloudflared.exe service install <TOKEN-LARGO>`.

   Instalá `cloudflared` y ejecutá ese comando en PowerShell **como administrador**. Así `cloudflared` queda instalado como **servicio de Windows** y arranca solo con la NAS. El token es secreto.
3. Cuando el túnel aparezca como **Healthy / Conectado**, entrá a su pestaña **Routes → Add route → Published application** (en versiones anteriores del panel se llamaba *Public hostname*) y completá:

| Campo | Valor |
|---|---|
| Subdomain | `futbol` |
| Domain | `tudominio.com` |
| Service URL | `http://127.0.0.1:8765` (si pide el tipo aparte: `HTTP` y `127.0.0.1:8765`) |

### 4.4 Ajustar el servidor

En la tarea del paso 2, los argumentos tienen que ser `-m deploy.server --host 127.0.0.1`. No hace falta tocar el router ni el firewall.

### 4.5 WebSockets activados

El juego usa WebSocket para el online. En Cloudflare, dentro del dominio: **Network → WebSockets: On**. Viene activado por defecto.

### 4.6 Probar

Desde otra red conectá el cliente de escritorio a `wss://futbol.tudominio.com/ws`. El panel queda en `https://futbol.tudominio.com/status`.

---

## 5. Camino C: dominio + puertos 80/443 + Caddy

Para esto tenés que tener IP pública (paso 3.1). Caddy saca y renueva solo el certificado HTTPS (Let's Encrypt) y deja pasar el WebSocket sin configuración extra. También funciona con un nombre gratis de DuckDNS (paso 3.4) en lugar de un dominio comprado.

1. **DNS:** creá un registro **A** `futbol.tudominio.com` que apunte a tu IP pública. Si el dominio está en Cloudflare, dejalo en **"Solo DNS"** (nube gris). Si tu IP cambia, usá DNS dinámico: DuckDNS, o lo que ofrezca tu registrador o tu router.
2. **Router:** redirigí **TCP 80 → NAS:80** y **TCP 443 → NAS:443**, igual que en 3.2.
3. **Caddy:** bajá la versión de Windows (amd64) de <https://caddyserver.com/download>. Guardala como `C:\Caddy\caddy.exe` y creá el archivo `C:\Caddy\Caddyfile` (sin extensión) con:

   ```
   futbol.tudominio.com {
       reverse_proxy 127.0.0.1:8765
   }
   ```

4. **Firewall** (PowerShell como administrador):

   ```powershell
   New-NetFirewallRule -DisplayName "Caddy HTTP/HTTPS" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow
   ```

5. **Probar a mano:** `cd C:\Caddy` y después `.\caddy.exe run`. La primera vez saca el certificado; para eso los puertos 80 y 443 tienen que llegar a la NAS desde internet.
6. **Arranque automático:** otra tarea en el Programador de tareas, igual que la del paso 2:
   - *Programa:* `C:\Caddy\caddy.exe`
   - *Argumentos:* `run --config C:\Caddy\Caddyfile`
   - *Iniciar en:* `C:\Caddy`
7. **Servidor del juego:** con `-m deploy.server --host 127.0.0.1` (paso 2).
8. **Probar** desde afuera con el cliente: `wss://futbol.tudominio.com/ws`.

Algunos proveedores bloquean el puerto 80 entrante. Si Caddy no consigue el certificado, revisá eso o pasate al camino B.

---

## 6. Camino D: prueba rápida sin dominio

Para una demo de un rato, sin cuenta y sin tocar el router:

1. Instalá `cloudflared`, por ejemplo con `winget install --id Cloudflare.cloudflared` o desde la página de Cloudflare.
2. Con el servidor del juego andando, ejecutá:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8765
   ```

3. A los segundos muestra una dirección `https://algo-al-azar.trycloudflare.com`. Para jugar, pasales `wss://algo-al-azar.trycloudflare.com/ws`.

Limitaciones:
- **Dura lo que la ventana:** anda mientras esa ventana esté abierta.
- **Dirección nueva cada vez:** cambia en cada arranque.
- **Sólo para pruebas:** Cloudflare no garantiza que esté disponible.

---

## 7. Comprobar que se juega entre dos redes

1. **En la NAS:** <http://127.0.0.1:8765/status> muestra el panel.
2. **Desde otra red** (celular con datos y wifi apagado): abrí `/status` en la dirección pública (camino A, B, C o D) como prueba HTTP.
3. **Dos compus en redes distintas** (por ejemplo, una en tu casa y otra con el celular como hotspot):
   1. las dos abren el cliente de escritorio, configuran el mismo servidor `ws://…/ws` o `wss://…/ws` y eligen su nombre;
   2. una crea una sala desde *Jugar → Multijugador → Online*;
   3. la otra se une, eligen personaje, ponen "listo" y juegan.
4. **Panel:** `.../status` muestra 2 conexiones y **un proceso de simulación para esa sala**, con su pid. Con F3 durante el partido se ve ese mismo pid y el tiempo de los ACK.
5. **Latencia:** la que muestra el cartelito de arriba a la derecha (entre dos casas, unos 20 a 80 ms) dice cómo anda la conexión.

---

## 8. Actualizar el juego en la NAS

```powershell
cd C:\FutbolDeCabeza
git pull
.venv\Scripts\python -m pip install -r tools/requirements/requirements-online.txt
```

Después reiniciá la tarea del servidor (Programador de tareas → *Finalizar* y *Ejecutar*).
- **Salas:** viven en memoria, así que reiniciar el servidor cierra las que estaban abiertas.

---

## 9. Problemas comunes

| Qué pasa | Por qué suele ser | Qué hacer |
|---|---|---|
| Desde afuera no abre, pero en casa sí | CGNAT, el puerto no está redirigido a la IP correcta, falta la regla del firewall, o estás probando con tu IP pública desde adentro | Paso 3.1, revisá la regla del router y la del firewall (1.9), y probá con datos móviles |
| El cliente queda "CONECTANDO…" | El WebSocket `/ws` no pasa: WebSockets apagado en Cloudflare, o una red que bloquea el puerto 8765 | Paso 4.5. En redes estrictas, usá HTTPS (caminos B o C) |
| En la facultad no anda y en casa sí | Redes que sólo dejan los puertos 80 y 443 | Camino B o C (HTTPS por el 443) |
| Se corta solo a los pocos días | La opción "Detener la tarea si se ejecuta más de 3 días" | Desmarcala (paso 2.6) |
| Después de una actualización de Windows no anda | La tarea no tiene el desencadenador "Al iniciar el sistema" o le falta "Ejecutar aunque el usuario no haya iniciado sesión" | Revisá el paso 2 |
| `/status/full` responde 404 | No se configuró la contraseña del panel | Sección "Contraseña del panel", y reiniciá |
| `/status/full` responde 401 | Contraseña incorrecta | El usuario da igual: sólo se controla la contraseña |
| Error al arrancar el servidor | Varias causas | Mirá `logs\server.log` |

---

## 10. Seguridad

- **Qué queda expuesto:**
  - camino A: sólo el puerto del juego;
  - camino C: el 80 y el 443, sólo para Caddy;
  - caminos B y D: ninguno.
- **Qué controla el servidor:**
  - valida cada mensaje (JSON, nunca `pickle`) y limita su tamaño y su frecuencia;
  - admite como máximo 64 conexiones y 16 salas en juego;
  - guarda las contraseñas de sala como hash con sal.
- **Secretos:** el token de DuckDNS, el del túnel de Cloudflare y la contraseña del panel son secretos. No los subas al repositorio ni los pegues en chats.
- **No abras nada más:** ni escritorio remoto ni carpetas compartidas. Mantené Windows actualizado.
- **HTTPS:** para algo que queda andando, preferí B o C.
