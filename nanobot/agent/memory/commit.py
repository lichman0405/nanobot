"""Memory commit data structure."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from nanobot.agent.memory.hash import compute_hash


@dataclass
class MemoryCommit:
    """
    A commit in the memory history.
    
    Similar to a git commit, this groups related memory events together
    and forms a linked list of memory states. Each commit points to its
    parent, forming a DAG structure that enables branching and merging.
    
    Attributes:
        branch: Name of the branch this commit belongs to.
        events: List of event IDs included in this commit.
        message: Human-readable description of what this commit represents.
        parent_id: ID of the parent commit (None for initial commit).
        timestamp: When this commit was created.
        metadata: Additional metadata (e.g., triggering context).
        id: Content-addressable hash (computed automatically).
    """
    
    branch: str
    events: list[str]
    message: str
    parent_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Content-addressable ID (computed after init)
    id: str = field(default="", init=False)
    
    def __post_init__(self) -> None:
        """Compute content-addressable ID after initialization."""
        if not self.id:
            self.id = self._compute_id()
    
    def _compute_id(self) -> str:
        """Compute SHA256 hash of commit content."""
        content = {
            "branch": self.branch,
            "events": sorted(self.events),  # Sort for determinism
            "parent_id": self.parent_id,
            "timestamp": self.timestamp.isoformat(),
        }
        return compute_hash(content)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryCommit":
        """Create from dictionary."""
        # Parse timestamp
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        
        commit = cls(
            branch=data["branch"],
            events=data["events"],
            message=data["message"],
            parent_id=data.get("parent_id"),
            timestamp=data.get("timestamp", datetime.now()),
            metadata=data.get("metadata", {}),
        )
        # Restore original ID if present
        if "id" in data and data["id"]:
            commit.id = data["id"]
        return commit
    
    def __str__(self) -> str:
        """Human-readable representation."""
        short_id = self.id[:8] if self.id else "??????"
        return f"{short_id} [{self.branch}] {self.message}"
    
    def __repr__(self) -> str:
        """Debug representation."""
        return f"MemoryCommit(id={self.id[:8]}..., branch={self.branch}, events={len(self.events)})"
