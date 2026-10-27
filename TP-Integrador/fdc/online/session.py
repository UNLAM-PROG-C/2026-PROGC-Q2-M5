"""Session of the online server: one person with a name.

A session survives short connection drops (the person comes back with its
token). Each connected session has a WRITER task with its own outbox, so a
slow client never blocks the server loop or the other players.
"""
import asyncio
import collections
import itertools
import logging
import secrets

from websockets import exceptions as ws_exceptions

from fdc import config
from fdc.online import wire

log = logging.getLogger("fdc.server")


class Session:
    """One person on the server: identity, token and outbox."""
    _ids = itertools.count(1)

    def __init__(self, traffic):
        self.id = f"s{next(self._ids)}"
        # To come back after a connection drop.
        self.token = secrets.token_urlsafe(config.Online.TOKEN_BYTES)
        self.username = None    # to show and log: "Ale #4821"
        self.identity = {}      # username, tag and display (from the Lobby)
        self.ws = None
        self.queue = collections.deque()    # reliable messages, in order
        self.state_text = None              # latest state: replaceable
        self.wake = asyncio.Event()
        self.writer = None
        self.expire_task = None
        self.dropped_states = 0
        self.traffic = traffic  # server counters (for the panel)

    # --------------------------------------------------------------- sending
    def send(self, msg):
        self.send_text(wire.encode(msg))

    def send_text(self, text, replaceable=False):
        """Never blocks: leaves the message for the writer task.

        Policy: states are replaceable (if the browser is slow only the
        newest is sent); everything else is delivered in order. If too many
        pile up, the client is not reading: the connection is closed (and
        the time to come back starts), so a slow client affects nobody."""
        if self.ws is None:
            return      # disconnected: it gets an updated summary on return
        if replaceable:
            self._replace_state(text)
        elif not self._enqueue(text):
            return
        self.wake.set()

    def _replace_state(self, text):
        if self.state_text is not None:
            self.dropped_states += 1
            self.traffic["states_replaced"] += 1
        self.state_text = text

    def _enqueue(self, text):
        """Queues a reliable message; False if the client stopped reading."""
        if len(self.queue) >= config.Online.OUTBOX_LIMIT:
            log.warning("%s does not read its messages: closing it",
                        self.username)
            asyncio.ensure_future(self.ws.close(wire.CLOSE_POLICY,
                                                "client too slow"))
            return False
        self.queue.append(text)
        return True

    def attach(self, ws):
        """Binds a WebSocket and starts its writer task."""
        self.detach()
        self.ws = ws
        self.queue.clear()
        self.state_text = None
        self.writer = asyncio.create_task(self._write_loop(ws))

    def detach(self):
        if self.writer is not None:
            self.writer.cancel()
            self.writer = None
        self.ws = None

    async def _write_loop(self, ws):
        """Writer task: sleeps until there is something to send."""
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                await self._flush(ws)
        except ws_exceptions.ConnectionClosed:
            pass

    async def _flush(self, ws):
        while self.queue:
            await ws.send(self.queue.popleft())
            self.traffic["messages_sent"] += 1
        if self.state_text is not None:
            text, self.state_text = self.state_text, None
            await ws.send(text)
            self.traffic["states_sent"] += 1
