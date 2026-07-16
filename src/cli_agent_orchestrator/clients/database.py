"""Minimal database client with only terminal metadata."""

import logging
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, declarative_base, sessionmaker

from cli_agent_orchestrator.constants import DATABASE_URL, DB_DIR, DEFAULT_PROVIDER
from cli_agent_orchestrator.models.flow import Flow
from cli_agent_orchestrator.models.inbox import InboxMessage, MessageStatus

logger = logging.getLogger(__name__)

Base: Any = declarative_base()


class TerminalModel(Base):
    """SQLAlchemy model for terminal metadata only."""

    __tablename__ = "terminals"

    id = Column(String, primary_key=True)  # "abc123ef"
    tmux_session = Column(String, nullable=False)  # "cao-session-name"
    tmux_window = Column(String, nullable=False)  # "window-name"
    provider = Column(String, nullable=False)  # "kiro_cli", "claude_code"
    agent_profile = Column(String)  # "developer", "reviewer" (optional)
    allowed_tools = Column(String, nullable=True)  # JSON-encoded list of CAO tool names
    shell_command = Column(String, nullable=True)  # shell process name captured before kiro launch
    caller_id = Column(String, nullable=True)  # terminal that created this one (callback target)
    last_active = Column(DateTime, default=datetime.now)


class InboxModel(Base):
    """SQLAlchemy model for inbox messages."""

    __tablename__ = "inbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String, nullable=False)
    receiver_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    status = Column(String, nullable=False)  # MessageStatus enum value
    created_at = Column(DateTime, default=datetime.now)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryMetadataModel(Base):
    """SQLAlchemy model for memory metadata (Phase 2 U1).

    SQLite is the source of truth for metadata queries; wiki markdown
    files remain the content store. Each row corresponds to exactly one
    wiki file on disk.
    """

    __tablename__ = "memory_metadata"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String, nullable=False)
    memory_type = Column(String, nullable=False)
    scope = Column(String, nullable=False)
    scope_id = Column(String, nullable=True)
    file_path = Column(String, nullable=False)
    tags = Column(String, nullable=False, default="")
    source_provider = Column(String, nullable=True)
    source_terminal_id = Column(String, nullable=True)
    token_estimate = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    # 3-factor scoring. ``access_count`` feeds the usage factor;
    # ``last_accessed_at`` backs a server-side rate-limit on increments. NOT
    # NULL DEFAULT 0 so existing rows read as "never recalled" without a
    # backfill. Migrated onto existing DBs by ``_migrate_add_access_count``.
    access_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_accessed_at = Column(DateTime(timezone=True), nullable=True, default=None)
    # LLM wiki compilation. NULL = never LLM-compiled (pre-existing rows, or
    # every compile attempt fell back to append). Non-NULL = UTC timestamp of
    # the last successful compile.
    last_compiled_at = Column(DateTime(timezone=True), nullable=True, default=None)
    # Comma-separated sanitised keys of cross-referenced articles. NULL =
    # never computed (pre-existing rows or LLM error). ``""`` = computed, no
    # related found (success — distinct from NULL to avoid endless retries).
    # Practical max ≤ 256 bytes (3 keys × 60 chars + 2 commas). The CHECK
    # constraint applies on FRESH databases only — existing DBs rely on the
    # parse-side cap in ``_parse_related_keys``.
    related_keys = Column(Text, nullable=True, default=None)

    __table_args__ = (
        UniqueConstraint("key", "scope", "scope_id", name="uq_memory_key_scope"),
        CheckConstraint(
            "related_keys IS NULL OR length(related_keys) < 1024",
            name="ck_related_keys_length",
        ),
    )


class ProjectAliasModel(Base):
    """SQLAlchemy model for project identity aliases (Phase 2.5 U6).

    Maps historical/alternate project identifiers (cwd hashes, manual labels)
    to a canonical ``project_id`` so memory recall survives directory rename
    and worktree layouts.
    """

    __tablename__ = "project_aliases"

    # ``alias`` is the sole primary key: an alias maps to exactly one canonical
    # project_id, so reverse lookups (get_project_id_by_alias) are stable. A
    # cwd-hash first resolved via an override and later via its git remote
    # upserts the same row rather than creating a second, ambiguous mapping.
    alias = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)  # "git_remote" | "cwd_hash" | "manual"
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class FlowModel(Base):
    """SQLAlchemy model for flow metadata."""

    __tablename__ = "flows"

    name = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    schedule = Column(String, nullable=False)
    agent_profile = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    script = Column(String, nullable=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)


def _ensure_db_dir() -> None:
    """Create the DB dir owner-only (0o700).

    The DB stores sensitive data (workflow spec_snapshot carries full prompt
    bodies + inputs_json), so the dir is owner-only — the same posture as
    claude_code prompt files (0o600) and the audit log (0o700/0o600). mkdir's
    mode is ignored when the dir already exists (exist_ok) and is masked by
    umask on creation — the chmod enforces 0o700 in both cases, best-effort.
    """
    DB_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(DB_DIR, 0o700)
    except OSError as e:
        logger.warning(f"Could not restrict DB dir permissions on {DB_DIR}: {e}")


# Module-level singletons
_ensure_db_dir()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables and apply schema migrations."""
    _migrate_project_aliases_schema()
    Base.metadata.create_all(bind=engine)
    _restrict_db_file_permissions()
    _migrate_terminals_schema()
    _migrate_memory_indexes()
    _migrate_add_access_count()
    _migrate_add_last_compiled_at()
    _migrate_add_related_keys()
    _migrate_workflow_index()
    _migrate_workflow_run()
    _migrate_workflow_run_step()
    _migrate_worker_token_usage()


def _restrict_db_file_permissions() -> None:
    """Chmod the SQLite file (+ -wal/-shm siblings if present) to 0o600.

    The DB persists sensitive data (workflow spec_snapshot prompt bodies,
    inputs_json), matching the owner-only posture of prompt files and the audit
    log. Called after ``create_all`` so the file exists. Best-effort: a chmod
    failure (exotic filesystems) degrades permissions only, never blocks startup.
    """
    from cli_agent_orchestrator.constants import DATABASE_FILE

    for path in (
        DATABASE_FILE,
        DATABASE_FILE.with_name(DATABASE_FILE.name + "-wal"),
        DATABASE_FILE.with_name(DATABASE_FILE.name + "-shm"),
    ):
        if not path.exists():
            continue
        try:
            os.chmod(path, 0o600)
        except OSError as e:
            logger.warning(f"Could not restrict DB file permissions on {path}: {e}")


def _migrate_project_aliases_schema() -> None:
    """Rebuild project_aliases if it predates the alias-only primary key.

    The table originally used a composite PK ``(project_id, alias)``, which
    allowed one alias to map to several project_ids and made reverse lookups
    nondeterministic. The new schema keys on ``alias`` alone. SQLite cannot
    alter a primary key in place, so drop and recreate. The table is an
    opportunistic identity cache rebuilt by ``resolve_project_id`` on demand,
    so dropping rows is safe. Runs before ``create_all`` so the fresh schema
    is created with the new PK.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master " "WHERE type='table' AND name='project_aliases'"
            ).fetchone()
            if row is None:
                return  # table doesn't exist yet — create_all builds it fresh
            cols = conn.execute("PRAGMA table_info(project_aliases)").fetchall()
            # PRAGMA returns rows: (cid, name, type, notnull, dflt_value, pk).
            # In the legacy schema both project_id and alias have pk>0; in the
            # new schema only alias does.
            pk_cols = {c[1] for c in cols if c[5]}
            if pk_cols != {"alias"}:
                conn.execute("DROP TABLE project_aliases")
                conn.commit()
                logger.info("Migration: rebuilt project_aliases with alias-only primary key")
    except Exception as e:
        logger.debug(f"project_aliases migration skipped: {e}")


def _migrate_memory_indexes() -> None:
    """Add explicit indexes on memory_metadata for query performance."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_metadata (scope, scope_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_updated ON memory_metadata (updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_metadata (memory_type)"
            )
    except Exception as e:
        logger.debug(f"Memory index migration skipped: {e}")


def _migrate_add_access_count() -> None:
    """Add access_count and last_accessed_at columns to memory_metadata if missing.

    Idempotent: PRAGMA table_info gate, ALTER TABLE ADD COLUMN only
    when missing. Fresh DBs already have the columns from
    ``Base.metadata.create_all``. Existing rows get ``0`` / ``NULL`` — the
    correct values for "never recalled".
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            cursor = conn.execute("PRAGMA table_info(memory_metadata)")
            columns = {row[1] for row in cursor.fetchall()}
            if "access_count" not in columns:
                conn.execute(
                    "ALTER TABLE memory_metadata ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
                )
                logger.info("Migration: added access_count column to memory_metadata")
            if "last_accessed_at" not in columns:
                conn.execute("ALTER TABLE memory_metadata ADD COLUMN last_accessed_at DATETIME")
                logger.info("Migration: added last_accessed_at column to memory_metadata")
    except Exception as e:
        logger.debug(f"Migration check for access_count failed: {e}")


def _migrate_add_last_compiled_at() -> None:
    """Add last_compiled_at column to memory_metadata if missing.

    Idempotent: skipped on fresh DBs (the column ships in the model) and on
    repeated runs. Existing Phase 1/2 rows get NULL — correct, since they were
    never LLM-compiled.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            cursor = conn.execute("PRAGMA table_info(memory_metadata)")
            columns = {row[1] for row in cursor.fetchall()}
            if "last_compiled_at" not in columns:
                conn.execute("ALTER TABLE memory_metadata ADD COLUMN last_compiled_at DATETIME")
                logger.info("Migration: added last_compiled_at column to memory_metadata")
    except Exception as e:
        logger.debug(f"Migration check for last_compiled_at failed: {e}")


def _migrate_add_related_keys() -> None:
    """Add related_keys column to memory_metadata if missing.

    Reuses the idempotent ALTER pattern: PRAGMA table_info gate, ALTER TABLE
    ADD COLUMN only when missing. The CHECK(length < 1024) constraint applies
    to FRESH DBs only — adding a CHECK to an existing SQLite table requires a
    full table rebuild we deliberately avoid. Existing DBs rely on the
    parse-side 1024-byte cap in ``_parse_related_keys``.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            cursor = conn.execute("PRAGMA table_info(memory_metadata)")
            columns = {row[1] for row in cursor.fetchall()}
            if "related_keys" not in columns:
                conn.execute("ALTER TABLE memory_metadata ADD COLUMN related_keys TEXT")
                logger.info("Migration: added related_keys column to memory_metadata")
    except Exception as e:
        logger.debug(f"Migration check for related_keys failed: {e}")


def _migrate_workflow_index() -> None:
    """Create/upgrade the derived ``workflow_index`` table (issue #312, N2).

    The table is a **derived, non-authoritative** projection of the workflow
    spec YAML files on disk (B2-BR-2): it can be dropped and rebuilt
    byte-identically from the files alone (``rebuild_index_from_files``). It
    carries no run/execution state — runs and per-step state are N5/N6.

    Idempotent (``CREATE TABLE IF NOT EXISTS``), zero-arg and self-connecting —
    mirrors the existing ``_migrate_memory_indexes`` pattern. Failure is logged
    at debug and never propagated (a missing index table is recoverable: the
    next ``list`` rebuilds it).

    U5 additively widens ``step_count`` to nullable: script-tier rows carry
    NULL (step count is run-time-determined, unknowable at index time), while
    YAML rows keep populating an int. ``CREATE TABLE IF NOT EXISTS`` only
    covers fresh DBs — on a pre-U5 DB the column already exists as NOT NULL,
    and SQLite cannot ``ALTER COLUMN`` to relax a NOT NULL constraint in
    place. Same drop/rebuild precedent as ``_migrate_project_aliases_schema``:
    the table is fully derived, so dropping it is safe — the next ``list``
    rebuilds it from the workflow files on disk.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_index'"
            ).fetchone()
            if row is not None:
                cols = conn.execute("PRAGMA table_info(workflow_index)").fetchall()
                # PRAGMA row: (cid, name, type, notnull, dflt_value, pk).
                step_count_col = next((c for c in cols if c[1] == "step_count"), None)
                if step_count_col is not None and step_count_col[3]:  # notnull flag set
                    conn.execute("DROP TABLE workflow_index")
                    conn.commit()
                    logger.info(
                        "Migration: rebuilt workflow_index with nullable step_count "
                        "(dropped legacy table; rebuilt from workflow files on next list)"
                    )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS workflow_index ("
                "name TEXT PRIMARY KEY, "
                "source_path TEXT NOT NULL, "
                "mode TEXT NOT NULL, "
                "step_count INTEGER, "  # nullable: script-tier rows carry NULL
                "description TEXT NOT NULL DEFAULT '', "
                "indexed_at TEXT NOT NULL"
                ")"
            )
    except Exception as e:  # noqa: BLE001 — derived table; rebuilt on next list
        logger.debug(f"workflow_index migration skipped: {e}")


def _migrate_workflow_run() -> None:
    """Create the durable ``workflow_run`` journal table if missing (issue #312, N6).

    The run aggregate root: one row per run, keyed by ``run_id`` (E1,
    domain-entities). Per Q1=B this is the **source of truth** for run execution
    state; the Bolt-3 in-memory ``run_registry`` is a cache over it. No loop
    columns (``iteration_counter`` etc.) — deferred to N8 (Q4=B, B4-BR-12).

    Idempotent (``CREATE TABLE IF NOT EXISTS``), zero-arg and self-connecting —
    mirrors ``_migrate_workflow_index`` (B2, B4-BR-1). Failure is logged at debug
    and never propagated: a missing table is recoverable, the next write retries
    the path and the live run completes on the in-memory floor (B4-RD-4).

    U3 (issue #312, script-tier journal extension) additively appends two
    columns — ``tier`` and ``generation`` (E1, domain-entities) — via the same
    idempotent ``PRAGMA table_info`` gate used by ``_migrate_add_access_count`` /
    ``_migrate_add_related_keys``. Both default to values that make a pre-U3 /
    YAML row read identically to its pre-extension form (INV-1/INV-2): existing
    rows back-fill to ``tier='yaml'``, ``generation='1'``. ``generation`` is TEXT,
    not INTEGER, so it compares byte-identically against the env-var-transported
    string generation value (domain-entities B4 fix).
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS workflow_run ("
                "run_id TEXT PRIMARY KEY, "
                "workflow_name TEXT NOT NULL, "
                "spec_snapshot TEXT NOT NULL, "
                "inputs_json TEXT NOT NULL, "
                "state TEXT NOT NULL, "
                "current_step_id TEXT, "
                "started_at TEXT NOT NULL, "
                "finished_at TEXT"
                ")"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(workflow_run)")}
            if "tier" not in columns:
                conn.execute(
                    "ALTER TABLE workflow_run ADD COLUMN tier TEXT NOT NULL DEFAULT 'yaml'"
                )
                logger.info("Migration: added tier column to workflow_run")
            if "generation" not in columns:
                conn.execute(
                    "ALTER TABLE workflow_run ADD COLUMN generation TEXT NOT NULL DEFAULT '1'"
                )
                logger.info("Migration: added generation column to workflow_run")
    except Exception as e:  # noqa: BLE001 — derived/recoverable; logged at debug (B4-RD-4)
        logger.debug(f"workflow_run migration skipped: {e}")


def _migrate_workflow_run_step() -> None:
    """Create the durable ``workflow_run_step`` table if missing (issue #312, N6).

    Per-step durable state: one row per ``(run_id, step_id)`` (E2,
    domain-entities). ``reprompted``/``terminal_id`` are deliberately NOT
    journaled (F3) — they are in-memory-only and defaulted on rebuild. No
    ``which_guard_fired``/``iterations_run`` columns — N8 adds them via its own
    additive migrator (Q4=B, B4-BR-12).

    Idempotent, zero-arg, self-connecting; failure logged at debug and never
    propagated (B4-BR-1 / B4-RD-4), same precedent as ``_migrate_workflow_index``.

    U3 (issue #312, script-tier journal extension) additively appends
    ``call_fingerprint`` (E2, domain-entities) via the same idempotent
    ``PRAGMA table_info`` gate. Defaults to ``NULL`` so a pre-U3 / YAML row is
    indistinguishable from its pre-extension form (INV-1/INV-2); ``append_step``
    is the sole write path for the column (``update_step`` stays untouched — the
    fingerprint is set once, at the RUNNING insert).
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS workflow_run_step ("
                "run_id TEXT NOT NULL, "
                "step_id TEXT NOT NULL, "
                "state TEXT NOT NULL, "
                "attempts INTEGER NOT NULL, "
                "output_json TEXT, "
                "error TEXT, "
                "updated_at TEXT NOT NULL, "
                "PRIMARY KEY (run_id, step_id)"
                ")"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(workflow_run_step)")}
            if "call_fingerprint" not in columns:
                conn.execute(
                    "ALTER TABLE workflow_run_step ADD COLUMN call_fingerprint TEXT DEFAULT NULL"
                )
                logger.info("Migration: added call_fingerprint column to workflow_run_step")
    except Exception as e:  # noqa: BLE001 — derived/recoverable; logged at debug (B4-RD-4)
        logger.debug(f"workflow_run_step migration skipped: {e}")


def _migrate_worker_token_usage() -> None:
    """Create the durable per-worker token usage table if missing.

    Usage rows intentionally contain metadata and counts only — never prompts,
    responses, or terminal transcripts. Each completed worker attempt gets its
    own row, so retries and workers whose terminals were deleted remain
    inspectable.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        with sqlite3.connect(str(DATABASE_FILE)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS worker_token_usage ("
                "id TEXT PRIMARY KEY, "
                "terminal_id TEXT NOT NULL, "
                "provider TEXT NOT NULL, "
                "agent TEXT NOT NULL, "
                "run_id TEXT, "
                "step_id TEXT, "
                "model TEXT, "
                "effort TEXT, "
                "progress TEXT, "
                "input_tokens INTEGER NOT NULL, "
                "output_tokens INTEGER NOT NULL, "
                "total_tokens INTEGER NOT NULL, "
                "estimated INTEGER NOT NULL DEFAULT 1, "
                "recorded_at TEXT NOT NULL"
                ")"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(worker_token_usage)")}
            for column in ("model", "effort", "progress"):
                if column not in columns:
                    conn.execute(f"ALTER TABLE worker_token_usage ADD COLUMN {column} TEXT")
                    logger.info("Migration: added %s column to worker_token_usage", column)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_worker_token_usage_terminal "
                "ON worker_token_usage (terminal_id, recorded_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_worker_token_usage_run_step "
                "ON worker_token_usage (run_id, step_id, recorded_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_worker_token_usage_recorded "
                "ON worker_token_usage (recorded_at DESC, id DESC)"
            )
    except Exception as e:  # noqa: BLE001 — recoverable; the worker path is best-effort
        logger.debug(f"worker_token_usage migration skipped: {e}")


def _migrate_terminals_schema() -> None:
    """Add allowed_tools and shell_command columns to terminals table if missing (schema migration)."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.execute("PRAGMA table_info(terminals)")
        columns = {row[1] for row in cursor.fetchall()}
        if "allowed_tools" not in columns:
            conn.execute("ALTER TABLE terminals ADD COLUMN allowed_tools TEXT")
            conn.commit()
            logger.info("Migration: added allowed_tools column to terminals table")
        if "shell_command" not in columns:
            conn.execute("ALTER TABLE terminals ADD COLUMN shell_command TEXT")
            conn.commit()
            logger.info("Migration: added shell_command column to terminals table")
        if "caller_id" not in columns:
            conn.execute("ALTER TABLE terminals ADD COLUMN caller_id TEXT")
            conn.commit()
            logger.info("Migration: added caller_id column to terminals table")
        conn.close()
    except Exception as e:
        logger.warning(f"Migration check for terminals schema failed: {e}")


def record_worker_token_usage(
    *,
    terminal_id: str,
    provider: str,
    agent: str,
    usage: Any,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    progress: Optional[str] = None,
    record_id: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> str:
    """Persist one completed worker attempt and return its id.

    The optional replay fields support durable spool recovery. INSERT OR
    IGNORE makes replay idempotent after a crash between SQLite commit and
    spool acknowledgement.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    record_id = record_id or str(uuid.uuid4())
    recorded_at = recorded_at or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(DATABASE_FILE)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO worker_token_usage ("
            "id, terminal_id, provider, agent, run_id, step_id, model, effort, "
            "progress, input_tokens, output_tokens, total_tokens, estimated, recorded_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                terminal_id,
                provider,
                agent,
                run_id,
                step_id,
                usage.model,
                usage.effort,
                progress if progress is not None else usage.progress,
                usage.input_tokens,
                usage.output_tokens,
                usage.total_tokens,
                int(usage.estimated),
                recorded_at,
            ),
        )
    return record_id


def list_worker_token_usage(
    *,
    terminal_id: Optional[str] = None,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List durable worker usage records, newest first."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    limit = max(1, min(limit, 1000))
    clauses: List[str] = []
    values: List[Any] = []
    for column, value in (("terminal_id", terminal_id), ("run_id", run_id), ("step_id", step_id)):
        if value is not None:
            clauses.append(f"{column} = ?")
            values.append(value)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(str(DATABASE_FILE)) as conn:
        rows = conn.execute(
            "SELECT id, terminal_id, provider, agent, run_id, step_id, model, effort, "
            f"progress, input_tokens, output_tokens, total_tokens, estimated, recorded_at "
            f"FROM worker_token_usage{where} ORDER BY recorded_at DESC, id DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
    return [
        {
            "id": row[0],
            "terminal_id": row[1],
            "provider": row[2],
            "agent": row[3],
            "run_id": row[4],
            "step_id": row[5],
            "model": row[6],
            "effort": row[7],
            "progress": row[8],
            "input_tokens": row[9],
            "output_tokens": row[10],
            "total_tokens": row[11],
            "estimated": bool(row[12]),
            "recorded_at": row[13],
        }
        for row in rows
    ]


_TOKEN_USAGE_FILTER_FIELDS = ("provider", "agent", "model", "effort")
_TOKEN_USAGE_NULLABLE_FIELDS = {"model", "effort"}
_TOKEN_USAGE_DEFAULT_SENTINEL = "__default__"
_TOKEN_USAGE_MAX_FILTER_VALUES = 25
_TOKEN_USAGE_MAX_FILTER_VALUE_LENGTH = 200


@dataclass(frozen=True)
class WorkerTokenUsageFilters:
    """Normalized filters shared by token usage page and summary queries."""

    provider: Tuple[str, ...] = ()
    agent: Tuple[str, ...] = ()
    model: Tuple[str, ...] = ()
    effort: Tuple[str, ...] = ()
    from_at: Optional[str] = None
    to_at: Optional[str] = None

    def fingerprint(self) -> str:
        payload = {
            "provider": self.provider,
            "agent": self.agent,
            "model": self.model,
            "effort": self.effort,
            "from": self.from_at,
            "to": self.to_at,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_worker_token_usage_timestamp(value: Optional[str], name: str) -> Optional[str]:
    """Validate and normalize a user-provided ISO-8601 UTC timestamp."""
    if value is None:
        return None
    if not value or len(value) > _TOKEN_USAGE_MAX_FILTER_VALUE_LENGTH:
        raise ValueError(f"{name} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def build_worker_token_usage_filters(
    *,
    provider: Optional[Sequence[str]] = None,
    agent: Optional[Sequence[str]] = None,
    model: Optional[Sequence[str]] = None,
    effort: Optional[Sequence[str]] = None,
    from_at: Optional[str] = None,
    to_at: Optional[str] = None,
) -> WorkerTokenUsageFilters:
    """Normalize and validate the shared page/summary filter contract."""

    normalized: Dict[str, Tuple[str, ...]] = {}
    for field in _TOKEN_USAGE_FILTER_FIELDS:
        raw_values = list(locals()[field] or [])
        if len(raw_values) > _TOKEN_USAGE_MAX_FILTER_VALUES:
            raise ValueError(f"{field} has too many values")
        values = []
        for value in raw_values:
            if not value or len(value) > _TOKEN_USAGE_MAX_FILTER_VALUE_LENGTH:
                raise ValueError(f"{field} contains an invalid value")
            if value == _TOKEN_USAGE_DEFAULT_SENTINEL and field not in _TOKEN_USAGE_NULLABLE_FIELDS:
                raise ValueError(f"{_TOKEN_USAGE_DEFAULT_SENTINEL} is not valid for {field}")
            if value not in values:
                values.append(value)
        normalized[field] = tuple(sorted(values))

    normalized_from = normalize_worker_token_usage_timestamp(from_at, "from")
    normalized_to = normalize_worker_token_usage_timestamp(to_at, "to")
    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise ValueError("from must not be later than to")
    return WorkerTokenUsageFilters(
        provider=normalized["provider"],
        agent=normalized["agent"],
        model=normalized["model"],
        effort=normalized["effort"],
        from_at=normalized_from,
        to_at=normalized_to,
    )


def _worker_token_usage_where(
    filters: WorkerTokenUsageFilters,
    *,
    snapshot_at: Optional[str] = None,
    boundary: Optional[Tuple[str, str]] = None,
) -> Tuple[str, List[Any]]:
    """Build a parameterized WHERE clause for token usage reads."""
    clauses: List[str] = []
    values: List[Any] = []
    for field in _TOKEN_USAGE_FILTER_FIELDS:
        selected = getattr(filters, field)
        if not selected:
            continue
        ordinary = [value for value in selected if value != _TOKEN_USAGE_DEFAULT_SENTINEL]
        field_clauses: List[str] = []
        if ordinary:
            placeholders = ", ".join("?" for _ in ordinary)
            field_clauses.append(f"{field} IN ({placeholders})")
            values.extend(ordinary)
        if _TOKEN_USAGE_DEFAULT_SENTINEL in selected:
            field_clauses.append(f"{field} IS NULL")
        clauses.append(f"({' OR '.join(field_clauses)})")
    if filters.from_at:
        clauses.append("recorded_at >= ?")
        values.append(filters.from_at)
    if filters.to_at:
        clauses.append("recorded_at <= ?")
        values.append(filters.to_at)
    if snapshot_at:
        clauses.append("recorded_at <= ?")
        values.append(snapshot_at)
    if boundary:
        last_recorded_at, last_id = boundary
        clauses.append("(recorded_at < ? OR (recorded_at = ? AND id < ?))")
        values.extend([last_recorded_at, last_recorded_at, last_id])
    return (f" WHERE {' AND '.join(clauses)}" if clauses else ""), values


def _worker_token_usage_record(row: Sequence[Any]) -> Dict[str, Any]:
    return {
        "id": row[0],
        "terminal_id": row[1],
        "provider": row[2],
        "agent": row[3],
        "run_id": row[4],
        "step_id": row[5],
        "model": row[6],
        "effort": row[7],
        "progress": row[8],
        "input_tokens": row[9],
        "output_tokens": row[10],
        "total_tokens": row[11],
        "estimated": bool(row[12]),
        "recorded_at": row[13],
    }


def list_worker_token_usage_page(
    filters: WorkerTokenUsageFilters,
    *,
    snapshot_at: str,
    boundary: Optional[Tuple[str, str]] = None,
    limit: int = 100,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Read one stable keyset page and indicate whether another page exists."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    limit = max(1, min(limit, 500))
    where, values = _worker_token_usage_where(filters, snapshot_at=snapshot_at, boundary=boundary)
    with sqlite3.connect(str(DATABASE_FILE)) as conn:
        rows = conn.execute(
            "SELECT id, terminal_id, provider, agent, run_id, step_id, model, effort, "
            f"progress, input_tokens, output_tokens, total_tokens, estimated, recorded_at "
            f"FROM worker_token_usage{where} ORDER BY recorded_at DESC, id DESC LIMIT ?",
            (*values, limit + 1),
        ).fetchall()
    has_more = len(rows) > limit
    return [_worker_token_usage_record(row) for row in rows[:limit]], has_more


def _worker_token_usage_aggregate(
    conn: Any,
    *,
    where: str,
    values: Sequence[Any],
    group_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    group_clause = f" GROUP BY {group_by} ORDER BY SUM(total_tokens) DESC" if group_by else ""
    rows = conn.execute(
        "SELECT "
        + (f"{group_by}, " if group_by else "")
        + "COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
        + "COALESCE(SUM(total_tokens), 0) FROM worker_token_usage"
        + where
        + group_clause,
        tuple(values),
    ).fetchall()
    if group_by:
        return [
            {
                "value": row[0],
                "attempts": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
                "total_tokens": row[4],
            }
            for row in rows
        ]
    return [
        {
            "attempts": row[0],
            "input_tokens": row[1],
            "output_tokens": row[2],
            "total_tokens": row[3],
        }
        for row in rows
    ]


def summarize_worker_token_usage(
    filters: WorkerTokenUsageFilters,
    *,
    snapshot_at: str,
) -> Dict[str, Any]:
    """Return aggregate and grouped usage without loading records into Python."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    where, values = _worker_token_usage_where(filters, snapshot_at=snapshot_at)
    with sqlite3.connect(str(DATABASE_FILE)) as conn:
        totals = _worker_token_usage_aggregate(conn, where=where, values=values)[0]
        daily = conn.execute(
            "SELECT substr(recorded_at, 1, 10), COUNT(*), COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0), COALESCE(SUM(total_tokens), 0) "
            f"FROM worker_token_usage{where} GROUP BY substr(recorded_at, 1, 10) "
            "ORDER BY substr(recorded_at, 1, 10) ASC",
            tuple(values),
        ).fetchall()
        grouped = {
            field: _worker_token_usage_aggregate(
                conn, where=where, values=values, group_by=field
            )
            for field in ("provider", "agent", "model", "effort")
        }
    return {
        **totals,
        "daily": [
            {
                "value": row[0],
                "attempts": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
                "total_tokens": row[4],
            }
            for row in daily
        ],
        "by_provider": grouped["provider"],
        "by_agent": grouped["agent"],
        "by_model": grouped["model"],
        "by_effort": grouped["effort"],
        "snapshot_at": snapshot_at,
    }


def get_worker_token_usage_totals(run_id: str) -> Dict[str, Dict[str, Any]]:
    """Aggregate persisted usage by workflow step for status snapshots."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    with sqlite3.connect(str(DATABASE_FILE)) as conn:
        rows = conn.execute(
            "SELECT step_id, SUM(input_tokens), SUM(output_tokens), SUM(total_tokens), "
            "MIN(model), MIN(effort), MAX(progress), MIN(estimated) "
            "FROM worker_token_usage WHERE run_id = ? AND step_id IS NOT NULL "
            "GROUP BY step_id",
            (run_id,),
        ).fetchall()
    return {
        row[0]: {
            "input_tokens": row[1] or 0,
            "output_tokens": row[2] or 0,
            "total_tokens": row[3] or 0,
            "model": row[4],
            "effort": row[5],
            "progress": row[6],
            "estimated": bool(row[7]),
        }
        for row in rows
    }


def create_terminal(
    terminal_id: str,
    tmux_session: str,
    tmux_window: str,
    provider: str,
    agent_profile: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    shell_command: Optional[str] = None,
    caller_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create terminal metadata record."""
    import json as _json

    with SessionLocal() as db:
        terminal = TerminalModel(
            id=terminal_id,
            tmux_session=tmux_session,
            tmux_window=tmux_window,
            provider=provider,
            agent_profile=agent_profile,
            allowed_tools=_json.dumps(allowed_tools) if allowed_tools else None,
            shell_command=shell_command,
            caller_id=caller_id,
        )
        db.add(terminal)
        db.commit()
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_profile": terminal.agent_profile,
            "allowed_tools": allowed_tools,
            "shell_command": terminal.shell_command,
            "caller_id": terminal.caller_id,
        }


def get_terminal_metadata(terminal_id: str) -> Optional[Dict[str, Any]]:
    """Get terminal metadata by ID."""
    import json as _json

    with SessionLocal() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if not terminal:
            logger.warning(f"Terminal metadata not found for terminal_id: {terminal_id}")
            return None
        logger.debug(
            f"Retrieved terminal metadata for {terminal_id}: provider={terminal.provider}, session={terminal.tmux_session}"
        )
        allowed_tools = _json.loads(terminal.allowed_tools) if terminal.allowed_tools else None
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_profile": terminal.agent_profile,
            "allowed_tools": allowed_tools,
            "shell_command": terminal.shell_command,
            "caller_id": terminal.caller_id,
            "last_active": terminal.last_active,
        }


def list_terminals_by_session(tmux_session: str) -> List[Dict[str, Any]]:
    """List all terminals in a tmux session."""
    with SessionLocal() as db:
        terminals = db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_profile": t.agent_profile,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def update_last_active(terminal_id: str) -> bool:
    """Update last active timestamp."""
    with SessionLocal() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if terminal:
            terminal.last_active = datetime.now()
            db.commit()
            return True
        return False


def update_terminal_shell_command(terminal_id: str, shell_command: str) -> bool:
    """Update the shell_command baseline for a terminal."""
    with SessionLocal() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if terminal:
            terminal.shell_command = shell_command
            db.commit()
            return True
        return False


def list_all_terminals() -> List[Dict[str, Any]]:
    """List all terminals."""
    with SessionLocal() as db:
        terminals = db.query(TerminalModel).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_profile": t.agent_profile,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def list_pending_receiver_ids_by_provider(provider: str) -> List[str]:
    """List receiver terminal IDs with pending messages for a specific provider."""
    with SessionLocal() as db:
        rows = (
            db.query(InboxModel.receiver_id)
            .join(TerminalModel, TerminalModel.id == InboxModel.receiver_id)
            .filter(
                TerminalModel.provider == provider,
                InboxModel.status == MessageStatus.PENDING.value,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows]


def list_pending_receiver_ids_older_than(min_age_seconds: int) -> List[str]:
    """List receiver terminal IDs whose messages have been PENDING too long.

    Returns the distinct receivers of any message still PENDING for longer than
    ``min_age_seconds``. Used by the inbox reconciliation sweep to find messages
    the immediate and watchdog delivery paths missed, without competing with
    them for freshly queued ones (issue #131).

    The join on ``terminals`` drops messages whose receiver terminal no longer
    exists, so the sweep does not keep retrying deliveries to deleted agents.

    ``created_at`` is stored local-naive (``InboxModel.created_at`` defaults to
    ``datetime.now``), so the cutoff uses ``datetime.now()`` to match — the same
    convention as the retention query in ``cleanup_service.cleanup_old_data``.
    """
    cutoff = datetime.now() - timedelta(seconds=min_age_seconds)
    with SessionLocal() as db:
        rows = (
            db.query(InboxModel.receiver_id)
            .join(TerminalModel, TerminalModel.id == InboxModel.receiver_id)
            .filter(
                InboxModel.status == MessageStatus.PENDING.value,
                InboxModel.created_at < cutoff,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows]


def delete_terminal(terminal_id: str) -> bool:
    """Delete terminal metadata."""
    with SessionLocal() as db:
        deleted = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).delete()
        db.commit()
        return deleted > 0


def delete_terminals_by_session(tmux_session: str) -> int:
    """Delete all terminals in a session."""
    with SessionLocal() as db:
        deleted = (
            db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).delete()
        )
        db.commit()
        return deleted


def create_inbox_message(sender_id: str, receiver_id: str, message: str) -> InboxMessage:
    """Create inbox message with status=MessageStatus.PENDING.

    Raises:
        ValueError: If the receiver terminal does not exist.
    """
    with SessionLocal() as db:
        if not db.query(TerminalModel).filter(TerminalModel.id == receiver_id).first():
            raise ValueError(f"Terminal '{receiver_id}' not found")
        inbox_msg = InboxModel(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message,
            status=MessageStatus.PENDING.value,
        )
        db.add(inbox_msg)
        db.commit()
        db.refresh(inbox_msg)
        return InboxMessage(
            id=inbox_msg.id,
            sender_id=inbox_msg.sender_id,
            receiver_id=inbox_msg.receiver_id,
            message=inbox_msg.message,
            status=MessageStatus(inbox_msg.status),
            created_at=inbox_msg.created_at,
        )


def get_pending_messages(receiver_id: str, limit: int = 1) -> List[InboxMessage]:
    """Get pending messages ordered by created_at ASC (oldest first)."""
    return get_inbox_messages(receiver_id, limit=limit, status=MessageStatus.PENDING)


def get_inbox_messages(
    receiver_id: str, limit: int = 10, status: Optional[MessageStatus] = None
) -> List[InboxMessage]:
    """Get inbox messages with optional status filter ordered by created_at ASC (oldest first).

    Args:
        receiver_id: Terminal ID to get messages for
        limit: Maximum number of messages to return (default: 10)
        status: Optional filter by message status (None = all statuses)

    Returns:
        List of inbox messages ordered by creation time (oldest first)
    """
    with SessionLocal() as db:
        query = db.query(InboxModel).filter(InboxModel.receiver_id == receiver_id)

        if status is not None:
            query = query.filter(InboxModel.status == status.value)

        messages = query.order_by(InboxModel.created_at.asc()).limit(limit).all()

        return [
            InboxMessage(
                id=msg.id,
                sender_id=msg.sender_id,
                receiver_id=msg.receiver_id,
                message=msg.message,
                status=MessageStatus(msg.status),
                created_at=msg.created_at,
            )
            for msg in messages
        ]


def record_project_alias(project_id: str, alias: str, kind: str) -> None:
    """Idempotently record a project_id ↔ alias mapping (Phase 2.5 U6).

    Used opportunistically by ``resolve_project_id`` to track historical
    cwd-hash and git-remote-url aliases for a canonical project_id. Best-effort
    only — DB errors are swallowed so identity resolution is never blocked.
    """
    if not project_id or not alias or project_id == alias:
        return
    try:
        with SessionLocal() as db:
            # Upsert by alias (the primary key). If the same alias was already
            # mapped — e.g. recorded against an override id, then re-resolved
            # via git remote — repoint it to the current canonical project_id
            # so reverse lookups stay deterministic instead of duplicating.
            existing = db.query(ProjectAliasModel).filter(ProjectAliasModel.alias == alias).first()
            if existing is None:
                db.add(ProjectAliasModel(project_id=project_id, alias=alias, kind=kind))
                db.commit()
            elif existing.project_id != project_id or existing.kind != kind:
                existing.project_id = project_id
                existing.kind = kind
                db.commit()
    except Exception as e:
        logger.debug(f"record_project_alias failed (non-fatal): {e}")


def get_project_id_by_alias(alias: str) -> Optional[str]:
    """Return the canonical ``project_id`` for an alias, or None if unknown."""
    if not alias:
        return None
    try:
        with SessionLocal() as db:
            row = db.query(ProjectAliasModel).filter(ProjectAliasModel.alias == alias).first()
            return cast(Optional[str], row.project_id) if row else None
    except Exception as e:
        logger.debug(f"get_project_id_by_alias failed (non-fatal): {e}")
        return None


def list_aliases_for_project(project_id: str) -> List[Dict[str, Any]]:
    """List all aliases recorded for a canonical ``project_id``."""
    if not project_id:
        return []
    try:
        with SessionLocal() as db:
            rows = (
                db.query(ProjectAliasModel).filter(ProjectAliasModel.project_id == project_id).all()
            )
            return [{"project_id": r.project_id, "alias": r.alias, "kind": r.kind} for r in rows]
    except Exception as e:
        logger.debug(f"list_aliases_for_project failed (non-fatal): {e}")
        return []


def update_message_status(message_id: int, status: MessageStatus) -> bool:
    """Update message status to MessageStatus.DELIVERED or MessageStatus.FAILED."""
    with SessionLocal() as db:
        message = db.query(InboxModel).filter(InboxModel.id == message_id).first()
        if message:
            message.status = status.value
            db.commit()
            return True
        return False


# Flow database functions


def create_flow(
    name: str,
    file_path: str,
    schedule: str,
    agent_profile: str,
    provider: str,
    script: str,
    next_run: datetime,
) -> Flow:
    """Create flow record."""
    with SessionLocal() as db:
        flow = FlowModel(
            name=name,
            file_path=file_path,
            schedule=schedule,
            agent_profile=agent_profile,
            provider=provider,
            script=script,
            next_run=next_run,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        return Flow(
            name=flow.name,
            file_path=flow.file_path,
            schedule=flow.schedule,
            agent_profile=flow.agent_profile,
            provider=flow.provider,
            script=flow.script,
            last_run=flow.last_run,
            next_run=flow.next_run,
            enabled=flow.enabled,
            prompt_template=None,
        )


def get_flow(name: str) -> Optional[Flow]:
    """Get flow by name."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if not flow:
            return None
        return Flow(
            name=flow.name,
            file_path=flow.file_path,
            schedule=flow.schedule,
            agent_profile=flow.agent_profile,
            provider=flow.provider,
            script=flow.script,
            last_run=flow.last_run,
            next_run=flow.next_run,
            enabled=flow.enabled,
            prompt_template=None,
        )


def list_flows() -> List[Flow]:
    """List all flows."""
    with SessionLocal() as db:
        flows = db.query(FlowModel).order_by(FlowModel.next_run).all()
        return [
            Flow(
                name=f.name,
                file_path=f.file_path,
                schedule=f.schedule,
                agent_profile=f.agent_profile,
                provider=f.provider,
                script=f.script,
                last_run=f.last_run,
                next_run=f.next_run,
                enabled=f.enabled,
                prompt_template=None,
            )
            for f in flows
        ]


def update_flow_run_times(name: str, last_run: datetime, next_run: datetime) -> bool:
    """Update flow run times after execution."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.last_run = last_run
            flow.next_run = next_run
            db.commit()
            return True
        return False


def update_flow_enabled(name: str, enabled: bool, next_run: Optional[datetime] = None) -> bool:
    """Update flow enabled status and optionally next_run."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.enabled = enabled
            if next_run is not None:
                flow.next_run = next_run
            db.commit()
            return True
        return False


def delete_flow(name: str) -> bool:
    """Delete flow."""
    with SessionLocal() as db:
        deleted = db.query(FlowModel).filter(FlowModel.name == name).delete()
        db.commit()
        return deleted > 0


def get_flows_to_run() -> List[Flow]:
    """Get enabled flows where next_run <= now."""
    with SessionLocal() as db:
        now = datetime.now()
        flows = (
            db.query(FlowModel).filter(FlowModel.enabled == True, FlowModel.next_run <= now).all()
        )
        return [
            Flow(
                name=f.name,
                file_path=f.file_path,
                schedule=f.schedule,
                agent_profile=f.agent_profile,
                provider=f.provider,
                script=f.script,
                last_run=f.last_run,
                next_run=f.next_run,
                enabled=f.enabled,
                prompt_template=None,
            )
            for f in flows
        ]
