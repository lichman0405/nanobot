"""Long-term memory tools for the agent."""

from typing import Any
from pathlib import Path

from nanobot.agent.tools.base import Tool
from nanobot.agent.memory import MemoryStore
from nanobot.providers.base import LLMProvider


class RememberTool(Tool):
    """
    Tool to save important information to long-term memory.
    
    Uses daily notes for memory storage with timestamps.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "remember"
    
    @property
    def description(self) -> str:
        return (
            "Save important information to long-term memory. "
            "Use this to remember facts about the user, preferences, "
            "ongoing projects, or anything that should be recalled later."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The information to remember (be specific and concise)"
                },
                "category": {
                    "type": "string",
                    "description": "Optional category (e.g., 'user_info', 'preferences', 'project')",
                },
                "importance": {
                    "type": "string",
                    "description": "Optional importance level: 'low', 'medium', 'high'",
                    "enum": ["low", "medium", "high"]
                }
            },
            "required": ["fact"]
        }
    
    async def execute(
        self, 
        fact: str, 
        category: str | None = None,
        importance: str | None = None,
        **kwargs: Any
    ) -> str:
        """
        Save a fact to memory using dual-track storage:
        1. Daily notes (YYYY-MM-DD.md): Raw timestamped record
        2. Knowledge base (MEMORY.md): Structured, deduplicated via lifecycle
        """
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%H:%M")
        cat = category or "general"
        
        # ========== TRACK 1: Always write to daily notes ==========
        entry_parts = [f"- [{timestamp}]"]
        if importance:
            importance_emoji = {"low": "ℹ️", "medium": "⭐", "high": "🔥"}
            entry_parts.append(importance_emoji.get(importance, ""))
        if category:
            entry_parts.append(f"`{category}`")
        entry_parts.append(fact)
        entry = " ".join(entry_parts)
        self._memory.append_today(entry)
        
        # ========== TRACK 2: Update knowledge base with lifecycle ==========
        if hasattr(self._memory, 'lifecycle_update'):
            try:
                result = await self._memory.lifecycle_update(
                    new_facts=[fact],
                    category=cat.title()
                )
                
                # Build response based on lifecycle action
                fact_preview = f"{fact[:50]}{'...' if len(fact) > 50 else ''}"
                if result["add"]:
                    return f"✓ Added to memory: {fact_preview}"
                elif result["update"]:
                    return f"✓ Updated memory: {fact_preview}"
                elif result["delete"]:
                    return f"✓ Replaced old info: {fact_preview}"
                elif result["noop"]:
                    return f"ℹ️ Already known: {fact_preview}"
                else:
                    return f"✓ Remembered: {fact_preview}"
                
            except Exception as e:
                # Lifecycle failed but daily note was written
                return f"✓ Saved to daily notes: {fact[:50]}{'...' if len(fact) > 50 else ''}"
        
        return f"✓ Remembered: {fact[:50]}{'...' if len(fact) > 50 else ''}"
        
        return f"✓ Remembered: {fact[:50]}{'...' if len(fact) > 50 else ''}"


class RecallTool(Tool):
    """
    Tool to recall relevant information from memory using scratchpad method.
    
    Uses the Anthropic scratchpad approach: quickly scan recent memories
    and present relevant facts without heavy vector search.
    """
    
    def __init__(self, memory_store: MemoryStore, llm_provider: LLMProvider | None = None):
        self._memory = memory_store
        self._llm = llm_provider
    
    @property
    def name(self) -> str:
        return "recall"
    
    @property
    def description(self) -> str:
        return (
            "Recall relevant information from long-term memory. "
            "Use this to remember what you know about the user, "
            "past conversations, or stored facts. Provide context "
            "about what you need to recall."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What information are you trying to recall? (e.g., 'user preferences', 'project status')"
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to search (default: 7)",
                    "minimum": 1,
                    "maximum": 30
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self, 
        query: str, 
        days_back: int = 7,
        **kwargs: Any
    ) -> str:
        """Recall relevant memories."""
        # Get recent memories
        recent = self._memory.get_recent_memories(days=days_back)
        long_term = self._memory.read_long_term()
        
        # Combine memory sources
        all_memories = []
        if long_term:
            all_memories.append(f"**Long-term Memory:**\n{long_term}")
        if recent:
            all_memories.append(f"**Recent Notes ({days_back} days):**\n{recent}")
        
        if not all_memories:
            return "No memories found."
        
        combined = "\n\n---\n\n".join(all_memories)
        
        # If LLM is available, use scratchpad method to filter relevant info
        if self._llm:
            try:
                response = await self._llm.chat(
                    messages=[
                        {
                            "role": "user",
                            "content": f"""You are a memory assistant. Given this query: "{query}"

Extract and return ONLY the relevant facts from these memories. Be concise.
If nothing is relevant, return "No relevant memories found."

Memories:
{combined[:4000]}  # Limit context size
"""
                        }
                    ],
                    max_tokens=500,
                    temperature=0.3,
                )
                
                if response and response.content:
                    return response.content
            except Exception as e:
                # Fall back to simple return if LLM fails
                pass
        
        # Fallback: simple keyword matching
        lines = combined.split('\n')
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        relevant_lines = []
        for line in lines:
            line_lower = line.lower()
            # Check if any query word appears in the line
            if any(word in line_lower for word in query_words if len(word) > 2):
                relevant_lines.append(line)
        
        if relevant_lines:
            return "\n".join(relevant_lines[:20])  # Limit to 20 most recent matches
        
        return "No relevant memories found."


class SearchMemoryTool(Tool):
    """
    Tool to search through memory files with text matching.
    
    Provides simple but effective text search across all memory files.
    """
    
    def __init__(self, memory_store: MemoryStore):
        self._memory = memory_store
    
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return (
            "Search through all memory files for specific keywords or phrases. "
            "Returns matching entries with dates and context."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Keywords or phrase to search for"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)",
                    "minimum": 1,
                    "maximum": 50
                }
            },
            "required": ["keywords"]
        }
    
    async def execute(
        self, 
        keywords: str, 
        max_results: int = 10,
        **kwargs: Any
    ) -> str:
        """Search memory files."""
        keywords_lower = keywords.lower()
        results = []
        
        # Search long-term memory
        long_term = self._memory.read_long_term()
        if long_term and keywords_lower in long_term.lower():
            results.append({
                "source": "MEMORY.md",
                "content": long_term,
                "date": "Long-term"
            })
        
        # Search daily notes
        memory_files = self._memory.list_memory_files()
        for memory_file in memory_files[:60]:  # Last 60 days max
            try:
                content = memory_file.read_text(encoding="utf-8")
                if keywords_lower in content.lower():
                    # Extract relevant lines
                    lines = content.split('\n')
                    matching_lines = [
                        line for line in lines 
                        if keywords_lower in line.lower()
                    ]
                    
                    results.append({
                        "source": memory_file.name,
                        "content": '\n'.join(matching_lines[:5]),  # First 5 matches per file
                        "date": memory_file.stem  # YYYY-MM-DD
                    })
                    
                    if len(results) >= max_results:
                        break
            except Exception:
                continue
        
        # Format results
        if not results:
            return f"No matches found for '{keywords}'"
        
        formatted = [f"Found {len(results)} matches for '{keywords}':\n"]
        for i, result in enumerate(results[:max_results], 1):
            formatted.append(f"\n**[{result['date']}] {result['source']}**")
            formatted.append(result['content'][:300])  # Limit content length
            if len(result['content']) > 300:
                formatted.append("...")
        
        return '\n'.join(formatted)
