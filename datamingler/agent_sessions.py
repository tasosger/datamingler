from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .projects import ProjectStore, validate_project_id

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class AgentMessage:
    role: str
    content: str
    created_at: str
    provider: str = ""
    model: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    queries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AgentSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    provider: str = "openai"
    model: str = "gpt-5.1"
    messages: list[AgentMessage] = field(default_factory=list)


class AgentSessionStore:
    def __init__(self, project_store: ProjectStore) -> None:
        self.project_store = project_store

    def list(self, project_id: str) -> list[AgentSession]:
        self._ensure_schema(project_id)
        with closing(self._connect(project_id)) as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at, s.provider, s.model
                FROM agent_sessions s
                ORDER BY s.updated_at DESC, s.created_at DESC
                """
            ).fetchall()
        return [
            AgentSession(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                provider=row["provider"],
                model=row["model"],
                messages=[],
            )
            for row in rows
        ]

    def create(self, project_id: str, *, title: str = "", provider: str = "openai", model: str = "gpt-5.1") -> AgentSession:
        self._ensure_schema(project_id)
        now = _now()
        session = AgentSession(
            id=uuid.uuid4().hex[:12],
            title=title.strip() or "New agent session",
            created_at=now,
            updated_at=now,
            provider=provider,
            model=model,
            messages=[],
        )
        with closing(self._connect(project_id)) as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (id, title, created_at, updated_at, provider, model)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session.id, session.title, session.created_at, session.updated_at, session.provider, session.model),
            )
            conn.commit()
        return session

    def get(self, project_id: str, session_id: str) -> AgentSession:
        session_id = validate_session_id(session_id)
        self._ensure_schema(project_id)
        with closing(self._connect(project_id)) as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at, provider, model
                FROM agent_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Agent session {session_id!r} does not exist")
            message_rows = conn.execute(
                """
                SELECT role, content, created_at, provider, model, steps_json, queries_json
                FROM agent_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()

        return AgentSession(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            provider=row["provider"],
            model=row["model"],
            messages=[_message_from_row(item) for item in message_rows],
        )

    def append_user_message(
        self,
        project_id: str,
        session_id: str,
        content: str,
        *,
        provider: str,
        model: str,
    ) -> AgentSession:
        session = self.get(project_id, session_id)
        now = _now()
        title = session.title
        if title == "New agent session" and content.strip():
            title = " ".join(content.strip().split()[:6])
        self._insert_message(
            project_id,
            session.id,
            AgentMessage(role="user", content=content, created_at=now, provider=provider, model=model),
            updated_at=now,
            title=title,
            provider=provider,
            model=model,
        )
        return self.get(project_id, session.id)

    def append_assistant_message(
        self,
        project_id: str,
        session_id: str,
        content: str,
        *,
        provider: str,
        model: str,
        steps: list[dict[str, Any]],
        queries: list[dict[str, Any]],
    ) -> AgentSession:
        session = self.get(project_id, session_id)
        now = _now()
        self._insert_message(
            project_id,
            session.id,
            AgentMessage(
                role="assistant",
                content=content,
                created_at=now,
                provider=provider,
                model=model,
                steps=steps,
                queries=queries,
            ),
            updated_at=now,
            title=session.title,
            provider=provider,
            model=model,
        )
        return self.get(project_id, session.id)

    def _insert_message(
        self,
        project_id: str,
        session_id: str,
        message: AgentMessage,
        *,
        updated_at: str,
        title: str,
        provider: str,
        model: str,
    ) -> None:
        self._ensure_schema(project_id)
        with closing(self._connect(project_id)) as conn:
            conn.execute(
                """
                INSERT INTO agent_messages
                    (session_id, role, content, created_at, provider, model, steps_json, queries_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message.role,
                    message.content,
                    message.created_at,
                    message.provider,
                    message.model,
                    json.dumps(message.steps),
                    json.dumps(message.queries),
                ),
            )
            conn.execute(
                """
                UPDATE agent_sessions
                SET title = ?, updated_at = ?, provider = ?, model = ?
                WHERE id = ?
                """,
                (title, updated_at, provider, model, session_id),
            )
            conn.commit()

    def _connect(self, project_id: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path(project_id))
        conn.row_factory = sqlite3.Row
        return conn

    def _db_path(self, project_id: str) -> Path:
        project_id = validate_project_id(project_id)
        project_dir = self.project_store.project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / "agent_sessions.sqlite"

    def _ensure_schema(self, project_id: str) -> None:
        with closing(self._connect(project_id)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    queries_json TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_messages_session_id ON agent_messages(session_id, id)"
            )
            conn.commit()


def validate_session_id(session_id: str | None) -> str:
    value = (session_id or "").strip()
    if not _SESSION_ID_RE.match(value):
        raise ValueError("Session id must contain only letters, numbers, '-' or '_'")
    return value


def session_to_dict(session: AgentSession, *, include_messages: bool = True) -> dict[str, Any]:
    data = asdict(session)
    if not include_messages:
        data.pop("messages", None)
        data["message_count"] = len(session.messages)
    return data


def _message_from_row(row: sqlite3.Row) -> AgentMessage:
    return AgentMessage(
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        provider=row["provider"],
        model=row["model"],
        steps=_json_list(row["steps_json"]),
        queries=_json_list(row["queries_json"]),
    )


def _json_list(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
