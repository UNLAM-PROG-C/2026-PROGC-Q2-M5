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
    icon = pygame.Surface((96, 96), pygame.SRCALPHA)
    BallSprite().draw(icon, 48, 48, 40, 20)
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
    (estadio, logo, cabezones, fuente pixel art y botones retro)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, ROOT)
    try:
        import pygame
    except ImportError:
        return False
    pygame.display.init()
    pygame.display.set_mode((1280, 720))
    from fdc.config import PLAYER_COLORS
    from fdc.ui import palette as C
    from fdc.ui.assets import draw_text, text
    from fdc.ui.retro import bevel_box
    from fdc.ui.screens import dim, draw_logo, panel
    from fdc.ui.sprites import CharacterSprites
    from fdc.ui.stadium import BallSprite, build_background

    splash = build_background().copy()
    dim(splash, 70)
    sprites = CharacterSprites()
    for i, (cid, x, f) in enumerate((("messi", 230, 1), ("pele", 1050, -1))):
        img, (fx, fy) = sprites.player(cid, f, 0, 0, PLAYER_COLORS[i], False, 1.6)
        splash.blit(img, (x - fx, 646 - fy))
    panel(splash, pygame.Rect(360, 20, 560, 150), alpha=225)
    draw_logo(splash, (640, 72), 0.9, 0.0)
    pygame.image.save(splash, os.path.join(out, "splash.png"))

    ball = pygame.Surface((64, 64), pygame.SRCALPHA)
    BallSprite().draw(ball, 32, 32, 26, 30)
    pygame.image.save(ball, os.path.join(out, "pelota.png"))

    for key, msg in LOADING_TEXTS.items():
        pygame.image.save(text(msg, 24, C.WHITE, outline=C.INK, shadow=True), os.path.join(out, f"txt_{key}.png"))

    btn = pygame.Surface((480, 84), pygame.SRCALPHA)
    bevel_box(btn, pygame.Rect(0, 0, 472, 76), C.GOLD)
    draw_text(btn, "¡TOCÁ PARA JUGAR!", 32, (236, 38), C.INK, outline=None)
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
    from fdc.config import GAME_NAME
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
        print(res.stdout[-3000:], res.stderr[-3000:], sep="\n")
        print("ERROR: pygbag no generó el cliente web")
        return 1
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(STAGE, "build", "web"), OUT)
    if not make_loading_images(OUT):          # van sueltas: no hace falta meterlas en el paquete
        print("AVISO: sin pygame no se generaron las imágenes de la pantalla de carga")
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"listo: {OUT} ({size / 1024:.0f} KB). Para probar: .venv/bin/python servidor.py "
          f"y abrir http://127.0.0.1:8765")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(main())
