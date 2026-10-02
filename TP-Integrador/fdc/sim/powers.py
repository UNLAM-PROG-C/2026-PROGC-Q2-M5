"""Poderes: objetos recolectables, efectos temporales y bombas.

Reglas implementadas (ver también README):
* Como máximo un objeto recolectable a la vez; aparece cada 7-10 s de juego
  efectivo y desaparece a los 6 s si nadie lo toca con la pelota.
* Receptor = último jugador que tocó la pelota. Si no hay último toque, los
  poderes personales NO se consumen (la pelota lo atraviesa); los globales sí.
* Los efectos se guardan en un diccionario con clave (objetivo, propiedad):
    - repetir el mismo efecto renueva la duración (misma clave, no se apila);
    - un efecto opuesto sobre la misma propiedad y objetivo lo reemplaza;
    - propiedades distintas conviven.
* Los modificadores se recalculan SIEMPRE desde los valores base, así que al
  expirar un efecto no quedan errores acumulados.
* Todo se descuenta sólo durante el juego efectivo: la pausa, las cuentas
  regresivas y las celebraciones congelan temporizadores y fusibles.
"""
import math

from ..config import (Arena, BallSpec, PERSONAL_TARGETS, POWER_IDS,
                      POWERS_BY_ID, PowerRules as PR)
from .physics import EPSILON, clamp

PLAYER_CLEARANCE = 10       # px libres entre un objeto que aparece y el cuerpo de un jugador
GOAL_CLEARANCE = 20         # px libres entre un objeto y la boca de un arco
FLOOR_CLEARANCE = 10        # px libres entre un objeto y el piso
CEILING_CLEARANCE = 60      # px libres entre un objeto y el techo (debajo del tablero)
BOMB_HEIGHT = 20            # px sobre el piso donde se apoya una bomba
BLAST_MIN_UPWARD = 0.35     # la explosión siempre empuja hacia arriba al menos esta fracción
TEST_SPAWN_OFFSET_X = 180   # modo de prueba: el objeto aparece a esta distancia horizontal de la pelota
TEST_SPAWN_HEIGHT = 200     # modo de prueba: y a esta altura sobre el piso (alcanzable con una patada)


class Effect:
    __slots__ = ("power", "target", "prop", "value", "left", "duration")

    def __init__(self, power, target, prop, value, duration):
        self.power = power
        self.target = target
        self.prop = prop
        self.value = value
        self.left = duration
        self.duration = duration


class Pickup:
    __slots__ = ("id", "power", "x", "y", "ttl")

    def __init__(self, pid, power, x, y):
        self.id = pid
        self.power = power
        self.x = x
        self.y = y
        self.ttl = PR.PICKUP_TTL


class Bomb:
    __slots__ = ("id", "x", "y", "fuse")

    def __init__(self, bid, x, y):
        self.id = bid
        self.x = x
        self.y = y
        self.fuse = PR.BOMB_WARNING


def resolve_targets(pdef, receptor):
    """Objetivos concretos ("p0", "goal1", "ball"...) de un poder."""
    if pdef.target == "self":
        return [f"p{receptor}"]
    if pdef.target == "rival":
        return [f"p{1 - receptor}"]
    if pdef.target == "rival_goal":
        # el arco que defiende el rival: donde ataca el receptor
        return [f"goal{1 - receptor}"]
    if pdef.target == "ball":
        return ["ball"]
    return []


class PowerManager:
    def __init__(self, rng):
        self.rng = rng
        self._next_id = 1
        self.clear()

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def _roll_spawn(self):
        return self.rng.uniform(PR.SPAWN_MIN, PR.SPAWN_MAX)

    def clear(self):
        """Limpia efectos, objeto y bombas (después de un gol o al reiniciar)."""
        self.effects = {}
        self.pickup = None
        self.bombs = []
        self.spawn_timer = self._roll_spawn()

    # ------------------------------------------------------------------
    def update(self, dt, match, events):
        """Se llama sólo en juego efectivo."""
        for key, eff in list(self.effects.items()):
            eff.left -= dt
            if eff.left <= 0:
                del self.effects[key]
                events.append(("power_expired", {"power": eff.power, "target": eff.target}))

        if self.pickup is not None:
            self.pickup.ttl -= dt
            if self.pickup.ttl <= 0:
                pk = self.pickup
                self.pickup = None
                events.append(("pickup_expired", {"power": pk.power, "x": pk.x, "y": pk.y}))

        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and self.pickup is None:
            pos = self._find_spawn(match)
            if pos is None:
                self.spawn_timer = 0.5  # no hubo lugar libre: reintentar pronto
            else:
                power = self.rng.choice(POWER_IDS)
                self.place_pickup(power, pos, events)
                self.spawn_timer = self._roll_spawn()

        for bomb in list(self.bombs):
            bomb.fuse -= dt
            if bomb.fuse <= 0:
                self.bombs.remove(bomb)
                self._explode(bomb, match, events)

    def place_pickup(self, power, pos, events):
        self.pickup = Pickup(self._new_id(), power, pos[0], pos[1])
        events.append(("power_spawn", {"pickup": self.pickup.id, "power": power,
                                       "x": pos[0], "y": pos[1]}))

    def _find_spawn(self, match):
        ball = match.ball
        r = PR.PICKUP_RADIUS
        for _ in range(PR.SPAWN_TRIES):
            x = self.rng.uniform(*PR.SPAWN_X)
            y = self.rng.uniform(*PR.SPAWN_Y)
            if math.hypot(x - ball.x, y - ball.y) < PR.SPAWN_MIN_BALL_DIST:
                continue
            if not self.position_is_free(x, y, match):
                continue
            ok = True
            for p in match.players:
                for cx, cy, cr in p.circles():
                    if math.hypot(x - cx, y - cy) < cr + r + PLAYER_CLEARANCE:
                        ok = False
            if ok:
                return x, y
        return None

    @staticmethod
    def position_is_free(x, y, match):
        """Fuera de arcos, travesaños, paredes y piso."""
        r = PR.PICKUP_RADIUS
        if x - r < Arena.GOAL_DEPTH + GOAL_CLEARANCE or x + r > Arena.WIDTH - Arena.GOAL_DEPTH - GOAL_CLEARANCE:
            return False
        if y + r > Arena.FLOOR_Y - FLOOR_CLEARANCE or y - r < Arena.CEILING_Y + CEILING_CLEARANCE:
            return False
        for g in match.goals:
            x0, y0, x1, y1 = g.bar_rect()
            if x0 - r < x < x1 + r and y0 - r < y < y1 + r:
                return False
        return True

    # ------------------------------------------------------------------
    def check_pickup(self, match, events):
        pk = self.pickup
        if pk is None:
            return
        ball = match.ball
        if math.hypot(ball.x - pk.x, ball.y - pk.y) > ball.radius + PR.PICKUP_RADIUS:
            return
        pdef = POWERS_BY_ID[pk.power]
        if pdef.target in PERSONAL_TARGETS and match.last_touch is None:
            return  # personal sin receptor: no se consume
        self.pickup = None
        self.activate(pk.power, match.last_touch, match, pk.x, pk.y, events)

    def activate(self, power, receptor, match, x, y, events):
        pdef = POWERS_BY_ID[power]
        if pdef.target in PERSONAL_TARGETS and receptor is None:
            return False
        targets = resolve_targets(pdef, receptor)
        for t in targets:
            # misma clave -> renueva o reemplaza (nunca se multiplica)
            self.effects[(t, pdef.prop)] = Effect(power, t, pdef.prop, pdef.value, pdef.duration)
        if pdef.prop == "bomb":
            bx = self.rng.uniform(*PR.BOMB_ZONE_X)
            bomb = Bomb(self._new_id(), bx, Arena.FLOOR_Y - BOMB_HEIGHT)
            self.bombs.append(bomb)
            events.append(("bomb_armed", {"bomb": bomb.id, "x": bomb.x, "y": bomb.y}))
        events.append(("power", {"power": power, "receptor": receptor,
                                 "targets": targets, "x": x, "y": y}))
        self.apply_modifiers(match)
        return True

    def apply_modifiers(self, match):
        """Recalcula todo desde los valores base."""
        eff = self.effects
        for p in match.players:
            p.clear_modifiers()
            key = f"p{p.idx}"
            if (key, "speed") in eff:
                p.speed_mult = eff[(key, "speed")].value
            if (key, "jump") in eff:
                p.jump_mult = eff[(key, "jump")].value
            if (key, "size") in eff:
                p.target_scale = eff[(key, "size")].value
            p.frozen = (key, "frozen") in eff
            p.no_kick = (key, "no_kick") in eff
            if p.frozen and p.kick_t >= 0:
                p.kick_t = -1.0
        for g in match.goals:
            e = eff.get((f"goal{g.side}", "goal_height"))
            g.set_multiplier(e.value if e else 1.0)
        e = eff.get(("ball", "radius"))
        match.ball.set_radius_multiplier(e.value if e else 1.0)
        e = eff.get(("ball", "bounce"))
        match.ball.bounce_mult = e.value if e else 1.0

    # ------------------------------------------------------------------
    def _explode(self, bomb, match, events):
        """Empuja pelota y jugadores según la distancia. No toca el último toque."""
        R = PR.BOMB_BLAST_RADIUS

        def push(cx, cy, strength):
            dx, dy = cx - bomb.x, cy - bomb.y
            d = math.hypot(dx, dy)
            if d >= R:
                return None
            f = 1.0 - d / R
            if d > EPSILON:
                nx, ny = dx / d, dy / d
            else:
                nx, ny = 0.0, -1.0
            ny = min(ny, -BLAST_MIN_UPWARD)          # siempre con componente hacia arriba
            n = math.hypot(nx, ny)
            return nx / n * strength * f, ny / n * strength * f, f

        ball = match.ball
        res = push(ball.x, ball.y, PR.BOMB_BALL_IMPULSE)
        if res:
            ball.vx += res[0]
            ball.vy += res[1]
            ball.clamp_speed()
        for p in match.players:
            res = push(p.x, p.y - p.height() / 2, PR.BOMB_PLAYER_IMPULSE)
            if res:
                p.vx += res[0]
                p.vy += res[1]
                p.on_ground = False
                p.knockback = PR.BOMB_KNOCKBACK * res[2]
        events.append(("bomb_explode", {"bomb": bomb.id, "x": bomb.x, "y": bomb.y,
                                        "radius": R}))

    # ------------------------------------------------------------------
    def snapshot(self):
        pk = self.pickup
        return {
            "pickup": None if pk is None else {
                "id": pk.id, "power": pk.power, "x": pk.x, "y": pk.y,
                "ttl": pk.ttl, "ttl_max": PR.PICKUP_TTL},
            "bombs": [{"id": b.id, "x": b.x, "y": b.y, "fuse": b.fuse,
                       "fuse_max": PR.BOMB_WARNING} for b in self.bombs],
            "effects": [{"power": e.power, "target": e.target, "left": e.left,
                         "dur": e.duration}
                        for e in sorted(self.effects.values(), key=lambda e: (e.target, e.prop))],
        }


def default_test_spawn(match):
    """Posición fija y alcanzable para el modo de prueba."""
    ball_x = match.ball.x
    x = clamp(ball_x + TEST_SPAWN_OFFSET_X if ball_x < Arena.WIDTH / 2 else ball_x - TEST_SPAWN_OFFSET_X,
              *PR.SPAWN_X)
    return x, Arena.FLOOR_Y - TEST_SPAWN_HEIGHT - BallSpec.RADIUS
