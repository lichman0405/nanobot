"""
Event ledger - immutable append-only event log.

This module implements Layer 0 of the memory system: the immutable event ledger.
All memory operations are recorded as events that cannot be modified or deleted,
only appended. This provides full traceability and auditability.
"""

import json
from pathlib import Path
from typing import Iterator

from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.commit import MemoryCommit


class EventLedger:
    """
    Immutable event ledger for memory operations.
    
    Stores events as individual JSON files using content-addressable storage.
    Each event is named by its SHA256 hash, ensuring:
    - Deduplication: identical events have the same ID
    - Integrity: any modification changes the hash
    - Traceability: full history is preserved
    
    Attributes:
        events_dir: Directory for event storage.
        commits_dir: Directory for commit storage.
    """
    
    def __init__(self, events_dir: Path, commits_dir: Path):
        self.events_dir = events_dir
        self.commits_dir = commits_dir
        
        # Ensure directories exist
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.commits_dir.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # Event Operations
    # =========================================================================
    
    def append_event(self, event: MemoryEvent) -> str:
        """
        Append an event to the ledger.
        
        If an event with the same ID already exists, this is a no-op
        (content-addressable storage naturally deduplicates).
        
        Args:
            event: The event to append.
        
        Returns:
            The event ID.
        """
        event_file = self.events_dir / f"{event.id}.json"
        
        if not event_file.exists():
            event_file.write_text(
                json.dumps(event.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        
        return event.id
    
    def get_event(self, event_id: str) -> MemoryEvent | None:
        """
        Retrieve an event by ID.
        
        Args:
            event_id: The event ID (hash).
        
        Returns:
            The event, or None if not found.
        """
        event_file = self.events_dir / f"{event_id}.json"
        
        if not event_file.exists():
            return None
        
        data = json.loads(event_file.read_text(encoding="utf-8"))
        return MemoryEvent.from_dict(data)
    
    def event_exists(self, event_id: str) -> bool:
        """Check if an event exists."""
        return (self.events_dir / f"{event_id}.json").exists()
    
    def list_events(self) -> list[str]:
        """List all event IDs in the ledger."""
        return [f.stem for f in self.events_dir.glob("*.json")]
    
    def iter_events(self) -> Iterator[MemoryEvent]:
        """Iterate over all events in the ledger."""
        for event_file in self.events_dir.glob("*.json"):
            data = json.loads(event_file.read_text(encoding="utf-8"))
            yield MemoryEvent.from_dict(data)
    
    def count_events(self) -> int:
        """Count total events in the ledger."""
        return len(list(self.events_dir.glob("*.json")))
    
    # =========================================================================
    # Commit Operations
    # =========================================================================
    
    def append_commit(self, commit: MemoryCommit) -> str:
        """
        Append a commit to the ledger.
        
        Args:
            commit: The commit to append.
        
        Returns:
            The commit ID.
        """
        commit_file = self.commits_dir / f"{commit.id}.json"
        
        if not commit_file.exists():
            commit_file.write_text(
                json.dumps(commit.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        
        return commit.id
    
    def get_commit(self, commit_id: str) -> MemoryCommit | None:
        """
        Retrieve a commit by ID.
        
        Args:
            commit_id: The commit ID (hash).
        
        Returns:
            The commit, or None if not found.
        """
        commit_file = self.commits_dir / f"{commit_id}.json"
        
        if not commit_file.exists():
            return None
        
        data = json.loads(commit_file.read_text(encoding="utf-8"))
        return MemoryCommit.from_dict(data)
    
    def commit_exists(self, commit_id: str) -> bool:
        """Check if a commit exists."""
        return (self.commits_dir / f"{commit_id}.json").exists()
    
    def list_commits(self) -> list[str]:
        """List all commit IDs in the ledger."""
        return [f.stem for f in self.commits_dir.glob("*.json")]
    
    def iter_commits(self) -> Iterator[MemoryCommit]:
        """Iterate over all commits in the ledger."""
        for commit_file in self.commits_dir.glob("*.json"):
            data = json.loads(commit_file.read_text(encoding="utf-8"))
            yield MemoryCommit.from_dict(data)
    
    def count_commits(self) -> int:
        """Count total commits in the ledger."""
        return len(list(self.commits_dir.glob("*.json")))
    
    # =========================================================================
    # History Traversal
    # =========================================================================
    
    def get_commit_history(self, commit_id: str) -> list[MemoryCommit]:
        """
        Get the full history of commits leading to a given commit.
        
        Traverses parent links from the given commit back to the root.
        
        Args:
            commit_id: Starting commit ID.
        
        Returns:
            List of commits from newest to oldest.
        """
        history = []
        current_id = commit_id
        
        while current_id:
            commit = self.get_commit(current_id)
            if commit is None:
                break
            history.append(commit)
            current_id = commit.parent_id
        
        return history
    
    def get_events_for_commit(self, commit_id: str) -> list[MemoryEvent]:
        """
        Get all events included in a commit.
        
        Args:
            commit_id: The commit ID.
        
        Returns:
            List of events in the commit.
        """
        commit = self.get_commit(commit_id)
        if commit is None:
            return []
        
        events = []
        for event_id in commit.events:
            event = self.get_event(event_id)
            if event:
                events.append(event)
        
        return events
    
    def get_all_events_up_to(self, commit_id: str) -> list[MemoryEvent]:
        """
        Get all events from the beginning up to and including a commit.
        
        Args:
            commit_id: The commit ID.
        
        Returns:
            List of all events in chronological order.
        """
        history = self.get_commit_history(commit_id)
        
        # Reverse to get chronological order (oldest first)
        history.reverse()
        
        all_events = []
        seen_ids = set()
        
        for commit in history:
            for event_id in commit.events:
                if event_id not in seen_ids:
                    event = self.get_event(event_id)
                    if event:
                        all_events.append(event)
                        seen_ids.add(event_id)
        
        return all_events
