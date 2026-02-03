"""
Memory view - materialized view of current memory state.

Provides a queryable view of the current memory state by applying all events
up to the current HEAD.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json
from pathlib import Path

from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.ledger import EventLedger
from nanobot.agent.memory.branch import MemoryBranch


@dataclass
class MemorySlot:
    """
    A slot in the memory view.
    
    Represents a single piece of knowledge with its history.
    """
    key: str
    current: MemoryEvent
    history: list[str] = field(default_factory=list)  # Event IDs
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "current": self.current.to_dict(),
            "history": self.history,
        }


class MemoryView:
    """
    Materialized view of current memory state.
    
    The view is computed by "replaying" all events from the beginning up to
    the current HEAD. Events are applied in order:
    - add: Creates a new memory slot
    - update: Updates an existing slot
    - confirm: Marks a memory as confirmed (increases confidence)
    - deprecate: Marks a memory as outdated but keeps history
    - forget: Removes a memory from the view
    
    The view can be cached to disk for faster access.
    """
    
    def __init__(
        self,
        ledger: EventLedger,
        view_dir: Path,
        branches_dir: Path,
        head_file: Path,
    ):
        self.ledger = ledger
        self.view_dir = view_dir
        self.branches_dir = branches_dir
        self.head_file = head_file
        
        self.view_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self._slots: dict[str, MemorySlot] = {}
        self._last_computed_head: str | None = None
    
    def _get_current_head(self) -> str | None:
        """Get the current HEAD commit ID."""
        if not self.head_file.exists():
            return None
        
        branch_name = self.head_file.read_text(encoding="utf-8").strip()
        branch_file = self.branches_dir / f"{branch_name}.json"
        
        if not branch_file.exists():
            return None
        
        data = json.loads(branch_file.read_text(encoding="utf-8"))
        return data.get("head")
    
    def _make_key(self, event: MemoryEvent) -> str:
        """Create a unique key for a memory slot."""
        return f"{event.subject}|{event.predicate}|{event.scope or ''}"
    
    def compute(self, force: bool = False) -> dict[str, MemorySlot]:
        """
        Compute the current memory view.
        
        Args:
            force: Force recomputation even if cached.
        
        Returns:
            Dictionary of memory slots.
        """
        current_head = self._get_current_head()
        
        # Use cache if available
        if not force and current_head == self._last_computed_head:
            return self._slots
        
        if current_head is None:
            self._slots = {}
            self._last_computed_head = None
            return self._slots
        
        # Replay all events
        events = self.ledger.get_all_events_up_to(current_head)
        
        slots: dict[str, MemorySlot] = {}
        
        for event in events:
            key = self._make_key(event)
            
            if event.event_type in ("add", "update", "confirm"):
                if key in slots:
                    # Update existing slot
                    slots[key].current = event
                    slots[key].history.append(event.id)
                else:
                    # Create new slot
                    slots[key] = MemorySlot(
                        key=key,
                        current=event,
                        history=[event.id],
                    )
            
            elif event.event_type == "deprecate":
                # Keep the slot but mark event type
                if key in slots:
                    slots[key].current = event
                    slots[key].history.append(event.id)
            
            elif event.event_type == "forget":
                # Remove from active view
                if key in slots:
                    del slots[key]
        
        self._slots = slots
        self._last_computed_head = current_head
        
        return slots
    
    def get_all(self) -> list[MemoryEvent]:
        """Get all current memories as a list of events."""
        slots = self.compute()
        return [
            slot.current for slot in slots.values()
            if slot.current.event_type not in ("deprecate", "forget")
        ]
    
    def get(self, subject: str, predicate: str, scope: str | None = None) -> MemoryEvent | None:
        """
        Get a specific memory.
        
        Args:
            subject: Memory subject.
            predicate: Memory predicate.
            scope: Optional scope.
        
        Returns:
            The memory event, or None if not found.
        """
        key = f"{subject}|{predicate}|{scope or ''}"
        slots = self.compute()
        
        slot = slots.get(key)
        if slot and slot.current.event_type not in ("deprecate", "forget"):
            return slot.current
        
        return None
    
    def search(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        scope: str | None = None,
        text: str | None = None,
    ) -> list[MemoryEvent]:
        """
        Search memories by criteria.
        
        Args:
            subject: Filter by subject (partial match).
            predicate: Filter by predicate (partial match).
            scope: Filter by scope (exact match).
            text: Free text search in object field.
        
        Returns:
            List of matching memory events.
        """
        results = []
        
        for event in self.get_all():
            # Apply filters
            if subject and subject.lower() not in event.subject.lower():
                continue
            if predicate and predicate.lower() not in event.predicate.lower():
                continue
            if scope and event.scope != scope:
                continue
            if text and text.lower() not in event.object.lower():
                continue
            
            results.append(event)
        
        return results
    
    def get_by_scope(self, scope: str) -> list[MemoryEvent]:
        """Get all memories in a specific scope."""
        return self.search(scope=scope)
    
    def get_by_subject(self, subject: str) -> list[MemoryEvent]:
        """Get all memories about a subject."""
        return [
            event for event in self.get_all()
            if event.subject == subject
        ]
    
    def to_context_string(self, max_items: int = 50) -> str:
        """
        Generate a context string for LLM consumption.
        
        Args:
            max_items: Maximum number of memories to include.
        
        Returns:
            Formatted memory context string.
        """
        memories = self.get_all()
        
        if not memories:
            return ""
        
        # Sort by confidence and recency
        memories.sort(key=lambda e: (e.confidence, e.timestamp), reverse=True)
        memories = memories[:max_items]
        
        # Group by scope
        by_scope: dict[str, list[MemoryEvent]] = {}
        for event in memories:
            scope = event.scope or "general"
            if scope not in by_scope:
                by_scope[scope] = []
            by_scope[scope].append(event)
        
        # Format output
        lines = ["## Memory"]
        
        for scope, events in sorted(by_scope.items()):
            lines.append(f"\n### {scope.title()}")
            for event in events:
                confidence_marker = "✓" if event.confidence >= 0.8 else "?"
                lines.append(f"- {confidence_marker} {event.subject} {event.predicate} {event.object}")
        
        return "\n".join(lines)
    
    def save_cache(self) -> None:
        """Save the current view to disk cache."""
        cache_file = self.view_dir / "current.json"
        
        slots = self.compute()
        data = {
            "head": self._last_computed_head,
            "slots": {key: slot.to_dict() for key, slot in slots.items()},
        }
        
        cache_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
    
    def load_cache(self) -> bool:
        """
        Load view from disk cache if valid.
        
        Returns:
            True if cache was loaded, False if recomputation needed.
        """
        cache_file = self.view_dir / "current.json"
        
        if not cache_file.exists():
            return False
        
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cached_head = data.get("head")
            current_head = self._get_current_head()
            
            if cached_head != current_head:
                return False  # Cache is stale
            
            # Restore slots
            self._slots = {}
            for key, slot_data in data.get("slots", {}).items():
                self._slots[key] = MemorySlot(
                    key=slot_data["key"],
                    current=MemoryEvent.from_dict(slot_data["current"]),
                    history=slot_data.get("history", []),
                )
            
            self._last_computed_head = cached_head
            return True
            
        except Exception:
            return False
