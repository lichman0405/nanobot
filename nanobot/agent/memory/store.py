"""
Memory store - main interface for the memory system.

This module provides backward compatibility with the old MemoryStore interface
while implementing the new git-like memory architecture internally.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

from nanobot.utils.helpers import ensure_dir, today_date
from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.commit import MemoryCommit
from nanobot.agent.memory.branch import MemoryBranch
from nanobot.agent.memory.ledger import EventLedger
from nanobot.agent.memory.branches import BranchManager
from nanobot.agent.memory.view import MemoryView


class MemoryStore:
    """
    Memory system for the agent.
    
    This class provides backward compatibility with the old interface
    while internally using the new git-like memory architecture.
    
    Old interface methods (preserved for compatibility):
        - read_today() / append_today()
        - read_long_term() / write_long_term()
        - get_recent_memories()
        - get_memory_context()
    
    New interface methods (git-like):
        - TODO: Will be added in Phase 2
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        
        # Legacy paths (for backward compatibility)
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        
        # New git-like structure paths
        self.ledger_dir = ensure_dir(self.memory_dir / "ledger")
        self.events_dir = ensure_dir(self.ledger_dir / "events")
        self.commits_dir = ensure_dir(self.ledger_dir / "commits")
        self.branches_dir = ensure_dir(self.memory_dir / "branches")
        self.view_dir = ensure_dir(self.memory_dir / "view")
        self.head_file = self.memory_dir / "HEAD"
        
        # Initialize ledger
        self.ledger = EventLedger(self.events_dir, self.commits_dir)
        
        # Initialize if needed
        self._ensure_initialized()
        
        # Initialize branch manager and view
        self.branch_manager = BranchManager(
            self.branches_dir,
            self.head_file,
            self.ledger,
        )
        self.view = MemoryView(
            self.ledger,
            self.view_dir,
            self.branches_dir,
            self.head_file,
        )
    
    def _ensure_initialized(self) -> None:
        """Ensure the memory system is initialized with default branch."""
        if not self.head_file.exists():
            # Create default HEAD pointing to main branch
            self.head_file.write_text("main", encoding="utf-8")
        
        # Ensure main branch exists
        main_branch_file = self.branches_dir / "main.json"
        if not main_branch_file.exists():
            main_branch = MemoryBranch(name="main", persona="default")
            main_branch_file.write_text(
                json.dumps(main_branch.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
    
    # =========================================================================
    # Legacy Interface (backward compatibility)
    # =========================================================================
    
    def get_today_file(self) -> Path:
        """Get path to today's memory file."""
        return self.memory_dir / f"{today_date()}.md"
    
    def read_today(self) -> str:
        """Read today's memory notes."""
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""
    
    def append_today(self, content: str) -> None:
        """Append content to today's memory notes."""
        today_file = self.get_today_file()
        
        if today_file.exists():
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            # Add header for new day
            header = f"# {today_date()}\n\n"
            content = header + content
        
        today_file.write_text(content, encoding="utf-8")
    
    def read_long_term(self) -> str:
        """Read long-term memory (MEMORY.md)."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""
    
    def write_long_term(self, content: str) -> None:
        """Write to long-term memory (MEMORY.md)."""
        self.memory_file.write_text(content, encoding="utf-8")
    
    def get_recent_memories(self, days: int = 7) -> str:
        """
        Get memories from the last N days.
        
        Args:
            days: Number of days to look back.
        
        Returns:
            Combined memory content.
        """
        memories = []
        today = datetime.now().date()
        
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(content)
        
        return "\n\n---\n\n".join(memories)
    
    def list_memory_files(self) -> list[Path]:
        """List all memory files sorted by date (newest first)."""
        if not self.memory_dir.exists():
            return []
        
        files = list(self.memory_dir.glob("????-??-??.md"))
        return sorted(files, reverse=True)
    
    def get_memory_context(self) -> str:
        """
        Get memory context for the agent.
        
        Returns:
            Formatted memory context including long-term and recent memories.
        """
        parts = []
        
        # Long-term memory
        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)
        
        # Today's notes
        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)
        
        return "\n\n".join(parts) if parts else ""
    
    # =========================================================================
    # New Git-like Interface
    # =========================================================================
    
    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return "main"
    
    def get_branch(self, name: str) -> MemoryBranch | None:
        """Get a branch by name."""
        branch_file = self.branches_dir / f"{name}.json"
        if not branch_file.exists():
            return None
        data = json.loads(branch_file.read_text(encoding="utf-8"))
        return MemoryBranch.from_dict(data)
    
    def save_branch(self, branch: MemoryBranch) -> None:
        """Save a branch to disk."""
        branch_file = self.branches_dir / f"{branch.name}.json"
        branch_file.write_text(
            json.dumps(branch.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def list_branches(self) -> list[MemoryBranch]:
        """List all branches."""
        branches = []
        for branch_file in self.branches_dir.glob("*.json"):
            data = json.loads(branch_file.read_text(encoding="utf-8"))
            branches.append(MemoryBranch.from_dict(data))
        return branches
    
    def create_branch(self, name: str, persona: str | None = None) -> MemoryBranch:
        """
        Create a new branch.
        
        The new branch starts from the current HEAD of the active branch.
        
        Args:
            name: Name of the new branch.
            persona: Optional persona description.
        
        Returns:
            The created branch.
        """
        # Get current branch's HEAD
        current = self.get_branch(self.get_current_branch())
        parent_head = current.head if current else None
        
        # Create new branch
        branch = MemoryBranch(name=name, head=parent_head, persona=persona)
        self.save_branch(branch)
        
        return branch
    
    def switch_branch(self, branch_name: str) -> bool:
        """
        Switch to a different branch.
        
        Args:
            branch_name: Name of the branch to switch to.
        
        Returns:
            True if successful, False if branch doesn't exist.
        """
        branch = self.get_branch(branch_name)
        if branch is None:
            return False
        
        self.head_file.write_text(branch_name, encoding="utf-8")
        return True
    
    def add_event(self, event: MemoryEvent) -> str:
        """
        Add an event to the ledger.
        
        Note: This only adds the event to storage. To include it in the
        memory history, you must also create a commit.
        
        Args:
            event: The event to add.
        
        Returns:
            The event ID.
        """
        return self.ledger.append_event(event)
    
    def commit(
        self,
        events: list[MemoryEvent],
        message: str,
        metadata: dict | None = None,
    ) -> MemoryCommit:
        """
        Create a commit with the given events.
        
        This is the primary way to add memories to the system. Events are
        first added to the ledger, then grouped into a commit which becomes
        the new HEAD of the current branch.
        
        Args:
            events: List of events to include in this commit.
            message: Human-readable commit message.
            metadata: Optional additional metadata.
        
        Returns:
            The created commit.
        """
        # Get current branch
        branch_name = self.get_current_branch()
        branch = self.get_branch(branch_name)
        
        if branch is None:
            # Create branch if it doesn't exist
            branch = self.create_branch(branch_name)
        
        # Add events to ledger
        event_ids = []
        for event in events:
            event_id = self.ledger.append_event(event)
            event_ids.append(event_id)
        
        # Create commit
        commit = MemoryCommit(
            branch=branch_name,
            events=event_ids,
            message=message,
            parent_id=branch.head,
            metadata=metadata or {},
        )
        
        # Save commit
        self.ledger.append_commit(commit)
        
        # Update branch HEAD
        branch.head = commit.id
        self.save_branch(branch)
        
        return commit
    
    def get_current_commit(self) -> MemoryCommit | None:
        """Get the current HEAD commit."""
        branch = self.get_branch(self.get_current_branch())
        if branch is None or branch.head is None:
            return None
        return self.ledger.get_commit(branch.head)
    
    def get_history(self, max_commits: int = 50) -> list[MemoryCommit]:
        """
        Get commit history for the current branch.
        
        Args:
            max_commits: Maximum number of commits to return.
        
        Returns:
            List of commits from newest to oldest.
        """
        branch = self.get_branch(self.get_current_branch())
        if branch is None or branch.head is None:
            return []
        
        history = self.ledger.get_commit_history(branch.head)
        return history[:max_commits]
    
    def get_all_memories(self) -> list[MemoryEvent]:
        """
        Get all memory events up to the current HEAD.
        
        Returns:
            List of events in chronological order.
        """
        branch = self.get_branch(self.get_current_branch())
        if branch is None or branch.head is None:
            return []
        
        return self.ledger.get_all_events_up_to(branch.head)
    
    def search_memories(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        scope: str | None = None,
    ) -> list[MemoryEvent]:
        """
        Search memories by criteria.
        
        Args:
            subject: Filter by subject.
            predicate: Filter by predicate.
            scope: Filter by scope.
        
        Returns:
            List of matching events.
        """
        memories = self.get_all_memories()
        
        results = []
        for event in memories:
            # Skip deprecated/forgotten events
            if event.event_type in ("deprecate", "forget"):
                continue
            
            # Apply filters
            if subject and event.subject != subject:
                continue
            if predicate and event.predicate != predicate:
                continue
            if scope and event.scope != scope:
                continue
            
            results.append(event)
        
        return results
    
    def get_memory_view(self) -> dict[str, MemoryEvent]:
        """
        Get the materialized view of current memories.
        
        This applies all events (add, update, deprecate, forget) to produce
        the current state. Each unique (subject, predicate, scope) tuple
        maps to its latest non-deprecated/forgotten value.
        
        Returns:
            Dictionary mapping memory keys to events.
        """
        memories = self.get_all_memories()
        view: dict[str, MemoryEvent] = {}
        
        for event in memories:
            # Create a key for this memory slot
            key = f"{event.subject}|{event.predicate}|{event.scope or ''}"
            
            if event.event_type in ("add", "update", "confirm"):
                view[key] = event
            elif event.event_type in ("deprecate", "forget"):
                view.pop(key, None)
        
        return view

