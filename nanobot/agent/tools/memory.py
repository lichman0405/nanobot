"""Memory tools for LLM to actively query and store memories."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.memory import MemoryStore, MemoryEvent


class MemoryRecallTool(Tool):
    """
    Tool for LLM to search and recall memories.
    
    Unlike passive injection which loads all memories into context,
    this allows targeted retrieval of specific information.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "memory_recall"
    
    @property
    def description(self) -> str:
        return (
            "Search through your long-term memories. Use when you need to recall "
            "specific information about the user, past decisions, preferences, "
            "or previously discussed topics. More efficient than scanning all memories."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memories (e.g., 'user's name', 'preferred programming language')"
                },
                "scope": {
                    "type": "string",
                    "enum": ["all", "permanent", "session"],
                    "description": "Filter by memory scope. Default: all"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 5"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, scope: str = "all", limit: int = 5) -> str:
        """Search memories and return matching results."""
        try:
            # Get current view using search method
            view = self._memory.view
            
            # Use the view's search capability
            results = view.search(scope=scope if scope != "all" else None)
            
            # Filter by query text
            query_lower = query.lower()
            matches = []
            for event in results:
                searchable = f"{event.subject} {event.predicate} {event.object}".lower()
                if query_lower in searchable:
                    matches.append(event)
            
            if not matches:
                return f"No memories found matching '{query}'"
            
            # Sort by timestamp (newest first) and limit
            matches.sort(key=lambda e: e.timestamp, reverse=True)
            matches = matches[:limit]
            
            # Format output
            output = [f"Found {len(matches)} memories matching '{query}':\n"]
            for i, event in enumerate(matches, 1):
                output.append(
                    f"{i}. [{event.scope}] {event.subject} {event.predicate} {event.object}"
                    f"\n   (confidence: {event.confidence:.1%}, source: {event.source})"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error searching memories: {str(e)}"


class MemoryStoreTool(Tool):
    """
    Tool for LLM to explicitly store important information.
    
    Use this for information that should definitely be remembered,
    separate from the automatic memory extraction.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "memory_store"
    
    @property
    def description(self) -> str:
        return (
            "Save important information to long-term memory. Use when the user "
            "says 'remember this', shares preferences, makes decisions, or provides "
            "information that should persist across sessions."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "What or who this is about (e.g., 'user', 'project X', 'coding preferences')"
                },
                "predicate": {
                    "type": "string",
                    "description": "The relationship or property (e.g., 'prefers', 'works at', 'is named')"
                },
                "object": {
                    "type": "string",
                    "description": "The value (e.g., 'dark mode', 'Google', 'Alice')"
                },
                "scope": {
                    "type": "string",
                    "enum": ["permanent", "session", "temporary"],
                    "description": "How long to remember: permanent (forever), session (this conversation), temporary (short-term). Default: permanent"
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level 0.0-1.0. Use lower values for uncertain info. Default: 0.9"
                }
            },
            "required": ["subject", "predicate", "object"]
        }
    
    async def execute(
        self, 
        subject: str, 
        predicate: str, 
        object: str,
        scope: str = "permanent",
        confidence: float = 0.9
    ) -> str:
        """Store a memory event."""
        try:
            event = MemoryEvent(
                event_type="add",
                subject=subject,
                predicate=predicate,
                object=object,
                scope=scope,  # type: ignore
                confidence=min(1.0, max(0.0, confidence)),
                source="memory_store_tool",
                evidence=None,
                sensitivity="normal"
            )
            
            # Commit with the event
            commit = self._memory.commit(
                events=[event],
                message=f"Stored: {subject} {predicate} {object}"
            )
            
            return (
                f"✓ Memory stored successfully\n"
                f"  {subject} {predicate} {object}\n"
                f"  Scope: {scope}, Confidence: {confidence:.0%}\n"
                f"  Commit: {commit.id[:8]}"
            )
            
        except Exception as e:
            return f"Error storing memory: {str(e)}"


class MemoryForgetTool(Tool):
    """
    Tool for LLM to forget specific information.
    
    Creates a 'forget' event which marks the information as outdated/removed.
    The original event is preserved for traceability.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "memory_forget"
    
    @property
    def description(self) -> str:
        return (
            "Forget specific information. Use when the user says 'forget that', "
            "corrects previous information, or when information becomes outdated. "
            "The original memory is preserved for history but marked as forgotten."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "What to forget about (e.g., 'user', 'old phone number')"
                },
                "predicate": {
                    "type": "string",
                    "description": "The relationship to forget (e.g., 'phone number is', 'lives at')"
                },
                "reason": {
                    "type": "string",
                    "description": "Why this is being forgotten (optional, for audit trail)"
                }
            },
            "required": ["subject", "predicate"]
        }
    
    async def execute(
        self, 
        subject: str, 
        predicate: str,
        reason: str = "User requested"
    ) -> str:
        """Create a forget event."""
        try:
            # Find matching memories to get parent_id
            view = self._memory.view
            memories = view.get_all()
            
            parent_id = None
            for event in memories:
                if event.subject == subject and event.predicate == predicate:
                    parent_id = event.id
                    break
            
            forget_event = MemoryEvent(
                event_type="forget",
                subject=subject,
                predicate=predicate,
                object=reason,
                scope="permanent",
                confidence=1.0,
                source="memory_forget_tool",
                evidence=None,
                sensitivity="normal",
                parent_id=parent_id
            )
            
            commit = self._memory.commit(
                events=[forget_event],
                message=f"Forgot: {subject} {predicate}"
            )
            
            return (
                f"✓ Memory forgotten\n"
                f"  Forgot: {subject} {predicate}\n"
                f"  Reason: {reason}\n"
                f"  Commit: {commit.id[:8]}"
            )
            
        except Exception as e:
            return f"Error forgetting memory: {str(e)}"


class MemoryBranchTool(Tool):
    """
    Tool for LLM to switch personas/branches.
    
    Different branches can have different memories, useful for
    context-specific interactions.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "memory_branch"
    
    @property
    def description(self) -> str:
        return (
            "Switch to a different memory branch/persona. Each branch has its own "
            "set of memories. Use for context switching (e.g., 'coding-assistant' vs "
            "'creative-writer'). Creates the branch if it doesn't exist."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Branch name to switch to (e.g., 'main', 'coding-assistant')"
                },
                "persona": {
                    "type": "string",
                    "description": "Description of this persona (only for new branches)"
                }
            },
            "required": ["branch"]
        }
    
    async def execute(self, branch: str, persona: str | None = None) -> str:
        """Switch to a different memory branch."""
        try:
            current = self._memory.get_current_branch()
            
            # Check if branch exists
            if not self._memory.get_branch(branch):
                # Create new branch
                self._memory.create_branch(branch, persona=persona)
                self._memory.switch_branch(branch)
                return (
                    f"✓ Created and switched to new branch '{branch}'\n"
                    f"  Persona: {persona or 'default'}\n"
                    f"  Previous branch: {current}"
                )
            else:
                self._memory.switch_branch(branch)
                return f"✓ Switched from '{current}' to '{branch}'"
            
        except Exception as e:
            return f"Error switching branch: {str(e)}"


def register_memory_tools(registry: "ToolRegistry", memory_store: MemoryStore) -> None:
    """Register all memory tools with the given registry."""
    registry.register(MemoryRecallTool(memory_store))
    registry.register(MemoryStoreTool(memory_store))
    registry.register(MemoryForgetTool(memory_store))
    registry.register(MemoryBranchTool(memory_store))
