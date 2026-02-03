"""
Git-like memory system for nanobot.

This module provides a versioned, traceable memory architecture inspired by git,
supporting:
- Immutable event ledger (append-only)
- Content-addressable storage (SHA256 hashing)
- Branch-based persona isolation
- LLM-driven autonomous memory management
"""

from nanobot.agent.memory.event import MemoryEvent
from nanobot.agent.memory.commit import MemoryCommit
from nanobot.agent.memory.branch import MemoryBranch
from nanobot.agent.memory.store import MemoryStore
from nanobot.agent.memory.controller import MemoryController

__all__ = [
    "MemoryEvent",
    "MemoryCommit",
    "MemoryBranch",
    "MemoryStore",
    "MemoryController",
]
