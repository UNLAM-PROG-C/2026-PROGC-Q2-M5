"""Compila el cliente web (pygbag) en build/web.

Uso:
    .venv/bin/python tools/construir_web.py

Arma una carpeta temporal (build/web-src) sólo con lo que necesita el
navegador: web/main.py como main.py, el paquete fdc (sin las partes de
procesos y del servidor) y los sprites. Después ejecuta pygbag y deja el
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

# lo que el navegador no puede (ni necesita) usar: procesos y servidor
SKIP = {os.path.join("fdc", "ipc.py"), os.path.join("fdc", "sim"), os.path.join("fdc", "online", "server.py")}


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
    cmd = [sys.executable, "-m", "pygbag", "--build", "--title", GAME_NAME, "--ume_block", "1"]
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
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"listo: {OUT} ({size / 1024:.0f} KB). Para probar: .venv/bin/python servidor.py "
          f"y abrir http://localhost:8765")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(main())
