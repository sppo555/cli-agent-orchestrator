"""Regression tests for the temporary tmux render viewer."""

import asyncio
from unittest.mock import MagicMock, call, patch

import pytest

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
            nudge_unattended_render("cao-main", "reviewer", nudge_gap_seconds=0, settle_seconds=0)
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


@pytest.mark.asyncio
async def test_deferred_init_uses_shared_headless_render_path():
    """The non-blocking assign path must not bypass unattended rendering."""
    provider = MagicMock()
    provider.shell_baseline = None

    with patch.object(
        terminal_service,
        "_initialize_provider_with_render",
        new_callable=MagicMock,
    ) as initialize:
        initialize.return_value = asyncio.sleep(0)
        terminal_service._schedule_deferred_init(provider, "worker-1", None, None, None)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    initialize.assert_called_once_with(provider)


@pytest.mark.asyncio
async def test_initialize_provider_with_render_wraps_tmux_and_cleans_up_on_success():
    provider = MagicMock(session_name="cao-main", window_name="developer")
    provider.initialize.return_value = asyncio.sleep(0)
    viewer = MagicMock()

    with (
        patch.object(terminal_service, "get_backend") as get_backend,
        patch.object(terminal_service, "render_during_init", return_value=viewer) as render,
    ):
        get_backend.return_value.supports_event_inbox.return_value = False
        await terminal_service._initialize_provider_with_render(provider)

    render.assert_called_once_with("cao-main", "developer")
    viewer.__enter__.assert_called_once_with()
    viewer.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_initialize_provider_with_render_cleans_up_tmux_on_failure():
    provider = MagicMock(session_name="cao-main", window_name="developer")
    provider.initialize.side_effect = RuntimeError("init failed")
    viewer = MagicMock()

    with (
        patch.object(terminal_service, "get_backend") as get_backend,
        patch.object(terminal_service, "render_during_init", return_value=viewer),
        pytest.raises(RuntimeError, match="init failed"),
    ):
        get_backend.return_value.supports_event_inbox.return_value = False
        await terminal_service._initialize_provider_with_render(provider)

    viewer.__enter__.assert_called_once_with()
    assert viewer.__exit__.call_count == 1
    assert viewer.__exit__.call_args.args[0] is RuntimeError


@pytest.mark.asyncio
async def test_initialize_provider_with_render_skips_tmux_for_event_backend():
    provider = MagicMock(session_name="herdr-session", window_name="developer")
    provider.initialize.return_value = asyncio.sleep(0)

    with (
        patch.object(terminal_service, "get_backend") as get_backend,
        patch.object(terminal_service, "render_during_init") as render,
    ):
        get_backend.return_value.supports_event_inbox.return_value = True
        await terminal_service._initialize_provider_with_render(provider)

    render.assert_not_called()
