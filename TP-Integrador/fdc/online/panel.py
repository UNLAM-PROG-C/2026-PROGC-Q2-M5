"""Server panel (/status): live processes, threads, tasks, rooms and traffic.

The public view only has technical data. The full view (/status/full) adds
player names and asks for a password (HTTP Basic authentication; only the
password is checked).
"""
import asyncio
import base64
import binascii
import collections
import hmac
import os
import platform
import threading
import time

# How the panel shows the asyncio tasks and the threads of the server.
TASK_KINDS = {
    "Server.conn_handler": "lectora (una por conexión)",
    "Session._write_loop": "escritora (una por conexión)",
    "Connection.keepalive": "keepalive / ping (una por conexión)",
    "RoomRunner._pump": "puente de sala (60 Hz, una por sala en juego)",
    "GameServer._expire_later": "plazo de reconexión (una por desconectado)",
    "GameServer._stats_loop": "estadísticas del panel",
    "GameServer.run": "principal del servidor",
}
THREAD_KINDS = {
    "MainThread": "principal (bucle asyncio)",
    "QueueFeederThread": "alimentador de cola (multiprocessing)",
    "asyncio": "ejecutor (lanzar/cerrar procesos, leer archivos)",
}
OTHER_TASKS = "otras (librería websockets)"
OTHER_THREADS = "otros"


def task_kind(task):
    """Panel label of an asyncio task (by the coroutine name)."""
    name = getattr(task.get_coro(), "__qualname__", "")
    return TASK_KINDS.get(name, OTHER_TASKS)


def thread_kind(thread):
    """Panel label of a thread (by its name)."""
    base = thread.name.split("_")[0].split("-")[0]
    return THREAD_KINDS.get(base, OTHER_THREADS)


def authorized(request, password):
    """HTTP Basic authentication: only the password is checked (any user
    name)."""
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    given = decoded.partition(":")[2]
    return hmac.compare_digest(given.encode("utf-8"),
                               password.encode("utf-8"))


def panel_data(server, full):
    """Snapshot of the server for the panel. The public view has no
    names."""
    now = time.monotonic()
    data = {"view": "full" if full else "public",
            "server": _server_info(server, now)}
    data.update(_activity(server))
    data["rooms"] = [_room_info(server, room, now, full)
                     for room in _sorted_rooms(server)]
    data["log"] = list(server.process_log)
    if full:
        data["players"] = [_player_info(s) for s in server.sessions.values()]
    return data


def _activity(server):
    """Connections, processes, tasks, threads and traffic."""
    return {
        "connections": server.connections,
        "sessions": len(server.sessions),
        "awaiting_reconnection": sum(s.ws is None
                                     for s in server.sessions.values()),
        "room_processes": len(server.runners),
        "tasks": _count(task_kind, asyncio.all_tasks()),
        "threads": _count(thread_kind, threading.enumerate()),
        "traffic_per_s": server.rates}


def _count(kind_of, items):
    """{label: how many} of tasks or threads."""
    return dict(collections.Counter(kind_of(item) for item in items))


def _sorted_rooms(server):
    return sorted(server.lobby.rooms.values(), key=lambda r: r.id)


def _server_info(server, now):
    return {"pid": os.getpid(), "uptime": now - server.started_at,
            "python": platform.python_version(),
            "system": platform.system(), "cores": os.cpu_count()}


def _room_info(server, room, now, full):
    info = {"room": room.id, "state": room.state,
            "players": len(room.members), "private": room.private}
    runner = server.runners.get(room.id)
    if runner is not None:
        info["simulation"] = runner.panel_info(now)
    if full:
        info.update(name=room.name, owner=room.owner,
                    members=[m.public() for m in room.members])
    return info


def _player_info(session):
    return {"name": session.username, "connected": session.ws is not None,
            "pending_messages": len(session.queue),
            "states_replaced": session.dropped_states}
