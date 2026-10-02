"""Compila el cliente web (pygbag) en build/web.

Uso:
    .venv/bin/python tools/construir_web.py

Arma una carpeta temporal (build/web-src) sólo con lo que necesita el
navegador: web/main.py como main.py, el paquete fdc (sin el proceso de
simulación ni el servidor) y los sprites. Después ejecuta pygbag y deja el
resultado en build/web, que es lo que sirve servidor.py.

Necesita internet la primera vez: pygbag descarga su plantilla. En el
navegador, el intérprete de Python (WebAssembly) se descarga del CDN de
pygame-web (pygame-web.github.io).
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "build", "web-src")
OUT = os.path.join(ROOT, "build", "web")

# lo que el navegador no puede (ni necesita) usar: el proceso de simulación con
# sus colas (multiprocessing) y el servidor. La simulación en sí SÍ va: los modos
# locales la corren dentro de la página (fdc/sim/inline.py).
SKIP = {os.path.join("fdc", "ipc.py"), os.path.join("fdc", "sim", "process.py"),
        os.path.join("fdc", "online", "server.py")}
FAVICON_SIZE = 96              # px: ícono de la pestaña del navegador
FAVICON_BALL = (48, 48, 40, 20)   # pelota del ícono: (x, y, radio, ángulo)
LOADING_BALL_SIZE = 64         # px: imagen de la pelota que gira en la pantalla de carga
LOADING_BALL = (32, 32, 26, 30)   # pelota de esa imagen: (x, y, radio, ángulo)
PLAY_BUTTON = (480, 84)        # imagen del botón "¡TOCÁ PARA JUGAR!" (con lugar para la sombra)
PLAY_BUTTON_FACE = (472, 76)   # el botón en sí
ERROR_TAIL = 3000              # caracteres finales de la salida de pygbag que se muestran si falla
BYTES_PER_KB = 1024            # para mostrar el tamaño del resultado


def copy_package():
    for base, dirs, files in os.walk(os.path.join(ROOT, "fdc")):
        rel_base = os.path.relpath(base, ROOT)
        dirs[:] = [d for d in dirs if d != "__pycache__" and os.path.join(rel_base, d) not in SKIP]
        for name in files:
            rel = os.path.join(rel_base, name)
            if name.endswith(".py") and rel not in SKIP:
                os.makedirs(os.path.join(STAGE, rel_base), exist_ok=True)
                shutil.copy2(os.path.join(ROOT, rel), os.path.join(STAGE, rel))


def make_icon(path):
    """Ícono de la pestaña: la pelota del juego (si pygame no está, pygbag usa el suyo)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, ROOT)
    try:
        import pygame
    except ImportError:
        return False
    from fdc.ui.stadium import BallSprite
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    icon = pygame.Surface((FAVICON_SIZE, FAVICON_SIZE), pygame.SRCALPHA)
    BallSprite().draw(icon, *FAVICON_BALL)
    pygame.image.save(icon, path)
    pygame.display.quit()
    return True


LOADING_TEXTS = {            # etapas de la pantalla de carga (web/plantilla.tmpl)
    "python": "LLEGANDO AL ESTADIO...",
    "archivo": "ABRIENDO EL VESTUARIO...",
    "cancha": "MARCANDO LA CANCHA...",
    "jugadores": "SALEN LOS JUGADORES...",
    "listo": "¡TODO LISTO!",
}


def make_loading_images(out):
    """Imágenes de la pantalla de carga, dibujadas con el mismo código del juego
    (estadio, logo, cabezones, fuente pixel art y botones retro). El fondo es el
    del menú principal, con las mismas medidas (screens.MenuScreen)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, ROOT)
    try:
        import pygame
    except ImportError:
        return False
    pygame.display.init()
    from fdc.config import LOGICAL_HEIGHT, LOGICAL_WIDTH, PLAYER_COLORS, Arena
    pygame.display.set_mode((LOGICAL_WIDTH, LOGICAL_HEIGHT))
    from fdc.ui import palette as C
    from fdc.ui.assets import draw_text, text
    from fdc.ui.layout import FONT_LARGE, FONT_TEXT, VEIL_MENU
    from fdc.ui.retro import bevel_box
    from fdc.ui.screens import LOGO_CENTER, LOGO_PANEL, LOGO_PANEL_ALPHA, LOGO_SCALE, MenuScreen, dim, draw_logo, panel
    from fdc.ui.sprites import CharacterSprites
    from fdc.ui.stadium import BallSprite, build_background

    splash = build_background().copy()
    dim(splash, VEIL_MENU)
    sprites = CharacterSprites()
    for i, (cid, x, f) in enumerate(MenuScreen.MASCOTS):
        img, (fx, fy) = sprites.player(cid, f, 0, 0, PLAYER_COLORS[i], False, MenuScreen.MASCOT_SCALE)
        splash.blit(img, (x - fx, Arena.FLOOR_Y - fy))
    panel(splash, pygame.Rect(LOGO_PANEL), alpha=LOGO_PANEL_ALPHA)
    draw_logo(splash, LOGO_CENTER, LOGO_SCALE, 0.0)
    pygame.image.save(splash, os.path.join(out, "splash.png"))

    ball = pygame.Surface((LOADING_BALL_SIZE, LOADING_BALL_SIZE), pygame.SRCALPHA)
    BallSprite().draw(ball, *LOADING_BALL)
    pygame.image.save(ball, os.path.join(out, "pelota.png"))

    for key, msg in LOADING_TEXTS.items():
        pygame.image.save(text(msg, FONT_TEXT, C.WHITE, outline=C.INK, shadow=True),
                          os.path.join(out, f"txt_{key}.png"))

    btn = pygame.Surface(PLAY_BUTTON, pygame.SRCALPHA)
    face = pygame.Rect((0, 0), PLAY_BUTTON_FACE)
    bevel_box(btn, face, C.GOLD)
    draw_text(btn, "¡TOCÁ PARA JUGAR!", FONT_LARGE, face.center, C.INK, outline=None)
    pygame.image.save(btn, os.path.join(out, "boton_jugar.png"))
    pygame.display.quit()
    return True


def ca_bundle_env():
    """Python de python.org en macOS no trae certificados: se usa el de pip."""
    env = dict(os.environ)
    if "SSL_CERT_FILE" not in env:
        try:
            from pip._vendor import certifi
            env["SSL_CERT_FILE"] = certifi.where()
        except ImportError:
            pass
    return env


def main():
    from fdc.config import GAME_NAME, Online
    shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE)
    shutil.copy2(os.path.join(ROOT, "web", "main.py"), os.path.join(STAGE, "main.py"))
    copy_package()
    shutil.copytree(os.path.join(ROOT, "assets", "personajes"), os.path.join(STAGE, "assets", "personajes"))
    icon = os.path.join(ROOT, "build", "favicon.png")      # fuera de STAGE: no viaja dentro del paquete
    template = os.path.join(ROOT, "web", "plantilla.tmpl")    # pantalla de carga propia
    cmd = [sys.executable, "-m", "pygbag", "--build", "--title", GAME_NAME, "--ume_block", "1",
           "--template", template]
    if make_icon(icon):
        cmd += ["--icon", icon]
    cmd.append(STAGE)
    print("compilando con pygbag...", flush=True)
    res = subprocess.run(cmd, env=ca_bundle_env(), stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.isfile(os.path.join(STAGE, "build", "web", "index.html")):
        print(res.stdout[-ERROR_TAIL:], res.stderr[-ERROR_TAIL:], sep="\n")
        print("ERROR: pygbag no generó el cliente web")
        return 1
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(STAGE, "build", "web"), OUT)
    if not make_loading_images(OUT):          # van sueltas: no hace falta meterlas en el paquete
        print("AVISO: sin pygame no se generaron las imágenes de la pantalla de carga")
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"listo: {OUT} ({size / BYTES_PER_KB:.0f} KB). Para probar: .venv/bin/python servidor.py "
          f"y abrir http://127.0.0.1:{Online.PORT}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(main())
