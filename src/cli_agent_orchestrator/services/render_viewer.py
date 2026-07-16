"""Force an unattended tmux worker pane to render when its TUI goes quiet.

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

Init fix: for the duration of init, attach a short-lived HEADLESS PTY client to the
worker window — the same grouped-viewer-session mechanism the Web terminal uses
(see ``api/main.py``), sized to match the pane so it does not reflow — AND
periodically toggle its size by one row to fire a SIGWINCH re-render. A passive
attach alone is not enough: the CLI paints its idle frame once (buried in the
launch burst) then goes quiet, and the StatusMonitor can miss it; the periodic
SIGWINCH makes the CLI repaint its current frame, so once it settles to idle a
clean idle box flows through ``pipe-pane`` and the status flips.

Post-init recovery: a continued terminal can also finish a turn without its
final ready frame reaching ``pipe-pane``. Inbox reconciliation briefly attaches
a non-periodic viewer and performs a shrink/restore pair of SIGWINCH redraws.
Both lifecycles avoid agent input and are limited to the tmux backend.

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
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, Tuple

from cli_agent_orchestrator.constants import (
    INBOX_REDRAW_NUDGE_GAP_SECONDS,
    INBOX_REDRAW_SETTLE_SECONDS,
)

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
        self._cols = _DEFAULT_COLS
        self._rows = _DEFAULT_ROWS
        self._stop = threading.Event()
        self._drain: threading.Thread | None = None
        self._nudge: threading.Thread | None = None

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

    def start(self, *, periodic_nudge: bool = True) -> bool:
        """Attach the headless viewer. Best-effort: returns False on any failure."""
        try:
            cols, rows = self._pane_size()
            self._cols, self._rows = cols, rows
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
            # ``window-size`` is a session option. Pin it only on our short-lived
            # grouped viewer session so the resize nudge never overwrites the
            # real CAO session's operator-selected sizing policy. Killing this
            # viewer session restores everything automatically.
            subprocess.run(
                [
                    "tmux",
                    "set-option",
                    "-t",
                    self._viewer_session,
                    "window-size",
                    "manual",
                ],
                check=False,
                capture_output=True,
            )
            self._drain = threading.Thread(target=self._drain_loop, daemon=True)
            self._drain.start()
            if periodic_nudge:
                self._nudge = threading.Thread(target=self._nudge_loop, daemon=True)
                self._nudge.start()
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

    def _nudge_loop(self) -> None:
        """Periodically resize the window to force a SIGWINCH re-render.

        Attaching a client alone is NOT enough: the CLI paints its idle frame
        once, mixed into the noisy launch output, and then goes quiet — the
        StatusMonitor's chunked read of that burst can miss the idle box and,
        with no further output, never re-evaluates (observed live: viewer
        attached, pane at the idle box, status stuck UNKNOWN for 80s+). A size
        change delivers SIGWINCH to the CLI, which repaints its CURRENT frame
        cleanly; once it has settled to idle that repaint is an unambiguous idle
        box that flows through pipe-pane and flips the status within one tick.
        The short-lived viewer session is pinned to ``window-size manual`` (see
        start), so the resize takes effect regardless of other clients without
        changing the real CAO session. It only runs for the short init window;
        destroying the viewer session removes its temporary sizing policy.
        """
        toggled = False
        while not self._stop.wait(2.5):
            if not self.nudge_once(shrink=toggled):
                break
            toggled = not toggled

    def nudge_once(self, *, shrink: bool = True) -> bool:
        """Force one repaint through the viewer without sending agent input."""
        rows = max(1, self._rows - 1) if shrink else self._rows
        try:
            subprocess.run(
                [
                    "tmux",
                    "resize-window",
                    "-t",
                    f"{self._viewer_session}:{self._window}",
                    "-x",
                    str(self._cols),
                    "-y",
                    str(rows),
                ],
                check=False,
                capture_output=True,
            )
            return True
        except OSError:
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


def nudge_unattended_render(
    session: str,
    window: str,
    *,
    nudge_gap_seconds: float = INBOX_REDRAW_NUDGE_GAP_SECONDS,
    settle_seconds: float = INBOX_REDRAW_SETTLE_SECONDS,
) -> bool:
    """Attach briefly and force one redraw for a quiescent unattended terminal.

    This is the post-init counterpart to :func:`render_during_init`.  It is
    intentionally one-shot: inbox reconciliation applies its own cooldown, and
    a resize redraw is sufficient to make the current idle/completed frame flow
    through tmux ``pipe-pane`` to the StatusMonitor.
    """
    viewer = _RenderViewer(session, window)
    if not viewer.start(periodic_nudge=False):
        return False
    try:
        if not viewer.nudge_once(shrink=True):
            return False
        if nudge_gap_seconds > 0:
            time.sleep(nudge_gap_seconds)
        if not viewer.nudge_once(shrink=False):
            return False
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        return True
    finally:
        viewer.stop()
