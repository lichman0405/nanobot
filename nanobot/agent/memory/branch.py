"""Memory branch data structure."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class MemoryBranch:
    """
    A branch in the memory system.
    
    Branches allow different memory contexts (personas) to coexist.
    Each branch has its own HEAD pointing to the latest commit,
    similar to git branches.
    
    Attributes:
        name: Unique name of the branch (e.g., "main", "secretary", "developer").
        head: ID of the latest commit on this branch (None if empty).
        persona: Description of the persona this branch represents.
        created_at: When this branch was created.
        metadata: Additional metadata.
    """
    
    name: str
    head: str | None = None
    persona: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryBranch":
        """Create from dictionary."""
        # Parse timestamp
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        
        return cls(
            name=data["name"],
            head=data.get("head"),
            persona=data.get("persona"),
            created_at=data.get("created_at", datetime.now()),
            metadata=data.get("metadata", {}),
        )
    
    def __str__(self) -> str:
        """Human-readable representation."""
        head_short = self.head[:8] if self.head else "empty"
        persona_str = f" ({self.persona})" if self.persona else ""
        return f"{self.name}{persona_str} -> {head_short}"
    
    def __repr__(self) -> str:
        """Debug representation."""
        return f"MemoryBranch(name={self.name}, head={self.head[:8] if self.head else None})"
