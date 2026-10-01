"""Captura de controles de ambos jugadores (en el hilo principal de pygame).

Se registran los KEYDOWN/KEYUP en lugar de consultar get_pressed(), para
poder liberar todo al perder el foco (si no, un jugador podría quedar
caminando con una tecla "trabada").

Saltos y patadas se cuentan: cada KEYDOWN incrementa un contador que viaja
en todas las fotos de controles. Así la simulación puede quedarse sólo con la
última foto sin perder una pulsación breve.
"""
import pygame

from ..config import PLAYER_KEYS

ACTIONS = ("left", "right", "jump", "kick")


def key_code(name):
    return pygame.key.key_code(name)


KEY_NAMES = {"left": "Flecha izq.", "right": "Flecha der.", "up": "Flecha arriba",
             "down": "Flecha abajo", "escape": "Esc", "space": "Espacio", "return": "Enter"}
KEY_SHORT = {"left": "Izq", "right": "Der", "up": "Arriba", "down": "Abajo"}


def key_label(name, short=False):
    """Nombre legible en español (sin glifos que las fuentes comunes no tienen)."""
    if short and name in KEY_SHORT:
        return KEY_SHORT[name]
    return KEY_NAMES.get(name, name.upper())


class InputTracker:
    def __init__(self, bindings=PLAYER_KEYS):
        self.bindings = bindings
        self.keymap = {}
        for idx, keys in enumerate(bindings):
            for action, name in keys.items():
                self.keymap[key_code(name)] = (idx, action)
        self.held = [dict.fromkeys(ACTIONS, False) for _ in bindings]
        self.jumps = [0 for _ in bindings]
        self.kicks = [0 for _ in bindings]
        self.capture = False   # sólo cuenta pulsaciones durante el partido

    def handle_event(self, ev):
        if ev.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return False
        hit = self.keymap.get(ev.key)
        if hit is None:
            return False
        idx, action = hit
        down = ev.type == pygame.KEYDOWN
        self.held[idx][action] = down
        if down and self.capture:
            if action == "jump":
                self.jumps[idx] += 1
            elif action == "kick":
                self.kicks[idx] += 1
        return True

    def release_all(self):
        for h in self.held:
            for k in h:
                h[k] = False

    def snapshot(self, active=True):
        """[[izq, der, saltos, patadas], ...]; con active=False, sin movimiento."""
        out = []
        for i, h in enumerate(self.held):
            if active:
                out.append([h["left"], h["right"], self.jumps[i], self.kicks[i]])
            else:
                out.append([False, False, self.jumps[i], self.kicks[i]])
        return out
