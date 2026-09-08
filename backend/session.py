"""Conversation state.

In-memory, like the FixFeels reference — fine for a demo, wrong for a pilot:
sessions die on restart and are not shared across App Service instances. Swap
for Redis or Azure Table Storage before any real traffic.

Transcripts are held in memory only. Nothing is written to disk: in a health
context that would be patient data, and the reference's habit of appending
every turn to a local qa_log.json is exactly what not to copy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

HISTORY_LIMIT = 24


@dataclass
class Session:
    session_id: str
    locale: str
    created_at: str
    turns: list[dict[str, str]] = field(default_factory=list)
    # Details the customer has already given, so the agent stops re-asking.
    known: dict[str, str] = field(default_factory=dict)
    escalated: bool = False

    def append(self, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > HISTORY_LIMIT:
            self.turns = self.turns[-HISTORY_LIMIT:]

    def remember(self, **facts: str) -> None:
        for key, value in facts.items():
            if value:
                self.known[key] = value


_sessions: dict[str, Session] = {}


def create(locale: str) -> Session:
    session = Session(
        session_id=str(uuid.uuid4()),
        locale=locale,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _sessions[session.session_id] = session
    return session


def get(session_id: str | None) -> Session | None:
    return _sessions.get(session_id or "")


def count() -> int:
    return len(_sessions)
