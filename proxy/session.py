import json
import time 
import uuid 
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class Session:
    session_id: str
    goal: str
    created_at: float
    call_ids: list[str] = field(default_factory=list)
    status: str = "open"
    outcome: Optional[str] = None
    closed_at: Optional[float] = None

class SessionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                self._sessions[data["session_id"]] = Session(**data)

    def _persist(self, session: Session) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(session)) + "\n")

    def create(self, goal: str) -> Session:
        session = Session(session_id=str(uuid.uuid4()), goal=goal, created_at=time.time())
        self._sessions[session.session_id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def append_call(self, session_id: str, call_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"No session {session_id!r}")
        session.call_ids.append(call_id)
        self._persist(session)

    def close(self, session_id: str, outcome: Optional[str] = None) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"No session {session_id!r}")
        session.status = "closed"
        session.outcome = outcome
        session.closed_at = time.time()
        self._persist(session)
        return session
