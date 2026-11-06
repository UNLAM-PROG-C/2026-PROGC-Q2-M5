# Servidor online en el NAS (Docker)

El servidor del modo online (`server.py`) escucha en **8765 dentro del
contenedor** y no necesita pygame ni numpy: la simulación corre sin
interfaz. Por eso la imagen lleva sólo `websockets`
(`deploy/requirements-server.txt`).

## Lo que hay en esta carpeta

| Archivo | Qué es |
| --- | --- |
| `Dockerfile` | Imagen del servidor (python:3.12-slim + websockets). |
| `requirements-server.txt` | La única dependencia de la imagen. |
| `docker-compose.yml` | Servicio `fdc-server` + `cloudflared` opcional (perfil `tunel`). |
| `.env.example` | Plantilla de `deploy/.env` (sin valores secretos). |
| `.env` | **No está en el repositorio**: se crea acá y tiene el token. |

## Puesta en marcha

En el NAS, dentro de la carpeta de despliegue (`/volume1/docker/fdc`):

```sh
cp deploy/.env.example deploy/.env     # y completar TUNNEL_TOKEN si se usa
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f fdc-server
```

Compilar sólo la imagen:

```sh
docker build -f deploy/Dockerfile -t fdc-server .
```

Compose lee `deploy/.env` para las variables `${...}` del archivo. Desde otra
carpeta: `docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d`.

## Variables (`deploy/.env`)

| Variable | Por defecto | Para qué |
| --- | --- | --- |
| `FDC_HOST_PORT` | `18765` | Puerto publicado en el **host**, sólo para probar desde la LAN. En el NAS el 8765 y el 8080 ya están ocupados; dentro del contenedor el servidor sigue en 8765. |
| `FDC_PANEL_PASSWORD` | vacío | Password de la vista completa del panel (`/status/full`). Vacío: queda la vista pública `/status`. |
| `FDC_TUNNEL_NETWORK` | `timecore-prod_default` | Red bridge **externa** donde vive el `cloudflared` que ya corre en el NAS. |
| `TUNNEL_TOKEN` | vacío | Sólo para el perfil `tunel` (un cloudflared propio). |

## El túnel: dos opciones

El hostname público ya creado para el juego es
`futbol.timecore.com.ar` → **`http://fdc-server:8765`**.
Cloudflare resuelve el destino **por nombre de contenedor y puerto**, no por
la IP del NAS: por eso el servicio se llama `fdc-server`
(`container_name: fdc-server`) y está conectado a la red
`${FDC_TUNNEL_NETWORK}` (externa), que es la del túnel existente.
`futbol.timecore.com.ar` y `timecore-prod_default` son los datos reales del
NAS; la IP del NAS no se usa en ningún lado.

### Opción A (recomendada): sumar el hostname al túnel que ya existe

No hay que levantar nada nuevo: el `cloudflared` de `timecore.com.ar` ya está
en la red `timecore-prod_default`, y `fdc-server` también. En el panel de
Cloudflare (o en el `config.yml` del túnel) se agrega:

```
futbol.timecore.com.ar  ->  http://fdc-server:8765
```

Para que el servidor de juego alcance a ese `cloudflared`, el contenedor tiene
que estar en esa red: es lo que hace `networks: [fdc, tunnel]` con
`FDC_TUNNEL_NETWORK=timecore-prod_default` en `deploy/.env`.

### Opción B: un cloudflared propio (perfil `tunel`)

```sh
docker compose -f deploy/docker-compose.yml --profile tunel up -d
```

Levanta `fdc-tunnel` con `TUNNEL_TOKEN` de `deploy/.env`, en la misma red
externa que el servidor. Sirve si se quiere un túnel separado; **no** hay que
usarlo si ya se sumó el hostname al túnel existente (Opción A).

## Recursos y reinicio

- `mem_limit: 256m` para el servidor (y 128m para el cloudflared opcional):
  el NAS tiene 2,4 GB libres y ya corren 46 contenedores.
- `restart: unless-stopped` en los dos servicios.
- Logs de Docker acotados (3 archivos de 10 MB) y `logs/server.log` adentro
  del contenedor (`docker compose exec fdc-server tail -f logs/server.log`).

## Pruebas

Desde la LAN, con el puerto del host:

```sh
curl http://IP-DEL-NAS:18765/status.json      # panel público en JSON
```

En el juego (escritorio o exe), para apuntar a ese servidor sin TLS:
`servidor.txt` con `ws://IP-DEL-NAS:18765/ws`, o `--server`, o `FDC_SERVER`.

Por el túnel, el juego usa `wss://futbol.timecore.com.ar/ws` (es el valor que
viene en el `servidor.txt` que acompaña al exe). Ese hostname resuelve por
TLS en Cloudflare y el tráfico viaja cifrado hasta el NAS.

Sin el cliente web compilado (`build/web`) la página `http://.../` da 404; el
modo online del juego de escritorio funciona igual.
