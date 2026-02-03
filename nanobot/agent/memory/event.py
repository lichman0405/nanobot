"""Memory event data structure."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Any

from nanobot.agent.memory.hash import compute_hash


# Event types for memory operations
EventType = Literal["add", "update", "deprecate", "forget", "confirm"]

# Sensitivity levels for access control
Sensitivity = Literal["public", "private", "ephemeral"]

# Source of memory (how it was created)
MemorySource = Literal[
    "user_explicit",    # User said "remember this"
    "user_implicit",    # Inferred from user message
    "agent_inferred",   # Agent's own inference
    "tool_output",      # From tool execution
    "system",           # System-generated
]


@dataclass
class MemoryEvent:
    """
    An immutable memory event in the ledger.
    
    Represents a single memory operation (add, update, deprecate, etc.)
    in the append-only event log. Each event is content-addressable via
    its SHA256 hash.
    
    Attributes:
        event_type: Type of memory operation.
        subject: The subject of the memory (who/what).
        predicate: The relationship or action.
        object: The object of the memory (what/whom).
        scope: Optional scope limiting where this memory applies.
        confidence: Confidence level (0.0 to 1.0).
        source: How this memory was created.
        evidence: Reference to the source (conversation snippet, tool output).
        sensitivity: Access control level.
        parent_id: ID of parent event (for traceability).
        timestamp: When this event was created.
        id: Content-addressable hash (computed automatically).
    """
    
    # Core memory content (subject-predicate-object triple)
    event_type: EventType
    subject: str
    predicate: str
    object: str
    
    # Metadata
    scope: str | None = None
    confidence: float = 1.0
    source: MemorySource = "user_implicit"
    evidence: str | None = None
    sensitivity: Sensitivity = "public"
    
    # Traceability
    parent_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Content-addressable ID (computed after init)
    id: str = field(default="", init=False)
    
    def __post_init__(self) -> None:
        """Compute content-addressable ID after initialization."""
        if not self.id:
            self.id = self._compute_id()
    
    def _compute_id(self) -> str:
        """Compute SHA256 hash of event content."""
        # Only hash the semantic content, not metadata that doesn't affect identity
        content = {
            "event_type": self.event_type,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "scope": self.scope,
            "timestamp": self.timestamp.isoformat(),
        }
        return compute_hash(content)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEvent":
        """Create from dictionary."""
        # Parse timestamp
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        
        # Create instance without auto-computing ID
        event = cls(
            event_type=data["event_type"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            scope=data.get("scope"),
            confidence=data.get("confidence", 1.0),
            source=data.get("source", "user_implicit"),
            evidence=data.get("evidence"),
            sensitivity=data.get("sensitivity", "public"),
            parent_id=data.get("parent_id"),
            timestamp=data.get("timestamp", datetime.now()),
        )
        # Restore original ID if present
        if "id" in data and data["id"]:
            event.id = data["id"]
        return event
    
    def __str__(self) -> str:
        """Human-readable representation."""
        return f"[{self.event_type}] {self.subject} {self.predicate} {self.object}"
    
    def __repr__(self) -> str:
        """Debug representation."""
        return f"MemoryEvent(id={self.id[:8]}..., {self})"
