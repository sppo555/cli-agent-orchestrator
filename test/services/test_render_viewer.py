"""Regression tests for the temporary tmux render viewer."""

from unittest.mock import MagicMock, call, patch

from cli_agent_orchestrator.services import terminal_service
from cli_agent_orchestrator.services.render_viewer import _RenderViewer, nudge_unattended_render


def test_render_viewer_scopes_manual_size_to_its_grouped_session():
    """Init rendering must not alter the real CAO session's size policy."""
    viewer = _RenderViewer("cao-main", "developer")

    with (
        patch.object(viewer, "_pane_size", return_value=(120, 40)),
        patch("cli_agent_orchestrator.services.render_viewer.subprocess.run") as mock_run,
        patch("cli_agent_orchestrator.services.render_viewer.subprocess.Popen"),
        patch("cli_agent_orchestrator.services.render_viewer.pty.openpty", return_value=(10, 11)),
        patch("cli_agent_orchestrator.services.render_viewer.fcntl.ioctl"),
        patch("cli_agent_orchestrator.services.render_viewer.os.close"),
        patch("cli_agent_orchestrator.services.render_viewer.threading.Thread"),
    ):
        assert viewer.start() is True

    calls = [call.args[0] for call in mock_run.call_args_list]
    assert ["tmux", "set-option", "-t", viewer._viewer_session, "window-size", "manual"] in calls
    assert not any("set-window-option" in call for call in calls)
    assert not any(f"cao-main:developer" in call and "window-size" in call for call in calls)


def test_unattended_nudge_shrinks_restores_and_always_stops_viewer():
    with patch("cli_agent_orchestrator.services.render_viewer._RenderViewer") as viewer_cls:
        viewer = viewer_cls.return_value
        viewer.start.return_value = True
        viewer.nudge_once.return_value = True

        assert (
            nudge_unattended_render(
                "cao-main", "reviewer", nudge_gap_seconds=0, settle_seconds=0
            )
            is True
        )

        viewer_cls.assert_called_once_with("cao-main", "reviewer")
        viewer.start.assert_called_once_with(periodic_nudge=False)
        assert viewer.nudge_once.call_args_list == [call(shrink=True), call(shrink=False)]
        viewer.stop.assert_called_once_with()


def test_unattended_nudge_start_failure_does_not_stop_unstarted_viewer():
    with patch("cli_agent_orchestrator.services.render_viewer._RenderViewer") as viewer_cls:
        viewer = viewer_cls.return_value
        viewer.start.return_value = False

        assert nudge_unattended_render("cao-main", "reviewer") is False

        viewer.nudge_once.assert_not_called()
        viewer.stop.assert_not_called()


def test_unattended_nudge_failure_still_stops_started_viewer():
    with patch("cli_agent_orchestrator.services.render_viewer._RenderViewer") as viewer_cls:
        viewer = viewer_cls.return_value
        viewer.start.return_value = True
        viewer.nudge_once.return_value = False

        assert nudge_unattended_render("cao-main", "reviewer") is False

        viewer.stop.assert_called_once_with()


def test_terminal_nudge_skips_event_driven_backend():
    with (
        patch.object(terminal_service, "get_backend") as get_backend,
        patch.object(terminal_service, "get_terminal_metadata") as get_metadata,
        patch.object(terminal_service, "nudge_unattended_render") as nudge,
    ):
        get_backend.return_value.supports_event_inbox.return_value = True

        assert terminal_service.nudge_terminal_render("worker-1") is False

        get_metadata.assert_not_called()
        nudge.assert_not_called()


def test_terminal_nudge_resolves_tmux_target_from_metadata():
    with (
        patch.object(terminal_service, "get_backend") as get_backend,
        patch.object(terminal_service, "get_terminal_metadata") as get_metadata,
        patch.object(terminal_service, "nudge_unattended_render", return_value=True) as nudge,
    ):
        get_backend.return_value.supports_event_inbox.return_value = False
        get_metadata.return_value = {"tmux_session": "cao-main", "tmux_window": "reviewer"}

        assert terminal_service.nudge_terminal_render("worker-1") is True

        nudge.assert_called_once_with("cao-main", "reviewer")
