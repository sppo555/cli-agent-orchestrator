"""Force an unattended tmux worker pane to render during initialization.

Root cause (custom 4.13): a tmux window that no client is currently viewing
does not flush its TUI redraws through ``pipe-pane``. The Ink-based Claude Code
and antigravity/agy CLIs only repaint when a client is attached to the window,
so the idle prompt frame never reaches the StatusMonitor's rolling buffer and
the terminal's status is stuck at ``UNKNOWN``. ``provider.initialize()`` then
times out in ``wait_for_shell`` / ``wait_until_status`` — the worker never
receives its dispatched task — unless a human happens to open the Web terminal
(which attaches a viewer and forces the pane to render). Observed live: workers
sat at ``UNKNOWN`` for the full init timeout and only reached IDLE within
seconds of a viewer attaching.

Fix: for the duration of init, attach a short-lived HEADLESS PTY client to the
worker window — the same grouped-viewer-session mechanism the Web terminal uses
(see ``api/main.py``), sized to match the pane so it does not reflow. That keeps
the pane rendering so the shell prompt, CLI launch banner and idle box all flow
through ``pipe-pane`` to the StatusMonitor. The viewer is detached as soon as
init returns; during an active task the CLI emits output continuously, so no
viewer is needed to keep status flowing after init.

Only relevant to the pipe-pane (tmux) backend; the herdr backend delivers status
via its own socket events and is never routed here.
"""

from __future__ import annotations

import fcntl
import logging
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import threading
import uuid
from contextlib import contextmanager
from typing import Iterator, Tuple

logger = logging.getLogger(__name__)

# Fallback pane size if tmux cannot report one (matches the default CAO session).
_DEFAULT_COLS, _DEFAULT_ROWS = 264, 53


class _RenderViewer:
    """A headless PTY client attached to one tmux window to keep it rendering."""

    def __init__(self, session: str, window: str) -> None:
        self._session = session
        self._window = window
        # Distinct prefix from the Web terminal's ``caoview_`` so the two are
        # never confused; grouped session shares the window/pane group.
        self._viewer_session = f"caoinit_{uuid.uuid4().hex[:12]}"
        self._proc: subprocess.Popen | None = None
        self._master_fd = -1
        self._stop = threading.Event()
        self._drain: threading.Thread | None = None

    def _pane_size(self) -> Tuple[int, int]:
        try:
            out = subprocess.run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    f"{self._session}:{self._window}",
                    "#{window_width} #{window_height}",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.split()
            return int(out[0]), int(out[1])
        except (ValueError, IndexError, OSError):
            return _DEFAULT_COLS, _DEFAULT_ROWS

    def start(self) -> bool:
        """Attach the headless viewer. Best-effort: returns False on any failure."""
        try:
            cols, rows = self._pane_size()
            subprocess.run(
                ["tmux", "new-session", "-d", "-t", self._session, "-s", self._viewer_session],
                check=True,
                capture_output=True,
            )
            # Point this grouped session's independent current-window at the
            # target so the attach renders THAT window (not the session's active
            # one), mirroring the Web terminal's per-connection isolation.
            subprocess.run(
                ["tmux", "select-window", "-t", f"{self._viewer_session}:{self._window}"],
                check=False,
                capture_output=True,
            )
            master_fd, slave_fd = pty.openpty()
            # Match the pane size so ``window-size latest`` does not reflow it.
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            self._proc = subprocess.Popen(
                ["tmux", "-u", "attach-session", "-t", f"{self._viewer_session}:{self._window}"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                preexec_fn=os.setsid,
                env={**os.environ, "TERM": os.environ.get("TERM") or "xterm-256color"},
            )
            os.close(slave_fd)
            self._master_fd = master_fd
            self._drain = threading.Thread(target=self._drain_loop, daemon=True)
            self._drain.start()
            logger.debug(
                "render-viewer %s attached to %s:%s (%dx%d)",
                self._viewer_session,
                self._session,
                self._window,
                cols,
                rows,
            )
            return True
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning(
                "render-viewer attach failed for %s:%s: %s", self._session, self._window, exc
            )
            self.stop()
            return False

    def _drain_loop(self) -> None:
        """Discard the attached client's screen output so its PTY never blocks."""
        while not self._stop.is_set() and self._master_fd >= 0:
            try:
                readable, _, _ = select.select([self._master_fd], [], [], 0.5)
                if readable and not os.read(self._master_fd, 65536):
                    break
            except OSError:
                break

    def stop(self) -> None:
        """Detach the viewer and tear down its grouped session (best-effort)."""
        self._stop.set()
        if self._proc is not None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                try:
                    self._proc.terminate()
                except OSError:
                    pass
            self._proc = None
        if self._master_fd >= 0:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = -1
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", self._viewer_session],
                check=False,
                capture_output=True,
            )
        except OSError:
            pass


@contextmanager
def render_during_init(session: str, window: str) -> Iterator[None]:
    """Hold a headless render-viewer on ``session:window`` for the block's duration.

    Attaches on entry and detaches on exit. Any attach failure is swallowed so
    terminal creation is never blocked by the viewer — a failed attach just
    reverts to the prior (viewer-less) behavior.
    """
    viewer = _RenderViewer(session, window)
    viewer.start()
    try:
        yield
    finally:
        viewer.stop()
