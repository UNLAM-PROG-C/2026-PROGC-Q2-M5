"""Estado autoritativo de un partido.

Esta clase no sabe nada de procesos ni de colas: recibe controles, avanza con
paso fijo y devuelve eventos. Por eso se puede probar directamente (tests) y
en el futuro podría correr en un servidor online sin cambios.

Fases:  countdown -> playing -> goal -> countdown -> playing ... -> finished
La pausa es una bandera aparte: congela cualquier fase.
El reloj sólo corre en "playing" y sin pausa.
"""
import math
import random

from ..config import MatchRules, PlayerSpec, POWERS_BY_ID, BallSpec
from .. import protocol as P
from .physics import (Ball, Goal, Player, apply_kick, ball_hits_foot,
                      collide_players, control_player, integrate_player, land_on_heads,
                      step_ball)
from .powers import PowerManager, default_test_spawn

# Prioridad para resolver contactos simultáneos (ver README):
# patada > cabeza > cuerpo; luego mayor velocidad de impacto; empate exacto ->
# se conserva el último toque anterior.
TOUCH_PRIORITY = {"kick": 3, "head": 2, "body": 1}
SOUND_COOLDOWN = 0.07
KICK_BALL_IGNORE = 0.12   # s sin choque entre la pelota y quien la acaba de patear
NET_DAMPING = 7.0   # 1/s: frenado de la red durante la celebración


class Match:
    def __init__(self, match_id, seed=None, characters=("?", "?"), duration=None):
        self.id = match_id
        self.seed = seed if seed is not None else random.randrange(2 ** 31)
        self.rng = random.Random(self.seed)
        # Los personajes sólo se guardan para el registro: la física usa
        # siempre las mismas capacidades base (config.PlayerSpec).
        self.characters = tuple(characters)
        self.players = [Player(0), Player(1)]
        self.ball = Ball()
        self.goals = [Goal(0), Goal(1)]
        self.powers = PowerManager(self.rng)
        self.score = [0, 0]
        self.clock = float(duration) if duration else MatchRules.DURATION
        self.tick = 0
        self.phase = P.PHASE_COUNTDOWN
        self.phase_left = MatchRules.KICKOFF_COUNTDOWN
        self.paused = False
        self.pause_reason = None
        self.last_touch = None
        self.scorer = None
        self.winner = None
        self.goal_latched = False
        self.move = [0, 0]
        self.pending_jump = [False, False]
        self.pending_kick = [False, False]
        self._sound_cd = {}
        self._events = []

    # ------------------------------------------------------------------ entrada
    def set_input(self, idx, left, right, new_jumps, new_kicks):
        self.move[idx] = (1 if right else 0) - (1 if left else 0)
        # las pulsaciones sólo cuentan en juego efectivo; las que llegan en
        # cuentas regresivas o pausa se descartan a propósito
        if self.phase == P.PHASE_PLAYING and not self.paused:
            if new_jumps > 0:
                self.pending_jump[idx] = True
            if new_kicks > 0:
                self.pending_kick[idx] = True

    def pause(self, reason=P.PAUSE_REASON_USER):
        if self.phase == P.PHASE_FINISHED:
            return False
        self.paused = True
        self.pause_reason = reason
        self.move = [0, 0]
        self.pending_jump = [False, False]
        self.pending_kick = [False, False]
        return True

    def resume(self):
        if not self.paused:
            return False
        self.paused = False
        self.pause_reason = None
        if self.phase == P.PHASE_PLAYING:
            self.phase = P.PHASE_COUNTDOWN
            self.phase_left = MatchRules.RESUME_COUNTDOWN
        return True

    # ------------------------------------------------------------------ paso
    def step(self, dt):
        """Avanza un paso fijo y devuelve la lista de eventos (tipo, datos)."""
        self._events = ev = []
        if self.paused or self.phase == P.PHASE_FINISHED:
            return ev
        self.tick += 1
        for k in list(self._sound_cd):
            self._sound_cd[k] -= dt

        if self.phase == P.PHASE_COUNTDOWN:
            self.phase_left -= dt
            if self.phase_left <= 0:
                self.phase = P.PHASE_PLAYING
                self.phase_left = 0.0
                ev.append((P.EV_KICKOFF, {}))
            return ev

        if self.phase == P.PHASE_GOAL:
            self.phase_left -= dt
            self._physics(dt, controls=False)
            # la red amortigua: la pelota queda adentro durante la celebración
            if any(g.ball_inside(self.ball) or abs(self.ball.x - g.mouth_x) < 40 for g in self.goals):
                k = math.exp(-NET_DAMPING * dt)
                self.ball.vx *= k
                self.ball.vy *= k if self.ball.vy < 0 else 1.0
            if self.phase_left <= 0:
                self._reset_after_goal()
            return ev

        # --- juego efectivo
        self.powers.update(dt, self, ev)
        self.powers.apply_modifiers(self)
        prev_x = self.ball.x
        self._physics(dt, controls=True)
        self.powers.check_pickup(self, ev)
        self._check_goals(prev_x)
        if self.phase == P.PHASE_PLAYING:
            self.clock = max(0.0, self.clock - dt)
            if self.clock <= 0:
                self._finish()
        return ev

    def _physics(self, dt, controls):
        ev = self._events
        actions = []
        for p in self.players:
            i = p.idx
            if controls:
                control_player(p, dt, self.move[i], self.pending_jump[i],
                               self.pending_kick[i], actions)
            else:
                control_player(p, dt, 0, False, False, actions)
            self.pending_jump[i] = self.pending_kick[i] = False
            p.update_size(dt)
        for kind, idx in actions:
            ev.append((P.EV_KICK if kind == "kick" else P.EV_KICK_BLOCKED, {"player": idx}))
        for p in self.players:
            integrate_player(p, dt, self.goals)
        land_on_heads(self.players)
        collide_players(self.players[0], self.players[1])
        for g in self.goals:
            g.update(dt)
        self.ball.update_size(dt)

        contacts, touches = [], []
        ball = self.ball
        kickers = [p for p in self.players
                   if p.kick_active() and not p.kick_hit and ball_hits_foot(ball, p)]
        if kickers:
            # si ambos patean en el mismo paso, la pelota recibe el promedio
            vels = [apply_kick(ball, p) for p in kickers]
            ball.vx = sum(v[0] for v in vels) / len(vels)
            ball.vy = sum(v[1] for v in vels) / len(vels)
            ball.clamp_speed()
            for p in kickers:
                p.kick_hit = True
                p.ball_ignore = KICK_BALL_IGNORE
                contacts.append((p.idx, "kick", PlayerSpec.KICK_POWER))
                ev.append((P.EV_TOUCH, {"kind": "kick", "player": p.idx,
                                        "x": ball.x, "y": ball.y, "speed": PlayerSpec.KICK_POWER}))
        step_ball(ball, self.players, self.goals, dt, contacts, touches)
        self._resolve_last_touch(contacts)
        self._sound_events(contacts, touches)

    def _resolve_last_touch(self, contacts):
        if not contacts:
            return
        best = {}
        for idx, kind, imp in contacts:
            key = (TOUCH_PRIORITY[kind], imp)
            if idx not in best or key > best[idx]:
                best[idx] = key
        if len(best) == 1:
            self.last_touch = next(iter(best))
        elif best[0] != best[1]:
            self.last_touch = 0 if best[0] > best[1] else 1
        # empate exacto: se conserva el último toque anterior

    def _sound_events(self, contacts, touches):
        ev = self._events
        seen = set()
        for idx, kind, imp in contacts:
            if kind == "kick" or imp < BallSpec.SOUND_MIN_IMPACT or kind in seen:
                continue
            if self._sound_cd.get(kind, 0) > 0:
                continue
            seen.add(kind)
            self._sound_cd[kind] = SOUND_COOLDOWN
            ev.append((P.EV_TOUCH, {"kind": kind, "player": idx, "x": self.ball.x,
                                    "y": self.ball.y, "speed": imp}))
        for kind, imp in touches:
            if imp < BallSpec.SOUND_MIN_IMPACT or kind in seen or self._sound_cd.get(kind, 0) > 0:
                continue
            seen.add(kind)
            self._sound_cd[kind] = SOUND_COOLDOWN
            ev.append((P.EV_TOUCH, {"kind": kind, "player": None, "x": self.ball.x,
                                    "y": self.ball.y, "speed": imp}))

    # ------------------------------------------------------------------ goles
    def _check_goals(self, prev_x):
        if self.goal_latched or self.phase != P.PHASE_PLAYING:
            return
        ball = self.ball
        for g in self.goals:
            moving_in = ball.x < prev_x if g.side == 0 else ball.x > prev_x
            if g.ball_inside(ball) and moving_in:
                self._score_goal(g)
                return

    def _score_goal(self, goal):
        scorer = 1 - goal.side
        self.goal_latched = True   # un mismo ingreso no genera más goles
        self.score[scorer] += 1
        self.scorer = scorer
        self.players[scorer].celebrating = True
        own_goal = self.last_touch == goal.side
        self.phase = P.PHASE_GOAL
        self.phase_left = MatchRules.GOAL_CELEBRATION
        self.powers.clear()
        self.powers.apply_modifiers(self)
        self._events.append((P.EV_GOAL, {"scorer": scorer, "side": goal.side,
                                         "score": list(self.score), "own_goal": own_goal,
                                         "x": self.ball.x, "y": self.ball.y}))

    def _reset_after_goal(self):
        for p in self.players:
            p.reset()
        self.ball.reset()
        for g in self.goals:
            g.reset()
        self.powers.clear()
        self.powers.apply_modifiers(self)
        self.last_touch = None
        self.scorer = None
        self.goal_latched = False
        self.phase = P.PHASE_COUNTDOWN
        self.phase_left = MatchRules.GOAL_COUNTDOWN

    def _finish(self):
        self.phase = P.PHASE_FINISHED
        self.powers.clear()
        s0, s1 = self.score
        self.winner = None if s0 == s1 else (0 if s0 > s1 else 1)
        if self.winner is not None:
            self.players[self.winner].celebrating = True
        self._events.append((P.EV_MATCH_END, {"score": list(self.score),
                                              "winner": self.winner}))

    # ------------------------------------------------------------------ prueba
    def debug_power(self, power, mode):
        """Modo de prueba: 'spawn' crea el objeto; 'p0'/'p1' lo activa directo.

        Devuelve (ok, detalle, eventos)."""
        ev = []
        if power not in POWERS_BY_ID:
            return False, f"poder desconocido: {power}", ev
        if self.phase == P.PHASE_FINISHED:
            return False, "el partido terminó", ev
        if mode == "spawn":
            self.powers.place_pickup(power, default_test_spawn(self), ev)
        else:
            receptor = 0 if mode == "p0" else 1
            self.powers.activate(power, receptor, self, self.ball.x, self.ball.y, ev)
        return True, "", ev

    # ------------------------------------------------------------------ estado
    def snapshot(self, seq):
        b = self.ball
        state = {
            "type": P.MSG_STATE, "match": self.id, "seq": seq, "tick": self.tick,
            "phase": self.phase, "paused": self.paused, "pause_reason": self.pause_reason,
            "phase_left": self.phase_left, "clock": self.clock, "score": list(self.score),
            "last_touch": self.last_touch, "scorer": self.scorer, "winner": self.winner,
            "players": [{
                "x": p.x, "y": p.y, "vx": p.vx, "vy": p.vy, "facing": p.facing,
                "ground": p.on_ground, "kick": p.kick_progress(), "scale": p.scale,
                "frozen": p.frozen, "no_kick": p.no_kick, "stride": p.stride,
                "knock": p.knockback > 0, "celebrate": p.celebrating, "on_head": p.on_head,
            } for p in self.players],
            "ball": {"x": b.x, "y": b.y, "r": b.radius, "angle": b.angle,
                     "vx": b.vx, "vy": b.vy},
            "goals": [g.height for g in self.goals],
        }
        state.update(self.powers.snapshot())
        return state
