"""Contract between the interface and "something that simulates the match".

The local screens (local multiplayer and tournament) only use these methods
and attributes. SimLink (fdc/ipc.py) implements them: a simulation process
connected through queues. The online server uses the same SimLink, one per
room in play.

The online match does not go through this contract: its screen
(OnlineMatchScreen) talks to NetClient (fdc/online/client.py), which also
handles rooms, requested pauses, "ready" and reconnection. The states and
events it draws are the same of fdc/protocol.py. See docs/ONLINE.md.
"""
import abc


class MatchLink(abc.ABC):
  """Minimal interface the UI needs (Strategy pattern).

    Attributes the UI reads:
      ready (bool), ready_info (dict of the READY message), error (str|None),
      error_detail (str), shutdown_report (dict|None)
    """

  ready = False
  ready_info = {}
  error = None
  error_detail = ""
  shutdown_report = None

  @abc.abstractmethod
  def start(self):
    """Connects / launches the simulation (non-blocking: READY arrives
        through poll)."""

  @abc.abstractmethod
  def send_command(self, ctype, **payload):
    """Reliable command (start_match, pause, ...). Returns its cid or
        None."""

  @abc.abstractmethod
  def send_input(self, players, seqs=None):
    """Replaceable controls snapshot (cumulative press counters).

        `seqs` (online) are the client sequence numbers of those snapshots:
        the simulation echoes them back in every state ("ack")."""

  @abc.abstractmethod
  def poll(self):
    """Non-blocking: (new messages, latest state or None)."""

  @abc.abstractmethod
  def check_health(self):
    """Returns an error text if the connection/simulation failed."""

  @abc.abstractmethod
  def stop(self):
    """Coordinated shutdown. Returns a report."""

  def restart(self):
    """Stops the simulation and launches a new one."""
    self.stop()
    self.start()

  @property
  def alive(self):
    return self.error is None

  def debug_lines(self):
    """Extra lines for the F3 panel (none by default)."""
    return {}
