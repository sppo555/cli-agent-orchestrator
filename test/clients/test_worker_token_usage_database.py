import sqlite3

import pytest

from cli_agent_orchestrator.clients.database import (
    _migrate_worker_token_usage,
    build_worker_token_usage_filters,
    list_worker_token_usage_page,
    summarize_worker_token_usage,
)
from cli_agent_orchestrator.models.provider import ProviderType


def _seed(db_file, rows):
    with sqlite3.connect(str(db_file)) as conn:
        conn.executemany(
            "INSERT INTO worker_token_usage ("
            "id, terminal_id, provider, agent, run_id, step_id, model, effort, progress, "
            "input_tokens, output_tokens, total_tokens, estimated, recorded_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def test_filter_contract_normalizes_repeated_values_sentinel_and_time(monkeypatch, tmp_path):
    db_file = tmp_path / "filters.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()

    filters = build_worker_token_usage_filters(
        provider=["codex", "codex"],
        model=["__default__"],
        from_at="2026-07-13T00:00:00+08:00",
        to_at="2026-07-13T01:00:00Z",
    )

    assert filters.provider == ("codex",)
    assert filters.model == ("__default__",)
    assert filters.from_at == "2026-07-12T16:00:00+00:00"
    assert filters.to_at == "2026-07-13T01:00:00+00:00"
    assert (
        filters.fingerprint()
        == build_worker_token_usage_filters(
            provider=["codex"], model=["__default__"], from_at=filters.from_at, to_at=filters.to_at
        ).fingerprint()
    )

    with pytest.raises(ValueError):
        build_worker_token_usage_filters(provider=["__default__"])
    with pytest.raises(ValueError):
        build_worker_token_usage_filters(
            from_at="2026-07-14T00:00:00Z", to_at="2026-07-13T00:00:00Z"
        )


def test_page_and_summary_use_sql_aggregates(monkeypatch, tmp_path):
    db_file = tmp_path / "aggregate.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    _seed(
        db_file,
        [
            (
                "old",
                "t",
                "codex",
                "planner",
                None,
                None,
                None,
                None,
                None,
                2,
                3,
                5,
                0,
                "2026-07-12T23:00:00+00:00",
            ),
            (
                "new",
                "t",
                "codex",
                "planner",
                None,
                None,
                "gpt-5",
                "high",
                None,
                7,
                11,
                18,
                1,
                "2026-07-13T01:00:00+00:00",
            ),
        ],
    )
    filters = build_worker_token_usage_filters(provider=["codex"])

    records, has_more = list_worker_token_usage_page(
        filters, snapshot_at="2026-07-13T02:00:00+00:00", limit=1
    )
    summary = summarize_worker_token_usage(filters, snapshot_at="2026-07-13T02:00:00+00:00")

    assert [record["id"] for record in records] == ["new"]
    assert has_more is True
    assert summary["attempts"] == 2
    assert summary["input_tokens"] == 9
    assert summary["output_tokens"] == 14
    assert summary["total_tokens"] == 23
    assert summary["by_model"][0]["value"] == "gpt-5"
    assert summary["by_model"][1]["value"] is None
    providers = {bucket["value"]: bucket for bucket in summary["by_provider"]}
    assert providers["codex"]["attempts"] == 2
    assert providers["codex"]["total_tokens"] == 23
    assert providers["codex"]["native_attempts"] == 1
    assert providers["codex"]["estimated_attempts"] == 1
    assert providers["codex"]["native_tokens"] == 5
    assert providers["codex"]["estimated_tokens"] == 18
    assert providers[ProviderType.ANTIGRAVITY_CLI.value] == {
        "value": ProviderType.ANTIGRAVITY_CLI.value,
        "attempts": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "native_attempts": 0,
        "estimated_attempts": 0,
        "native_tokens": 0,
        "estimated_tokens": 0,
    }
    assert providers[ProviderType.GROK_CLI.value] == {
        "value": ProviderType.GROK_CLI.value,
        "attempts": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert ProviderType.MOCK_CLI.value not in providers


def test_page_query_uses_recorded_keyset_index(monkeypatch, tmp_path):
    db_file = tmp_path / "index.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    _seed(
        db_file,
        [
            (
                str(index),
                "t",
                "codex",
                "agent",
                None,
                None,
                None,
                None,
                None,
                1,
                1,
                2,
                1,
                f"2026-07-13T00:{index % 60:02d}:00+00:00",
            )
            for index in range(1001)
        ],
    )

    with sqlite3.connect(str(db_file)) as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM worker_token_usage "
            "WHERE recorded_at <= ? ORDER BY recorded_at DESC, id DESC LIMIT ?",
            ("2026-07-14T00:00:00+00:00", 100),
        ).fetchall()

    assert "ix_worker_token_usage_recorded" in " ".join(str(row) for row in plan)
