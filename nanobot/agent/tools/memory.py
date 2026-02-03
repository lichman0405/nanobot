"""
Memory tools - Git-like memory operations for agent self-management.

These tools expose the memory system to the agent, allowing autonomous:
- Memory search and retrieval
- Memory storage and updates
- Memory forgetting
- Branch/persona management
- History inspection
- Memory consolidation

This is the key to "autonomous memory management" - the agent can
actively decide what to remember, forget, and how to organize memories.
"""

from typing import Any
import json

from nanobot.agent.tools.base import Tool
from nanobot.agent.memory import MemoryStore, MemoryEvent


class MemorySearchTool(Tool):
    """Search through memories by query or filters."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_search"
    
    @property
    def description(self) -> str:
        return (
            "Search your long-term memories. Use when you need to recall "
            "specific information about the user, past decisions, preferences, "
            "or previously learned facts. Returns matching memories with their "
            "confidence scores and sources."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in memories (searches subject, predicate, object)"
                },
                "subject": {
                    "type": "string",
                    "description": "Filter by subject (e.g., 'user', 'project')"
                },
                "predicate": {
                    "type": "string",
                    "description": "Filter by predicate (e.g., 'prefers', 'works at')"
                },
                "scope": {
                    "type": "string",
                    "description": "Filter by scope (e.g., 'permanent', 'work', 'personal')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)"
                }
            },
            "required": []
        }
    
    async def execute(
        self,
        query: str | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        scope: str | None = None,
        limit: int = 10,
    ) -> str:
        try:
            # Get all memories from view
            memories = self._store.view.get_all()
            
            results = []
            query_lower = query.lower() if query else None
            
            for event in memories:
                # Text search
                if query_lower:
                    searchable = f"{event.subject} {event.predicate} {event.object}".lower()
                    if query_lower not in searchable:
                        continue
                
                # Filters
                if subject and event.subject != subject:
                    continue
                if predicate and event.predicate != predicate:
                    continue
                if scope and event.scope != scope:
                    continue
                
                results.append(event)
            
            if not results:
                return "No memories found matching your criteria."
            
            # Sort by confidence (highest first), then by timestamp (newest first)
            results.sort(key=lambda e: (-e.confidence, e.timestamp), reverse=False)
            results = results[:limit]
            
            # Format output
            lines = [f"Found {len(results)} memories:\n"]
            for i, e in enumerate(results, 1):
                lines.append(
                    f"{i}. {e.subject} {e.predicate} {e.object}\n"
                    f"   [scope: {e.scope or 'default'}, confidence: {e.confidence:.0%}, "
                    f"source: {e.source}, id: {e.id[:8]}]"
                )
            
            return "\n".join(lines)
            
        except Exception as ex:
            return f"Error searching memories: {ex}"


class MemoryAddTool(Tool):
    """Add a new memory."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_add"
    
    @property
    def description(self) -> str:
        return (
            "Store information in long-term memory. Use when you learn something "
            "important about the user (preferences, facts, decisions) or when "
            "the user explicitly asks you to remember something. Memories persist "
            "across sessions."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Who/what this is about (e.g., 'user', 'project:nanobot')"
                },
                "predicate": {
                    "type": "string",
                    "description": "The relationship (e.g., 'is named', 'prefers', 'works at')"
                },
                "object": {
                    "type": "string",
                    "description": "The value (e.g., 'Alice', 'dark mode', 'Google')"
                },
                "scope": {
                    "type": "string",
                    "description": "Context scope (e.g., 'permanent', 'work', 'personal', project name)"
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0 (default: 0.9). Use lower for uncertain info."
                },
                "evidence": {
                    "type": "string",
                    "description": "Source/evidence for this memory (optional)"
                }
            },
            "required": ["subject", "predicate", "object"]
        }
    
    async def execute(
        self,
        subject: str,
        predicate: str,
        object: str,
        scope: str | None = None,
        confidence: float = 0.9,
        evidence: str | None = None,
    ) -> str:
        try:
            event = MemoryEvent(
                event_type="add",
                subject=subject,
                predicate=predicate,
                object=object,
                scope=scope,
                confidence=min(1.0, max(0.0, confidence)),
                source="agent_tool",
                evidence=evidence,
                sensitivity="normal",
            )
            
            commit = self._store.commit(
                events=[event],
                message=f"Add: {subject} {predicate} {object}",
            )
            
            return (
                f"✓ Memory stored\n"
                f"  {subject} {predicate} {object}\n"
                f"  [scope: {scope or 'default'}, confidence: {confidence:.0%}]\n"
                f"  commit: {commit.id[:8]}"
            )
            
        except Exception as ex:
            return f"Error storing memory: {ex}"


class MemoryForgetTool(Tool):
    """Forget a specific memory."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_forget"
    
    @property
    def description(self) -> str:
        return (
            "Forget specific information. Use when the user says 'forget that', "
            "when information is outdated, or when correcting wrong memories. "
            "The original memory is preserved in history but marked as forgotten."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Subject of the memory to forget"
                },
                "predicate": {
                    "type": "string",
                    "description": "Predicate of the memory to forget"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for forgetting (for audit trail)"
                }
            },
            "required": ["subject", "predicate"]
        }
    
    async def execute(
        self,
        subject: str,
        predicate: str,
        reason: str = "User requested",
    ) -> str:
        try:
            # Find existing memory
            existing = self._store.view.get(subject, predicate)
            parent_id = existing.id if existing else None
            
            event = MemoryEvent(
                event_type="forget",
                subject=subject,
                predicate=predicate,
                object=reason,
                scope="permanent",
                confidence=1.0,
                source="agent_tool",
                parent_id=parent_id,
            )
            
            commit = self._store.commit(
                events=[event],
                message=f"Forget: {subject} {predicate}",
            )
            
            return (
                f"✓ Memory forgotten\n"
                f"  {subject} {predicate}\n"
                f"  reason: {reason}\n"
                f"  commit: {commit.id[:8]}"
            )
            
        except Exception as ex:
            return f"Error forgetting memory: {ex}"


class MemoryUpdateTool(Tool):
    """Update an existing memory with new information."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_update"
    
    @property
    def description(self) -> str:
        return (
            "Update an existing memory with new value. Use when information "
            "changes (e.g., user got a new job, changed preferences). Creates "
            "a modification event linking to the old memory."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Subject of the memory to update"
                },
                "predicate": {
                    "type": "string",
                    "description": "Predicate of the memory to update"
                },
                "new_value": {
                    "type": "string",
                    "description": "The new value"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the update"
                }
            },
            "required": ["subject", "predicate", "new_value"]
        }
    
    async def execute(
        self,
        subject: str,
        predicate: str,
        new_value: str,
        reason: str = "Updated information",
    ) -> str:
        try:
            # Find existing memory
            existing = self._store.view.get(subject, predicate)
            
            if not existing:
                return f"No existing memory found for '{subject} {predicate}'. Use memory_add instead."
            
            old_value = existing.object
            
            # Create modify event
            event = MemoryEvent(
                event_type="modify",
                subject=subject,
                predicate=predicate,
                object=new_value,
                scope=existing.scope,
                confidence=0.95,
                source="agent_tool",
                evidence=f"Updated from '{old_value}'. Reason: {reason}",
                parent_id=existing.id,
            )
            
            commit = self._store.commit(
                events=[event],
                message=f"Update: {subject} {predicate}",
            )
            
            return (
                f"✓ Memory updated\n"
                f"  {subject} {predicate}: {old_value} → {new_value}\n"
                f"  reason: {reason}\n"
                f"  commit: {commit.id[:8]}"
            )
            
        except Exception as ex:
            return f"Error updating memory: {ex}"


class MemoryBranchTool(Tool):
    """Manage memory branches (personas)."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_branch"
    
    @property
    def description(self) -> str:
        return (
            "Manage memory branches for different personas/contexts. Each branch "
            "maintains separate memories. Use 'list' to see branches, 'switch' to "
            "change active branch, 'create' for new persona."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "current", "switch", "create"],
                    "description": "Action to perform"
                },
                "name": {
                    "type": "string",
                    "description": "Branch name (for switch/create)"
                },
                "persona": {
                    "type": "string",
                    "description": "Persona description (for create)"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        name: str | None = None,
        persona: str | None = None,
    ) -> str:
        try:
            if action == "list":
                branches = self._store.list_branches()
                current = self._store.get_current_branch()
                lines = ["Memory branches:"]
                for b in branches:
                    marker = "→ " if b.name == current else "  "
                    desc = f" ({b.persona})" if b.persona else ""
                    lines.append(f"{marker}{b.name}{desc}")
                return "\n".join(lines)
            
            elif action == "current":
                current = self._store.get_current_branch()
                branch = self._store.get_branch(current)
                persona_info = f" (persona: {branch.persona})" if branch and branch.persona else ""
                return f"Current branch: {current}{persona_info}"
            
            elif action == "switch":
                if not name:
                    return "Error: 'name' is required for switch action"
                if self._store.switch_branch(name):
                    return f"✓ Switched to branch '{name}'"
                else:
                    return f"Error: Branch '{name}' does not exist"
            
            elif action == "create":
                if not name:
                    return "Error: 'name' is required for create action"
                branch = self._store.create_branch(name, persona=persona)
                self._store.switch_branch(name)
                return f"✓ Created and switched to branch '{name}'"
            
            else:
                return f"Unknown action: {action}"
            
        except Exception as ex:
            return f"Error managing branches: {ex}"


class MemoryHistoryTool(Tool):
    """View memory commit history."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_history"
    
    @property
    def description(self) -> str:
        return (
            "View the history of memory changes. Shows commits with timestamps "
            "and messages. Useful for understanding when and why memories changed."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum commits to show (default: 10)"
                },
                "show_events": {
                    "type": "boolean",
                    "description": "Show events in each commit (default: false)"
                }
            },
            "required": []
        }
    
    async def execute(
        self,
        limit: int = 10,
        show_events: bool = False,
    ) -> str:
        try:
            history = self._store.get_history(max_commits=limit)
            
            if not history:
                return "No memory history yet."
            
            lines = [f"Memory history ({len(history)} commits):\n"]
            
            for commit in history:
                time_str = commit.timestamp.strftime("%Y-%m-%d %H:%M")
                lines.append(f"[{commit.id[:8]}] {time_str} - {commit.message}")
                
                if show_events:
                    for event_id in commit.events:
                        event = self._store.ledger.get_event(event_id)
                        if event:
                            lines.append(
                                f"    {event.event_type}: {event.subject} "
                                f"{event.predicate} {event.object}"
                            )
            
            return "\n".join(lines)
            
        except Exception as ex:
            return f"Error getting history: {ex}"


class MemoryConsolidateTool(Tool):
    """Consolidate and clean up memories."""
    
    def __init__(self, store: MemoryStore):
        self._store = store
    
    @property
    def name(self) -> str:
        return "memory_consolidate"
    
    @property
    def description(self) -> str:
        return (
            "Review and consolidate memories. Use during idle time (heartbeat) to: "
            "1) Identify duplicate or similar memories to merge, "
            "2) Find outdated memories to forget, "
            "3) Review low-confidence memories. "
            "Returns a report of memories that may need attention."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["report", "find_duplicates", "find_low_confidence", "stats"],
                    "description": "What to analyze"
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, action: str) -> str:
        try:
            memories = self._store.view.get_all()
            
            if action == "stats":
                branches = self._store.list_branches()
                commits = self._store.ledger.count_commits()
                events = self._store.ledger.count_events()
                
                # Group by scope
                scopes: dict[str, int] = {}
                for m in memories:
                    scope = m.scope or "default"
                    scopes[scope] = scopes.get(scope, 0) + 1
                
                lines = [
                    f"Memory Statistics:",
                    f"  Active memories: {len(memories)}",
                    f"  Total events: {events}",
                    f"  Total commits: {commits}",
                    f"  Branches: {len(branches)}",
                    f"\nBy scope:"
                ]
                for scope, count in sorted(scopes.items()):
                    lines.append(f"  {scope}: {count}")
                
                return "\n".join(lines)
            
            elif action == "find_duplicates":
                # Group by subject+predicate
                groups: dict[str, list] = {}
                for m in memories:
                    key = f"{m.subject}|{m.predicate}"
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(m)
                
                duplicates = [(k, v) for k, v in groups.items() if len(v) > 1]
                
                if not duplicates:
                    return "No potential duplicates found."
                
                lines = ["Potential duplicates found:\n"]
                for key, mems in duplicates:
                    lines.append(f"  {key}:")
                    for m in mems:
                        lines.append(f"    - {m.object} (scope: {m.scope}, id: {m.id[:8]})")
                
                return "\n".join(lines)
            
            elif action == "find_low_confidence":
                low_conf = [m for m in memories if m.confidence < 0.7]
                
                if not low_conf:
                    return "No low-confidence memories found."
                
                lines = [f"Low-confidence memories ({len(low_conf)}):\n"]
                for m in sorted(low_conf, key=lambda x: x.confidence):
                    lines.append(
                        f"  [{m.confidence:.0%}] {m.subject} {m.predicate} {m.object}"
                    )
                
                return "\n".join(lines)
            
            elif action == "report":
                # Generate full consolidation report
                low_conf = [m for m in memories if m.confidence < 0.7]
                
                # Find old memories (by timestamp, rough heuristic)
                old_count = sum(1 for m in memories if "session" in (m.scope or ""))
                
                lines = [
                    "Memory Consolidation Report:",
                    f"  Total active memories: {len(memories)}",
                    f"  Low confidence (<70%): {len(low_conf)}",
                    f"  Session-scoped (may need upgrade): {old_count}",
                    "",
                    "Recommendations:",
                ]
                
                if low_conf:
                    lines.append("  - Review low-confidence memories with find_low_confidence")
                if old_count > 0:
                    lines.append("  - Consider upgrading session memories to permanent")
                if len(memories) > 50:
                    lines.append("  - Consider archiving old memories")
                
                if len(low_conf) == 0 and old_count == 0:
                    lines.append("  - Memories look healthy, no action needed")
                
                return "\n".join(lines)
            
            else:
                return f"Unknown action: {action}"
            
        except Exception as ex:
            return f"Error consolidating: {ex}"


def create_memory_tools(store: MemoryStore) -> list[Tool]:
    """Create all memory tools for the given store."""
    return [
        MemorySearchTool(store),
        MemoryAddTool(store),
        MemoryForgetTool(store),
        MemoryUpdateTool(store),
        MemoryBranchTool(store),
        MemoryHistoryTool(store),
        MemoryConsolidateTool(store),
    ]


def register_memory_tools(registry, store: MemoryStore) -> None:
    """Register all memory tools with a tool registry."""
    for tool in create_memory_tools(store):
        registry.register(tool)
