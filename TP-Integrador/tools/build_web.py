"""Builds the web client (pygbag) in build/web.

Usage:
    .venv/bin/python tools/build_web.py

It prepares a temporary folder (build/web-src) with only what the browser
needs: web/main.py as main.py, the fdc package (without the simulation
process nor the server) and the sprites. Then it runs pygbag and leaves the
result in build/web, which is what server.py serves.

It needs internet the first time: pygbag downloads its template. In the
browser, the Python interpreter (WebAssembly) is downloaded from the
pygame-web CDN (pygame-web.github.io).
"""
import importlib
import os
import shutil
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "build", "web-src")
OUT = os.path.join(ROOT, "build", "web")

# What the browser cannot (nor needs to) use: the simulation process with
# its queues (multiprocessing) and the server. The simulation itself DOES
# go: the local modes run it inside the page (fdc/sim/inline.py).
SKIP = {os.path.join("fdc", "ipc.py"), os.path.join("fdc", "sim", "process.py"),
        os.path.join("fdc", "online", "server.py"),
        os.path.join("fdc", "online", "session.py"),
        os.path.join("fdc", "online", "room_runner.py"),
        os.path.join("fdc", "online", "panel.py")}
FAVICON_SIZE = 96              # px: icon of the browser tab
FAVICON_BALL = (48, 48, 40, 20)   # ball of the icon: (x, y, radius, angle)
LOADING_BALL_SIZE = 64         # px: ball image spinning on the loading screen
LOADING_BALL = (32, 32, 26, 30)   # ball of that image: (x, y, radius, angle)
PLAY_BUTTON = (480, 84)        # play button image (with room for the shadow)
PLAY_BUTTON_FACE = (472, 76)   # the button itself (px)
ERROR_TAIL = 3000              # last characters of pygbag output on failure
BYTES_PER_KB = 1024            # to show the size of the result
# Drawing modules of the game used for the loading images.
UI_MODULES = ("assets", "layout", "palette", "retro", "screens", "sprites",
              "stadium")
# Stages of the loading screen (web/template.tmpl) and their texts.
LOADING_TEXTS = {
    "python": "LLEGANDO AL ESTADIO...",
    "file": "ABRIENDO EL VESTUARIO...",
    "pitch": "MARCANDO LA CANCHA...",
    "players": "SALEN LOS JUGADORES...",
    "ready": "¡TODO LISTO!",
}


def copy_package():
    """Copies the fdc package without what the browser does not use."""
    for base, dirs, files in os.walk(os.path.join(ROOT, "fdc")):
        rel_base = os.path.relpath(base, ROOT)
        dirs[:] = [d for d in dirs if d != "__pycache__"
                   and os.path.join(rel_base, d) not in SKIP]
        for name in files:
            rel = os.path.join(rel_base, name)
            if name.endswith(".py") and rel not in SKIP:
                os.makedirs(os.path.join(STAGE, rel_base), exist_ok=True)
                shutil.copy2(os.path.join(ROOT, rel), os.path.join(STAGE, rel))


def _load_ui():
    """pygame and the drawing modules of the game, or None without pygame
    (the images are optional)."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path.insert(0, ROOT)
    try:
        pygame = importlib.import_module("pygame")
    except ImportError:
        return None
    ui = types.SimpleNamespace(pygame=pygame,
                               config=importlib.import_module("fdc.config"))
    for name in UI_MODULES:
        setattr(ui, name, importlib.import_module(f"fdc.ui.{name}"))
    return ui


def make_icon(path):
    """Tab icon: the game ball (without pygame, pygbag uses its own)."""
    ui = _load_ui()
    if ui is None:
        return False
    pygame = ui.pygame
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    icon = pygame.Surface((FAVICON_SIZE, FAVICON_SIZE), pygame.SRCALPHA)
    ui.stadium.BallSprite().draw(icon, *FAVICON_BALL)
    pygame.image.save(icon, path)
    pygame.display.quit()
    return True


def make_loading_images(out):
    """Images of the loading screen, drawn with the same code of the game
    (stadium, logo, mascots, pixel art font and retro buttons). The
    background is the main menu one, with the same measures
    (screens.MenuScreen)."""
    ui = _load_ui()
    if ui is None:
        return False
    ui.pygame.display.init()
    ui.pygame.display.set_mode((ui.config.LOGICAL_WIDTH,
                                ui.config.LOGICAL_HEIGHT))
    ui.pygame.image.save(_splash(ui), os.path.join(out, "splash.png"))
    _save_ball(ui, out)
    _save_texts(ui, out)
    ui.pygame.image.save(_play_button(ui), os.path.join(out,
                                                        "play_button.png"))
    ui.pygame.display.quit()
    return True


def _splash(ui):
    """The main menu background: stadium, mascots and logo."""
    screens = ui.screens
    splash = ui.stadium.build_background().copy()
    screens.dim(splash, ui.layout.VEIL_MENU)
    _mascots(ui, splash)
    screens.panel(splash, ui.pygame.Rect(screens.LOGO_PANEL),
                  alpha=screens.LOGO_PANEL_ALPHA)
    screens.draw_logo(splash, screens.LOGO_CENTER, screens.LOGO_SCALE, 0.0)
    return splash


def _mascots(ui, splash):
    sprite_set = ui.sprites.CharacterSprites()
    menu = ui.screens.MenuScreen
    for i, (cid, x, f) in enumerate(menu.MASCOTS):
        img, (fx, fy) = sprite_set.player(cid, f, 0, 0,
                                          ui.config.PLAYER_COLORS[i], False,
                                          menu.MASCOT_SCALE)
        splash.blit(img, (x - fx, ui.config.Arena.FLOOR_Y - fy))


def _save_ball(ui, out):
    pygame = ui.pygame
    ball = pygame.Surface((LOADING_BALL_SIZE, LOADING_BALL_SIZE),
                          pygame.SRCALPHA)
    ui.stadium.BallSprite().draw(ball, *LOADING_BALL)
    pygame.image.save(ball, os.path.join(out, "ball.png"))


def _save_texts(ui, out):
    palette = ui.palette
    for key, msg in LOADING_TEXTS.items():
        ui.pygame.image.save(
            ui.assets.text(msg, ui.layout.FONT_TEXT, palette.WHITE,
                           outline=palette.INK, shadow=True),
            os.path.join(out, f"txt_{key}.png"))


def _play_button(ui):
    pygame, palette = ui.pygame, ui.palette
    btn = pygame.Surface(PLAY_BUTTON, pygame.SRCALPHA)
    face = pygame.Rect((0, 0), PLAY_BUTTON_FACE)
    ui.retro.bevel_box(btn, face, palette.GOLD)
    ui.assets.draw_text(btn, "¡TOCÁ PARA JUGAR!", ui.layout.FONT_LARGE,
                        face.center, palette.INK, outline=None)
    return btn


def ca_bundle_env():
    """Python from python.org on macOS has no certificates: pip's are used."""
    env = dict(os.environ)
    if "SSL_CERT_FILE" not in env:
        try:
            # pylint: disable-next=import-outside-toplevel
            from pip._vendor import certifi  # Optional.
            env["SSL_CERT_FILE"] = certifi.where()
        except ImportError:
            pass
    return env


def _stage_files():
    """Fresh build/web-src with main.py, the package and the sprites."""
    shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE)
    shutil.copy2(os.path.join(ROOT, "web", "main.py"),
                 os.path.join(STAGE, "main.py"))
    copy_package()
    shutil.copytree(os.path.join(ROOT, "assets", "characters"),
                    os.path.join(STAGE, "assets", "characters"))


def _pygbag_command(title):
    # Outside STAGE: it does not travel inside the package.
    icon = os.path.join(ROOT, "build", "favicon.png")
    template = os.path.join(ROOT, "web", "template.tmpl")   # own loading screen
    cmd = [sys.executable, "-m", "pygbag", "--build", "--title", title,
           "--ume_block", "1", "--template", template]
    if make_icon(icon):
        cmd += ["--icon", icon]
    cmd.append(STAGE)
    return cmd


def _run_pygbag(title):
    """Runs pygbag on build/web-src; False (and its output) on failure."""
    print("compilando con pygbag...", flush=True)
    res = subprocess.run(_pygbag_command(title), env=ca_bundle_env(),
                         stdin=subprocess.DEVNULL, capture_output=True,
                         text=True, check=False)
    built = os.path.join(STAGE, "build", "web", "index.html")
    if res.returncode != 0 or not os.path.isfile(built):
        print(res.stdout[-ERROR_TAIL:], res.stderr[-ERROR_TAIL:], sep="\n")
        print("ERROR: pygbag no generó el cliente web")
        return False
    return True


def _publish():
    """Copies the result to build/web and adds the loading images."""
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(os.path.join(STAGE, "build", "web"), OUT)
    if not make_loading_images(OUT):   # loose files: not in the package
        print("AVISO: sin pygame no se generaron las imágenes de la pantalla "
              "de carga")


def main():
    """Builds build/web; returns the exit code."""
    # pylint: disable-next=import-outside-toplevel
    from fdc import config  # Here: ROOT is added to the path first.
    _stage_files()
    if not _run_pygbag(config.GAME_NAME):
        return 1
    _publish()
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print(f"listo: {OUT} ({size / BYTES_PER_KB:.0f} KB). Para probar: "
          f".venv/bin/python server.py y abrir "
          f"http://127.0.0.1:{config.Online.PORT}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(main())
