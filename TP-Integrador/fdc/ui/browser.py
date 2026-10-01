"""Ajustes de la página cuando el juego corre en el navegador (pygbag).

El navegador tiene acciones propias para algunas teclas que el juego usa:
Escape "detiene la carga" de la página (en Chrome eso congela el WebSocket),
F3 abre "Buscar", Tab saca el foco del juego y las flechas desplazan la
página. Se anula SÓLO la acción del navegador (preventDefault): el evento
sigue llegando a pygame. Espacio no se toca porque hace falta para escribir
espacios en los nombres.
"""
import sys

_GUARD_JS = r"""
if (!window.fdcKeyGuard) {
  window.fdcKeyGuard = true;
  const keys = new Set(['Escape', 'Tab', 'F3', 'Backspace', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);
  window.addEventListener('keydown', function (e) { if (keys.has(e.key)) e.preventDefault(); }, true);
}
"""


def install_key_guard():
    if sys.platform != "emscripten":
        return                   # fuera del navegador (p. ej. pruebas del modo web) no hace falta
    import platform              # en pygbag, "platform" expone el objeto window de JS
    platform.window.eval(_GUARD_JS)
