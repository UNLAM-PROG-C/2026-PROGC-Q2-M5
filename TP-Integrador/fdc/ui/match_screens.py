"""Pantallas del partido: selección de personajes, juego y resultado."""
import math

import pygame

from .. import protocol as P
from ..config import (CATEGORY_BAD, CATEGORY_COLORS, CATEGORY_GLOBAL, PLAYER_COLORS, PLAYER_KEYS,
                      PLAYER_LABELS, POWER_IDS, POWERS_BY_ID, Arena, MatchRules)
from . import palette as C
from . import pixelfont
from .assets import draw_text, text, wrap
from .retro import bevel_box
from .characters import CHARACTER_IDS, CHARACTERS_BY_ID, short_name
from .icons import power_icon
from .input import key_code, key_label
from .render import MatchRenderer
from .screens import BACK_KEYS, Menu, MenuScreen, Screen, button, dim, footer, panel, title


# ---------------------------------------------------------------------------
# Selección de personajes (independiente para cada jugador)
# ---------------------------------------------------------------------------
class SelectScreen(Screen):
    CARD_W, CARD_H, GAP = 150, 168, 14

    def __init__(self, app, preselect=None):
        super().__init__(app)
        pre = preselect or app.last_characters or (CHARACTER_IDS[0], CHARACTER_IDS[2])
        self.cursor = [CHARACTER_IDS.index(pre[0]), CHARACTER_IDS.index(pre[1])]
        self.ready = [False, False]
        self.both_ready_t = None
        self.keys = [{a: key_code(n) for a, n in PLAYER_KEYS[i].items()} for i in (0, 1)]
        self.hover = None

    # ------------------------------------------------------------------ geometría
    def card_rect(self, k):
        total = len(CHARACTER_IDS) * self.CARD_W + (len(CHARACTER_IDS) - 1) * self.GAP
        x0 = 640 - total / 2
        return pygame.Rect(x0 + k * (self.CARD_W + self.GAP), 508, self.CARD_W, self.CARD_H)

    def buttons(self, i):
        """Botones de mouse de cada jugador: ◄  OK/CANCELAR  ►."""
        x = 250 if i == 0 else 1030
        y = 402
        return {"prev": pygame.Rect(x - 150, y, 52, 44), "ok": pygame.Rect(x - 86, y, 172, 44),
                "next": pygame.Rect(x + 98, y, 52, 44)}

    # ------------------------------------------------------------------ acciones
    def move(self, i, d):
        if not self.ready[i]:
            self.cursor[i] = (self.cursor[i] + d) % len(CHARACTER_IDS)
            self.app.audio.play("select")

    def toggle(self, i):
        self.ready[i] = not self.ready[i]
        self.both_ready_t = None
        self.app.audio.play("confirm" if self.ready[i] else "back")

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key in BACK_KEYS:
                self.app.audio.play("back")
                self.app.switch(MenuScreen(self.app))
                return
            for i in (0, 1):
                k = self.keys[i]
                if ev.key == k["left"]:
                    self.move(i, -1)
                elif ev.key == k["right"]:
                    self.move(i, 1)
                elif ev.key == k["kick"] and not self.ready[i]:
                    self.toggle(i)
                elif ev.key == k["jump"] and self.ready[i]:
                    self.toggle(i)
        elif ev.type == pygame.MOUSEMOTION:
            self.hover = None
            for i in (0, 1):
                for name, r in self.buttons(i).items():
                    if r.collidepoint(ev.pos):
                        self.hover = (i, name)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
            for i in (0, 1):
                b = self.buttons(i)
                if b["ok"].collidepoint(ev.pos):
                    self.toggle(i)
                    return
                if b["prev"].collidepoint(ev.pos):
                    self.move(i, -1)
                    return
                if b["next"].collidepoint(ev.pos):
                    self.move(i, 1)
                    return
            # tarjetas: clic izquierdo elige para J1, derecho para J2
            i = 0 if ev.button == 1 else 1
            for k in range(len(CHARACTER_IDS)):
                if self.card_rect(k).collidepoint(ev.pos) and not self.ready[i]:
                    self.cursor[i] = k
                    self.app.audio.play("select")

    def update(self, dt):
        super().update(dt)
        if all(self.ready):
            if self.both_ready_t is None:
                self.both_ready_t = 0.9
            self.both_ready_t -= dt
            if self.both_ready_t <= 0:
                chars = [CHARACTER_IDS[c] for c in self.cursor]
                self.app.last_characters = chars
                self.app.switch(MatchScreen(self.app, chars))

    # ------------------------------------------------------------------ dibujo
    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 120)
        title(surf, "ELEGÍ TU PERSONAJE", (640, 40), 48)
        draw_text(surf, "Todos tienen las mismas capacidades: sólo cambia la apariencia. Pueden elegir el mismo.",
                  16, (640, 84), C.INK, outline=C.WHITE)
        sp = self.app.sprites
        for i in (0, 1):
            cid = CHARACTER_IDS[self.cursor[i]]
            ch = CHARACTERS_BY_ID[cid]
            x = 250 if i == 0 else 1030
            f = 1 if i == 0 else -1
            tag = pygame.Rect(0, 0, 300, 70)
            tag.midtop = (x, 108)
            inner = panel(surf, tag)
            pygame.draw.rect(surf, PLAYER_COLORS[i], (inner.left, inner.top, inner.width, 6))
            draw_text(surf, f"{PLAYER_LABELS[i]}  {short_name(ch).upper()}", 24, (x, inner.top + 22),
                      PLAYER_COLORS[i], outline=C.INK)
            draw_text(surf, f"{ch['team']} - camiseta {ch['number']}", 16, (x, inner.top + 44), C.INK, outline=None)
            # pedestal y jugador (festeja al confirmar)
            ped = pygame.Rect(0, 0, 200, 18)
            ped.midtop = (x, 376)
            bevel_box(surf, ped, C.STRUCT, shadow=True)
            if self.ready[i]:
                ang, bob = -50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6)
            else:
                ang, bob = 0, (-1 if (self.t * 1.6 + i * 0.5) % 2 < 1 else 0)
            img, (fx, fy) = sp.player(cid, f, ang, bob, PLAYER_COLORS[i], False, 1.9)
            surf.blit(img, (x - fx, 380 - fy))
            if self.ready[i]:
                draw_text(surf, "¡LISTO!", 32, (x + (170 if i == 0 else -170), 300 + (4 if int(self.t * 6) % 2 else 0)),
                          C.GREEN, kind="title", outline=C.INK, shadow=True)
            b = self.buttons(i)
            hv = self.hover
            button(surf, b["prev"], "◄", hv == (i, "prev"), not self.ready[i], 24, self.t)
            button(surf, b["ok"], "CANCELAR" if self.ready[i] else "OK", hv == (i, "ok"), True, 24, self.t)
            button(surf, b["next"], "►", hv == (i, "next"), not self.ready[i], 24, self.t)
            names = PLAYER_KEYS[i]
            hint = (f"{key_label(names['left'], True)}/{key_label(names['right'], True)} elegir  "
                    f"{key_label(names['kick'], True)} confirmar  {key_label(names['jump'], True)} cancelar")
            draw_text(surf, hint, 16, (x, 458), C.INK, outline=C.WHITE)
        draw_text(surf, "VS", 72, (640, 280), C.WHITE, kind="title", outline=C.INK, shadow=True)
        for k, cid in enumerate(CHARACTER_IDS):
            r = self.card_rect(k)
            sel = [i for i in (0, 1) if self.cursor[i] == k]
            rr = r.move(0, -8 if sel else 0)
            pygame.draw.rect(surf, C.INK, rr.move(6, 6))
            surf.blit(sp.portrait(cid), rr)
            pygame.draw.rect(surf, C.INK, rr, 4)
            ch = CHARACTERS_BY_ID[cid]
            draw_text(surf, short_name(ch).upper(), 16, (rr.centerx, rr.bottom - 14), C.WHITE, outline=C.INK)
            for n, i in enumerate(sel):
                inset = 6 * n if len(sel) == 2 else 0
                fr = rr.inflate(12 - inset * 2, 12 - inset * 2)
                pygame.draw.rect(surf, PLAYER_COLORS[i], fr, 6)
                lab = text(PLAYER_LABELS[i], 16, C.WHITE, outline=C.INK)
                pos = (fr.left + 6, fr.top - 12) if i == 0 else (fr.right - lab.get_width() - 6, fr.top - 12)
                pygame.draw.rect(surf, PLAYER_COLORS[i], (pos[0] - 4, pos[1] - 2, lab.get_width() + 8,
                                                          lab.get_height() + 4))
                surf.blit(lab, pos)
        if all(self.ready):
            draw_text(surf, "¡A LA CANCHA!", 40, (640, 360), C.GOLD, kind="title", outline=C.INK, shadow=True)
        footer(surf, "Esc: volver  -  Mouse: botones de cada jugador; clic izquierdo en una tarjeta elige J1, derecho J2")


# ---------------------------------------------------------------------------
# Partido
# ---------------------------------------------------------------------------
class MatchScreen(Screen):
    def __init__(self, app, characters):
        super().__init__(app)
        self.chars = list(characters)
        self.renderer = MatchRenderer(app, self.chars)
        self.filter = P.StateFilter()
        self.state = None
        self.match_id = None
        self.waiting = None          # "start" | "restart" mientras falta la confirmación
        self.pause_state = None      # None | "requested" | "paused" | "resuming"
        self.pause_reason = None
        self.pause_menu = Menu([("Continuar", self.resume), ("Reiniciar", self.restart),
                                ("Menú principal", self.to_menu)], (640, 420), width=380)
        self.end_info = None
        self.end_timer = 0.0
        self.toasts = []
        self.last_count = None
        self.ignored_events = 0
        self.test_sel = 0
        self.expected_cid = {}

    # ------------------------------------------------------------------ ciclo
    def enter(self):
        for cid in set(self.chars):
            self.app.sprites.warm(cid)   # antes de empezar: sin tirones durante el juego
        self.app.input.capture = True
        self.app.fx.clear()
        self._start(P.CMD_START)

    def leave(self):
        self.app.input.capture = False
        self.app.input.release_all()
        self.app.audio.crowd(False)

    def _start(self, cmd):
        self.match_id = self.app.next_match_id()
        self.filter.expect(self.match_id)   # desde ya se ignoran estados viejos
        self.state = None
        self.end_info = None
        self.renderer.reset()
        self.app.fx.clear()
        self.toasts.clear()
        payload = {"match": self.match_id, "characters": self.chars}
        if self.app.options.seed is not None:
            payload["seed"] = self.app.options.seed
        cid = self.app.link.send_command(cmd, **payload)
        self.expected_cid[cid] = cmd
        self.waiting = "start" if cmd == P.CMD_START else "restart"

    def _send(self, cmd, **payload):
        cid = self.app.link.send_command(cmd, **payload)
        if cid is not None:
            self.expected_cid[cid] = cmd
        return cid

    # ------------------------------------------------------------------ órdenes
    def request_pause(self, reason=P.PAUSE_REASON_USER):
        if self.waiting or self.pause_state is not None or self.state is None:
            return
        if self.state["phase"] == P.PHASE_FINISHED:
            return
        self.app.input.release_all()
        self.pause_state = "requested"
        self.pause_reason = reason
        self.pause_menu.sel = 0
        self._send(P.CMD_PAUSE, reason=reason)

    def resume(self):
        if self.pause_state != "paused":
            return
        self.pause_state = "resuming"
        self._send(P.CMD_RESUME)

    def restart(self):
        if self.pause_state != "paused":
            return
        self.pause_state = None
        self._start(P.CMD_RESTART)

    def to_menu(self):
        self._send(P.CMD_END)
        self.app.switch(MenuScreen(self.app))

    # ------------------------------------------------------------------ entrada
    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if self.pause_state is None:
                    self.request_pause()
                elif self.pause_state == "paused":
                    self.app.audio.play("confirm")
                    self.resume()
                return
            if self.app.options.test_mode and self.pause_state is None:
                self._test_key(ev.key)
        if self.pause_state == "paused":
            self.pause_menu.handle_event(ev, self.app.audio)

    def _test_key(self, key):
        n = len(POWER_IDS)
        power = POWER_IDS[self.test_sel]
        if key == key_code("f5"):
            self.test_sel = (self.test_sel - 1) % n
        elif key == key_code("f6"):
            self.test_sel = (self.test_sel + 1) % n
        elif key == key_code("f7"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="spawn")
        elif key == key_code("f8"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="p0")
        elif key == key_code("f9"):
            self._send(P.CMD_DEBUG_POWER, power=power, mode="p1")
        elif key == key_code("f12"):
            self._send(P.CMD_DEBUG_CRASH)

    def on_focus_lost(self):
        self.request_pause(P.PAUSE_REASON_FOCUS)

    # ------------------------------------------------------------------ mensajes
    def on_link(self, msgs, state):
        for m in msgs:
            t = m["type"]
            if t == P.EV_ACK:
                self._on_ack(m)
                continue
            if m.get("match") != self.match_id:
                self.ignored_events += 1     # evento de un partido anterior
                continue
            self._on_event(m)
        if state is not None and self.filter.accept(state):
            self.state = state
            if self.waiting and state["match"] == self.match_id:
                self.waiting = None

    def _on_ack(self, m):
        cmd = self.expected_cid.pop(m["cid"], None)
        if cmd is None:
            return
        if cmd in (P.CMD_START, P.CMD_RESTART):
            if not m["ok"]:
                self.app.link.fail("La simulación rechazó el inicio del partido: " + m.get("detail", ""))
        elif cmd == P.CMD_PAUSE:
            if m["ok"]:
                self.pause_state = "paused"
                self.app.audio.play("back")
            else:
                self.pause_state = None
        elif cmd == P.CMD_RESUME:
            self.pause_state = None if m["ok"] else "paused"
        elif cmd == P.CMD_DEBUG_POWER and not m["ok"]:
            self.toast(f"Prueba rechazada: {m.get('detail', '')}", (255, 120, 120))

    def _on_event(self, m):
        t = m["type"]
        au, fx, st = self.app.audio, self.app.fx, self.state
        if t == P.EV_KICKOFF:
            self.renderer.kickoff_flash = 0.8
            au.play("go")
            au.play("whistle")
        elif t == P.EV_GOAL:
            self.renderer.goal_banner = (MatchRules.GOAL_CELEBRATION, m)
            gx = 50 if m["side"] == 0 else Arena.WIDTH - 50
            fx.confetti(gx, Arena.FLOOR_Y - 120, [PLAYER_COLORS[m["scorer"]], C.WHITE, C.GOLD])
            fx.shake = 0.25
            au.play("goal")
        elif t == P.EV_MATCH_END:
            self.end_info = m
            self.end_timer = 1.8
            au.play("whistle_end")
        elif t == P.EV_PAUSED:
            self.pause_state = "paused"
            self.pause_reason = m.get("reason")
            self.app.input.release_all()
        elif t == P.EV_POWER:
            pdef = POWERS_BY_ID[m["power"]]
            col = CATEGORY_COLORS[pdef.category]
            fx.sparkle(m["x"], m["y"], col)
            au.play({CATEGORY_BAD: "power_bad", CATEGORY_GLOBAL: "power_global"}.get(pdef.category, "power_good"))
            who = PLAYER_LABELS[m["receptor"]] if m["receptor"] is not None else "Partido"
            targets = ", ".join({"p0": "J1", "p1": "J2", "goal0": "arco de J1", "goal1": "arco de J2",
                                 "ball": "pelota"}.get(x, x) for x in m["targets"])
            txt = f"{who}: {pdef.name}" + (f"  (sobre {targets})" if targets else "")
            self.toast(txt, col, m["power"])
        elif t == P.EV_POWER_SPAWN:
            fx.ring(m["x"], m["y"], 10, 60, 0.35, CATEGORY_COLORS[POWERS_BY_ID[m["power"]].category], 4)
            au.play("spawn")
        elif t == P.EV_PICKUP_EXPIRED:
            fx.burst(m["x"], m["y"], 14, (230, 230, 240), speed=(40, 120), g=0, kind="puff", size=(4, 8))
        elif t == P.EV_BOMB_ARMED:
            au.play("bomb_tick")
        elif t == P.EV_BOMB_EXPLODE:
            fx.explosion(m["x"], m["y"], m["radius"])
            au.play("explosion")
        elif t == P.EV_KICK:
            au.play("whoosh", 0.7)
        elif t == P.EV_KICK_BLOCKED:
            au.play("blocked")
            if st:
                p = st["players"][m["player"]]
                fx.burst(p["x"] + 30 * p["facing"], p["y"] - 20, 8, (255, 80, 80), speed=(40, 120), g=0)
        elif t == P.EV_TOUCH:
            kind, sp = m["kind"], m.get("speed", 0)
            k = min(1.0, sp / 1100)
            if kind == "kick":
                au.play("kick")
                fx.impact(m["x"], m["y"], 1.0, (255, 245, 200))
            elif kind == "head":
                au.play("header", 0.5 + 0.5 * k)
                fx.impact(m["x"], m["y"], 0.5 + k * 0.5)
            elif kind == "bar":
                au.play("post", 0.4 + 0.6 * k)
                fx.impact(m["x"], m["y"], k, (255, 255, 255))
            elif kind == "floor":
                au.play("bounce", 0.3 + 0.7 * k)
                if sp > 350:
                    fx.dust(m["x"], Arena.FLOOR_Y, k)
            else:
                au.play("bounce", 0.3 + 0.7 * k)

    def toast(self, txt, color, power=None):
        self.toasts.append([txt, color, 2.6, power])
        self.toasts = self.toasts[-3:]

    # ------------------------------------------------------------------ ciclo
    def update(self, dt):
        super().update(dt)
        self.renderer.update(dt)
        self.app.fx.update(dt)
        self.pause_menu.enabled = self.pause_state == "paused"
        self.pause_menu.update(dt)
        for tst in self.toasts:
            tst[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]
        st = self.state
        # los controles viajan en cada cuadro (también sirven de latido para el watchdog)
        active = (st is not None and self.pause_state is None and not st["paused"]
                  and st["phase"] == P.PHASE_PLAYING)
        self.app.link.send_input(self.app.input.snapshot(active))
        self.app.audio.crowd(st is not None and not st["paused"] and self.pause_state is None)
        if st and st["phase"] == P.PHASE_COUNTDOWN and not st["paused"]:
            n = math.ceil(st["phase_left"])
            if n != self.last_count:
                self.last_count = n
                self.app.audio.play("beep")
        else:
            self.last_count = None
        if st:
            for p in st["players"]:
                if p["frozen"] and int(self.t * 20) % 3 == 0:
                    self.app.fx.snow(p["x"] + (self.t * 97 % 60) - 30, p["y"] - 120 * p["scale"])
        if self.end_info is not None:
            self.end_timer -= dt
            if self.end_timer <= 0:
                self.app.switch(ResultScreen(self.app, self.chars, self.end_info, self.state))

    # ------------------------------------------------------------------ dibujo
    def draw(self, surf):
        st = self.state
        if st is None:
            surf.blit(self.app.background, (0, 0))
            dim(surf, 120)
            msg = "Preparando partido..." if self.waiting != "restart" else "Reiniciando partido..."
            title(surf, msg, (640, 330), 32, C.WHITE)
            draw_text(surf, "Esperando la confirmación de la simulación", 16, (640, 380), C.INK, outline=C.WHITE)
            return
        off = self.app.fx.shake_offset()
        self.renderer.draw_world(surf, st, off)
        self.app.fx.draw(surf, off)
        self.renderer.draw_hud(surf, st)
        self.renderer.draw_center_messages(surf, st)
        self._draw_toasts(surf)
        if self.end_info is not None:
            title(surf, "¡FINAL DEL PARTIDO!", (640, 330), 56, C.WHITE)
        if self.app.options.test_mode:
            self._draw_test_panel(surf)
        if self.pause_state is not None:
            self._draw_pause(surf)

    def _draw_toasts(self, surf):
        for k, (txt, col, left, power) in enumerate(self.toasts):
            if left < 0.3 and int(left * 20) % 2:
                continue                                  # parpadeo retro al desaparecer
            img = text(txt, 16, C.INK, outline=None)
            w = img.get_width() + (58 if power else 28)
            r = pygame.Rect(0, 0, w, 40)
            r.midtop = (640, 170 + k * 46)
            inner = bevel_box(surf, r, C.CREAM)
            pygame.draw.rect(surf, col, (inner.left, inner.top, 6, inner.height))
            x = inner.left + 12
            if power:
                surf.blit(power_icon(power, 28), (x, r.centery - 14))
                x += 34
            surf.blit(img, (x, r.centery - img.get_height() // 2))

    def _draw_test_panel(self, surf):
        power = POWER_IDS[self.test_sel]
        pdef = POWERS_BY_ID[power]
        r = pygame.Rect(8, 646, 600, 68)
        inner = bevel_box(surf, r, C.GOLD)
        surf.blit(power_icon(power, 44), (inner.left + 6, inner.top + 6))
        draw_text(surf, f"MODO PRUEBA - {pdef.name}", 16, (inner.left + 60, inner.top + 8), C.INK,
                  anchor="topleft", outline=None)
        draw_text(surf, "F5/F6 elegir  F7 generar objeto  F8 dar a J1  F9 dar a J2  F12 fallo SIM", 16,
                  (inner.left + 60, inner.top + 32), C.INK, anchor="topleft", outline=None)

    def _draw_pause(self, surf):
        dim(surf, 120)
        r = pygame.Rect(0, 0, 560, 380)
        r.center = (640, 390)
        inner = panel(surf, r)
        title(surf, "PAUSA", (640, inner.top + 34), 48)
        reason = {P.PAUSE_REASON_FOCUS: "La ventana perdió el foco: se liberaron los controles.",
                  P.PAUSE_REASON_WATCHDOG: "Pausa automática: la simulación dejó de recibir controles."}.get(
            self.pause_reason, "El reloj, los poderes y las bombas están detenidos.")
        for k, ln in enumerate(wrap(reason, 16, inner.width - 20)):
            draw_text(surf, ln, 16, (640, inner.top + 78 + k * 22), C.INK, outline=None)
        if self.pause_state == "paused":
            self.pause_menu.draw(surf)
        else:
            msg = {"requested": "Pausando... esperando confirmación de la simulación",
                   "resuming": "Reanudando..."}.get(self.pause_state, "")
            draw_text(surf, msg, 16, (640, r.centery + 30), C.INK, outline=None)

    def debug_info(self):
        st = self.state or {}
        f = self.filter
        return {
            "match": self.match_id, "phase": st.get("phase", "—"), "paused": st.get("paused"),
            "seq": st.get("seq", "—"), "tick": st.get("tick", "—"), "clock": st.get("clock"),
            "filtered": f"{f.rejected_old_match} de otro partido, {f.rejected_stale} viejos",
            "sim_dropped": st.get("dropped_states", 0), "cosmetic_dropped": st.get("dropped_cosmetic", 0),
            "ignored_events": self.ignored_events, "ui_pause": self.pause_state or "—",
        }


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
class ResultScreen(Screen):
    def __init__(self, app, chars, end_info, last_state):
        super().__init__(app)
        self.chars = chars
        self.score = end_info["score"]
        self.winner = end_info["winner"]
        self.menu = Menu([("Revancha", self.rematch), ("Elegir personajes", self.choose),
                          ("Menú principal", self.to_menu)], (640, 560), width=380, height=52, gap=10, size=26)
        self.confetti_t = 0.0

    def enter(self):
        self.app.audio.crowd(False)
        self.app.fx.clear()

    def rematch(self):
        self.app.switch(MatchScreen(self.app, self.chars))

    def choose(self):
        self.app.switch(SelectScreen(self.app, preselect=self.chars))

    def to_menu(self):
        self.app.switch(MenuScreen(self.app))

    def handle_event(self, ev):
        self.menu.handle_event(ev, self.app.audio)

    def update(self, dt):
        super().update(dt)
        self.menu.update(dt)
        self.app.fx.update(dt)
        self.confetti_t -= dt
        if self.winner is not None and self.confetti_t <= 0:
            self.confetti_t = 1.4
            x = 330 if self.winner == 0 else 950
            self.app.fx.confetti(x, 380, [PLAYER_COLORS[self.winner], C.WHITE, C.GOLD])

    def draw(self, surf):
        surf.blit(self.app.background, (0, 0))
        dim(surf, 100)
        sp = self.app.sprites
        for i in (0, 1):
            cid = self.chars[i]
            x, f = (330, 1) if i == 0 else (950, -1)
            win = self.winner == i
            if win:
                ang, bob = -50 + 50 * math.sin(self.t * 14), -int(abs(math.sin(self.t * 7)) * 6)
            else:
                ang, bob = 0, (-1 if (self.t * 1.6 + i * 0.5) % 2 < 1 else 0)
            img, (fx, fy) = sp.player(cid, f, ang, bob, PLAYER_COLORS[i], False, 2.4 if win else 1.8)
            surf.blit(img, (x - fx, 470 - fy))
            ch = CHARACTERS_BY_ID[cid]
            draw_text(surf, f"{PLAYER_LABELS[i]} - {short_name(ch)}", 24, (x, 500), PLAYER_COLORS[i], outline=C.INK)
        self.app.fx.draw(surf)
        if self.winner is None:
            head, col = "¡EMPATE!", C.WHITE
        else:
            head, col = f"¡GANÓ {PLAYER_LABELS[self.winner]}!", PLAYER_COLORS[self.winner]
        title(surf, head, (640, 80), 64, col)
        if self.winner is not None:
            draw_text(surf, short_name(CHARACTERS_BY_ID[self.chars[self.winner]]), 24, (640, 136), C.INK,
                      outline=C.WHITE)
        box = pygame.Rect(0, 0, 300, 110)
        box.center = (640, 290)
        pygame.draw.rect(surf, C.INK, box.move(6, 6))
        pygame.draw.rect(surf, C.STRUCT_DARK, box)
        pygame.draw.rect(surf, C.INK, box, 4)
        led = box.inflate(-16, -16)
        pygame.draw.rect(surf, C.LED_BG, led)
        score = pixelfont.render_led(f"{self.score[0]}-{self.score[1]}", 9, C.LED_ON, C.LED_OFF)
        surf.blit(score, score.get_rect(center=led.center))
        self.menu.draw(surf)
        footer(surf, "Revancha: mismos personajes  -  Elegir personajes: volver a la selección")
