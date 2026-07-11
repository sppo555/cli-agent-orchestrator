"""Regression tests for the temporary tmux render viewer."""

from unittest.mock import MagicMock, patch

from cli_agent_orchestrator.services.render_viewer import _RenderViewer


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
