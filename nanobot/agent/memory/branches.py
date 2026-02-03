"""
Branch manager for memory system.

Provides higher-level branch operations including merging and cherry-picking.
"""

import json
from pathlib import Path
from datetime import datetime

from nanobot.agent.memory.branch import MemoryBranch
from nanobot.agent.memory.commit import MemoryCommit
from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.ledger import EventLedger


class BranchManager:
    """
    Manages memory branches (personas).
    
    Provides operations for:
    - Branch creation and deletion
    - Branch merging
    - Cherry-picking commits between branches
    - Branch comparison
    """
    
    def __init__(
        self,
        branches_dir: Path,
        head_file: Path,
        ledger: EventLedger,
    ):
        self.branches_dir = branches_dir
        self.head_file = head_file
        self.ledger = ledger
        
        self.branches_dir.mkdir(parents=True, exist_ok=True)
    
    def get_current_branch_name(self) -> str:
        """Get the name of the current branch."""
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return "main"
    
    def set_current_branch(self, name: str) -> None:
        """Set the current branch."""
        self.head_file.write_text(name, encoding="utf-8")
    
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
    
    def delete_branch(self, name: str) -> bool:
        """
        Delete a branch.
        
        Cannot delete the main branch or the current branch.
        
        Args:
            name: Branch name.
        
        Returns:
            True if deleted, False otherwise.
        """
        if name == "main":
            return False
        
        if name == self.get_current_branch_name():
            return False
        
        branch_file = self.branches_dir / f"{name}.json"
        if branch_file.exists():
            branch_file.unlink()
            return True
        
        return False
    
    def list_branches(self) -> list[MemoryBranch]:
        """List all branches."""
        branches = []
        for branch_file in self.branches_dir.glob("*.json"):
            data = json.loads(branch_file.read_text(encoding="utf-8"))
            branches.append(MemoryBranch.from_dict(data))
        return sorted(branches, key=lambda b: b.name)
    
    def create_branch(
        self,
        name: str,
        persona: str | None = None,
        from_branch: str | None = None,
    ) -> MemoryBranch:
        """
        Create a new branch.
        
        Args:
            name: Name of the new branch.
            persona: Optional persona description.
            from_branch: Branch to fork from (default: current branch).
        
        Returns:
            The created branch.
        """
        source_name = from_branch or self.get_current_branch_name()
        source = self.get_branch(source_name)
        
        parent_head = source.head if source else None
        
        branch = MemoryBranch(name=name, head=parent_head, persona=persona)
        self.save_branch(branch)
        
        return branch
    
    def switch_branch(self, name: str) -> bool:
        """
        Switch to a different branch.
        
        Args:
            name: Branch name.
        
        Returns:
            True if successful.
        """
        branch = self.get_branch(name)
        if branch is None:
            return False
        
        self.set_current_branch(name)
        return True
    
    def merge_branch(
        self,
        source_name: str,
        target_name: str | None = None,
        message: str | None = None,
    ) -> MemoryCommit | None:
        """
        Merge one branch into another.
        
        This creates a new commit on the target branch that includes all
        events from the source branch that are not already in the target.
        
        Args:
            source_name: Branch to merge from.
            target_name: Branch to merge into (default: current branch).
            message: Optional commit message.
        
        Returns:
            The merge commit, or None if nothing to merge.
        """
        target_name = target_name or self.get_current_branch_name()
        
        source = self.get_branch(source_name)
        target = self.get_branch(target_name)
        
        if source is None or target is None:
            return None
        
        if source.head is None:
            return None  # Nothing to merge
        
        # Get events from source that are not in target
        source_events = set()
        if source.head:
            for event in self.ledger.get_all_events_up_to(source.head):
                source_events.add(event.id)
        
        target_events = set()
        if target.head:
            for event in self.ledger.get_all_events_up_to(target.head):
                target_events.add(event.id)
        
        new_event_ids = source_events - target_events
        
        if not new_event_ids:
            return None  # Nothing new to merge
        
        # Create merge commit
        commit = MemoryCommit(
            branch=target_name,
            events=list(new_event_ids),
            message=message or f"Merge branch '{source_name}' into '{target_name}'",
            parent_id=target.head,
            metadata={"merge_source": source_name, "merge_source_head": source.head},
        )
        
        self.ledger.append_commit(commit)
        
        # Update target branch
        target.head = commit.id
        self.save_branch(target)
        
        return commit
    
    def cherry_pick(
        self,
        commit_id: str,
        target_name: str | None = None,
        message: str | None = None,
    ) -> MemoryCommit | None:
        """
        Cherry-pick a commit to another branch.
        
        Copies the events from the specified commit to the target branch.
        
        Args:
            commit_id: ID of the commit to cherry-pick.
            target_name: Target branch (default: current branch).
            message: Optional commit message.
        
        Returns:
            The new commit, or None if failed.
        """
        target_name = target_name or self.get_current_branch_name()
        target = self.get_branch(target_name)
        
        if target is None:
            return None
        
        source_commit = self.ledger.get_commit(commit_id)
        if source_commit is None:
            return None
        
        # Create new commit with same events
        commit = MemoryCommit(
            branch=target_name,
            events=source_commit.events,
            message=message or f"Cherry-pick: {source_commit.message}",
            parent_id=target.head,
            metadata={"cherry_pick_from": commit_id},
        )
        
        self.ledger.append_commit(commit)
        
        # Update target branch
        target.head = commit.id
        self.save_branch(target)
        
        return commit
    
    def get_branch_diff(
        self,
        branch_a: str,
        branch_b: str,
    ) -> tuple[list[str], list[str]]:
        """
        Compare two branches.
        
        Returns event IDs that are unique to each branch.
        
        Args:
            branch_a: First branch name.
            branch_b: Second branch name.
        
        Returns:
            Tuple of (events only in A, events only in B).
        """
        a = self.get_branch(branch_a)
        b = self.get_branch(branch_b)
        
        events_a = set()
        events_b = set()
        
        if a and a.head:
            for event in self.ledger.get_all_events_up_to(a.head):
                events_a.add(event.id)
        
        if b and b.head:
            for event in self.ledger.get_all_events_up_to(b.head):
                events_b.add(event.id)
        
        only_in_a = list(events_a - events_b)
        only_in_b = list(events_b - events_a)
        
        return only_in_a, only_in_b
