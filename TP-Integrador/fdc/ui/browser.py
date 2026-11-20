"""Page adjustments when the game runs in the browser (pygbag).

The loading screen (stadium, bar, "¡TOCÁ PARA JUGAR!") is in
web/template.tmpl; the game hides it when it draws its first frame.

The browser has its own actions for some keys the game uses: Escape "stops
loading" the page (in Chrome that freezes the WebSocket), F3 opens "Find",
Tab takes the focus away from the game and the arrows scroll the page. ONLY
the browser action is cancelled (preventDefault): the event still reaches
pygame. Space is not touched because it is needed to type spaces in names.
"""
import sys

_GUARD_JS = r"""
if (!window.fdcKeyGuard) {
  window.fdcKeyGuard = true;
  const keys = new Set(['Escape', 'Tab', 'F3', 'Backspace', 'ArrowUp',
                        'ArrowDown', 'ArrowLeft', 'ArrowRight']);
  window.addEventListener('keydown', function (e) {
    if (keys.has(e.key)) e.preventDefault();
  }, true);
}
"""


def _window():
  # pylint: disable-next=import-outside-toplevel
  import platform     # in pygbag, "platform" exposes the JS window object
  return platform.window


def install_key_guard():
  """Stops the browser actions of the game keys."""
  if sys.platform != "emscripten":
    return          # outside the browser (e.g. web mode tests) not needed
  _window().eval(_GUARD_JS)


def hide_loading_screen():
  """The game drew its first frame: the loading screen goes away
    (web/template.tmpl)."""
  if sys.platform != "emscripten":
    return
  splash = getattr(_window(), "fdcSplash", None)
  if splash is not None:
    splash.done()
