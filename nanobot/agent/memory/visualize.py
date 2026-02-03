"""
Memory visualization utilities.

Provides various formats for visualizing memory history and structure.
"""

from datetime import datetime
from typing import Any

from nanobot.agent.memory.store import MemoryStore
from nanobot.agent.memory.commit import MemoryCommit
from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.branch import MemoryBranch


def format_commit_log(
    store: MemoryStore,
    max_commits: int = 20,
    show_events: bool = False,
) -> str:
    """
    Format commit history similar to `git log`.
    
    Args:
        store: The memory store.
        max_commits: Maximum commits to show.
        show_events: Whether to show event details.
    
    Returns:
        Formatted log string.
    """
    lines = []
    history = store.get_history(max_commits)
    current_branch = store.get_current_branch()
    
    if not history:
        return "No commits yet."
    
    for commit in history:
        # Commit header
        lines.append(f"commit {commit.id}")
        lines.append(f"Branch: {commit.branch}")
        lines.append(f"Date:   {commit.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if commit.parent_id:
            lines.append(f"Parent: {commit.parent_id[:8]}...")
        
        lines.append("")
        lines.append(f"    {commit.message}")
        lines.append("")
        
        # Show events if requested
        if show_events:
            events = store.ledger.get_events_for_commit(commit.id)
            for event in events:
                lines.append(f"    [{event.event_type}] {event.subject} {event.predicate} {event.object}")
            lines.append("")
        
        lines.append("")
    
    return "\n".join(lines)


def format_commit_oneline(store: MemoryStore, max_commits: int = 20) -> str:
    """
    Format commit history in one-line format similar to `git log --oneline`.
    
    Args:
        store: The memory store.
        max_commits: Maximum commits to show.
    
    Returns:
        Formatted log string.
    """
    lines = []
    history = store.get_history(max_commits)
    current_branch = store.get_current_branch()
    
    if not history:
        return "No commits yet."
    
    for i, commit in enumerate(history):
        prefix = "* " if i == 0 else "  "
        head_marker = " (HEAD)" if i == 0 else ""
        lines.append(f"{prefix}{commit.id[:8]} [{commit.branch}]{head_marker} {commit.message}")
    
    return "\n".join(lines)


def format_branches(store: MemoryStore) -> str:
    """
    Format branch list similar to `git branch`.
    
    Args:
        store: The memory store.
    
    Returns:
        Formatted branch list.
    """
    lines = []
    branches = store.list_branches()
    current = store.get_current_branch()
    
    for branch in sorted(branches, key=lambda b: b.name):
        marker = "* " if branch.name == current else "  "
        head_short = branch.head[:8] if branch.head else "empty"
        persona_str = f" ({branch.persona})" if branch.persona else ""
        lines.append(f"{marker}{branch.name}{persona_str} -> {head_short}")
    
    return "\n".join(lines)


def format_memory_view(store: MemoryStore, max_items: int = 50) -> str:
    """
    Format current memory view.
    
    Args:
        store: The memory store.
        max_items: Maximum items to show.
    
    Returns:
        Formatted memory view.
    """
    return store.view.to_context_string(max_items)


def generate_mermaid_graph(
    store: MemoryStore,
    max_commits: int = 20,
    show_branches: bool = True,
) -> str:
    """
    Generate a Mermaid diagram of the commit history.
    
    Args:
        store: The memory store.
        max_commits: Maximum commits to include.
        show_branches: Whether to show branch pointers.
    
    Returns:
        Mermaid diagram code.
    """
    lines = ["gitGraph"]
    
    # Get all branches and their histories
    branches = store.list_branches()
    current = store.get_current_branch()
    
    # Build commit graph
    all_commits: dict[str, MemoryCommit] = {}
    branch_commits: dict[str, list[MemoryCommit]] = {}
    
    for branch in branches:
        if branch.head:
            history = store.ledger.get_commit_history(branch.head)[:max_commits]
            branch_commits[branch.name] = history
            for commit in history:
                all_commits[commit.id] = commit
    
    if not all_commits:
        return "gitGraph\n    commit id: \"No commits\""
    
    # Sort commits by timestamp
    sorted_commits = sorted(all_commits.values(), key=lambda c: c.timestamp)
    
    # Track which branches have been created
    created_branches = set()
    current_branch = "main"
    
    for commit in sorted_commits:
        short_id = commit.id[:8]
        msg = commit.message[:30].replace('"', "'")
        
        # Check if we need to switch/create branch
        if commit.branch != current_branch:
            if commit.branch not in created_branches:
                lines.append(f'    branch {commit.branch}')
                created_branches.add(commit.branch)
            else:
                lines.append(f'    checkout {commit.branch}')
            current_branch = commit.branch
        
        # Check if this is a merge
        if commit.metadata.get("merge_source"):
            source = commit.metadata["merge_source"]
            lines.append(f'    merge {source} id: "{short_id}"')
        else:
            lines.append(f'    commit id: "{short_id}" message: "{msg}"')
    
    return "\n".join(lines)


def generate_mermaid_timeline(store: MemoryStore, max_events: int = 30) -> str:
    """
    Generate a Mermaid timeline of memory events.
    
    Args:
        store: The memory store.
        max_events: Maximum events to include.
    
    Returns:
        Mermaid timeline diagram code.
    """
    lines = ["timeline"]
    lines.append("    title Memory Timeline")
    
    memories = store.get_all_memories()
    
    if not memories:
        lines.append("    section No Memories")
        lines.append("        No events yet")
        return "\n".join(lines)
    
    # Group by date
    by_date: dict[str, list[MemoryEvent]] = {}
    for event in memories[-max_events:]:
        date_str = event.timestamp.strftime("%Y-%m-%d")
        if date_str not in by_date:
            by_date[date_str] = []
        by_date[date_str].append(event)
    
    for date_str in sorted(by_date.keys()):
        lines.append(f"    section {date_str}")
        for event in by_date[date_str]:
            desc = f"{event.subject} {event.predicate} {event.object}"
            desc = desc[:40].replace(":", "-")  # Mermaid-safe
            lines.append(f"        {desc}")
    
    return "\n".join(lines)


def format_event_detail(event: MemoryEvent) -> str:
    """
    Format detailed information about a single event.
    
    Args:
        event: The event to format.
    
    Returns:
        Formatted event details.
    """
    lines = [
        f"Event ID: {event.id}",
        f"Type:     {event.event_type}",
        f"",
        f"Content:",
        f"  Subject:   {event.subject}",
        f"  Predicate: {event.predicate}",
        f"  Object:    {event.object}",
        f"  Scope:     {event.scope or '(none)'}",
        f"",
        f"Metadata:",
        f"  Confidence: {event.confidence:.2f}",
        f"  Source:     {event.source}",
        f"  Sensitivity: {event.sensitivity}",
        f"  Timestamp:  {event.timestamp.isoformat()}",
    ]
    
    if event.parent_id:
        lines.append(f"  Parent:     {event.parent_id}")
    
    if event.evidence:
        lines.append(f"")
        lines.append(f"Evidence:")
        lines.append(f"  {event.evidence[:200]}...")
    
    return "\n".join(lines)
