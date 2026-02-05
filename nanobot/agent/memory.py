"""Memory system for persistent agent memory."""

import re
import html
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Literal
from collections import Counter

from loguru import logger

from nanobot.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """
    Memory system for the agent.
    
    Supports daily notes (memory/YYYY-MM-DD.md) and long-term memory (MEMORY.md).
    Enhanced with:
    - Mem0-inspired lifecycle management (ADD/UPDATE/DELETE/NOOP)
    - JIT (Just-In-Time) retrieval for relevant memories
    - Security hardening (path validation, content sanitization)
    """
    
    def __init__(self, workspace: Path, llm_provider: Any = None, config: Any = None):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self._llm = llm_provider
        self._config = config
    
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
        from datetime import timedelta
        
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
    
    async def smart_extract(self, conversation: list[dict[str, str]], max_facts: int = 3) -> list[str]:
        """
        Extract important facts from a conversation using LLM.
        
        Uses the Mem0 approach: ADD/UPDATE/DELETE lifecycle for facts.
        
        Args:
            conversation: List of message dicts with 'role' and 'content'.
            max_facts: Maximum number of facts to extract.
        
        Returns:
            List of extracted facts.
        """
        if not self._llm:
            logger.warning("LLM not available for smart extraction")
            return []
        
        # Build conversation text
        conv_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in conversation[-10:]  # Last 10 messages
        ])
        
        if len(conv_text) < 20:
            return []  # Too short to extract anything meaningful
        
        try:
            response = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory extraction assistant. Extract important, factual "
                            "information from conversations. Focus on: user preferences, personal "
                            "details, ongoing projects, goals, and constraints.\n"
                            "Output ONLY a numbered list of facts (max 3). Be concise and specific.\n"
                            "If nothing important, output 'NONE'."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract up to {max_facts} important facts:\n\n{conv_text[:2000]}"
                    }
                ],
                max_tokens=300,
                temperature=0.3,
            )
            
            if not response or not response.content:
                return []
            
            content = response.content.strip()
            if content.upper() == "NONE":
                return []
            
            # Parse numbered list
            facts = []
            for line in content.split('\n'):
                line = line.strip()
                # Match patterns like "1. ", "1) ", "- ", etc.
                if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                    # Remove list markers
                    fact = line.lstrip('0123456789.-*) \t')
                    if fact and len(fact) > 10:  # Meaningful length
                        facts.append(fact)
                        if len(facts) >= max_facts:
                            break
            
            return facts
            
        except Exception as e:
            logger.error(f"Smart extraction failed: {e}")
            return []
    
    async def smart_dedupe(self, facts: list[str]) -> list[str]:
        """
        Deduplicate facts using LLM to detect semantic similarity.
        
        This is expensive (LLM calls), so it's optional and disabled by default.
        
        Args:
            facts: List of facts to deduplicate.
        
        Returns:
            Deduplicated list of facts.
        """
        if not self._llm or not facts or len(facts) < 2:
            return facts
        
        # Check config
        if self._config and hasattr(self._config, 'memory'):
            if not self._config.memory.smart_dedupe:
                return facts  # Simple dedup disabled
        
        try:
            facts_text = "\n".join([f"{i+1}. {fact}" for i, fact in enumerate(facts)])
            
            response = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a deduplication assistant. Given a list of facts, "
                            "identify and merge duplicates or very similar items.\n"
                            "Output ONLY the deduplicated numbered list. Keep the most "
                            "informative version of each fact."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Deduplicate these facts:\n\n{facts_text}"
                    }
                ],
                max_tokens=500,
                temperature=0.2,
            )
            
            if not response or not response.content:
                return facts
            
            # Parse result
            deduped = []
            for line in response.content.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    fact = line.lstrip('0123456789.-*) \t')
                    if fact:
                        deduped.append(fact)
            
            return deduped if deduped else facts
            
        except Exception as e:
            logger.error(f"Smart deduplication failed: {e}")
            return facts
    
    async def consolidate_weekly(self, force: bool = False) -> bool:
        """
        Consolidate the past week's daily notes into long-term memory.
        
        This runs on a schedule (default: Sunday) and extracts important
        information from daily notes into MEMORY.md.
        
        Args:
            force: Force consolidation even if not the scheduled day.
        
        Returns:
            True if consolidation was performed.
        """
        if not self._llm:
            logger.info("LLM not available for consolidation")
            return False
        
        # Check if it's the scheduled day (default: Sunday = 6)
        if not force:
            if self._config and hasattr(self._config, 'memory'):
                consolidate_day = getattr(self._config.memory, 'consolidate_day', 'sunday')
                day_map = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6
                }
                target_day = day_map.get(consolidate_day.lower(), 6)
                
                if datetime.now().weekday() != target_day:
                    return False
        
        # Get past week's notes
        recent_notes = self.get_recent_memories(days=7)
        
        if not recent_notes or len(recent_notes) < 50:
            logger.info("Not enough recent notes to consolidate")
            return False
        
        try:
            # Ask LLM to consolidate
            response = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory consolidation assistant. Review the past week's "
                            "notes and extract the most important, enduring information.\n"
                            "Focus on: significant events, decisions, learnings, and facts "
                            "that should be remembered long-term.\n"
                            "Output a concise summary in markdown format."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Consolidate these weekly notes:\n\n{recent_notes[:4000]}"
                    }
                ],
                max_tokens=800,
                temperature=0.3,
            )
            
            if response and response.content:
                # Append to long-term memory
                existing = self.read_long_term()
                week_str = datetime.now().strftime("%Y-W%U")
                
                consolidated = f"\n\n## Week of {week_str}\n{response.content}"
                
                if existing:
                    self.write_long_term(existing + consolidated)
                else:
                    self.write_long_term(consolidated.lstrip())
                
                logger.info(f"Weekly consolidation completed for {week_str}")
                return True
                
        except Exception as e:
            logger.error(f"Weekly consolidation failed: {e}")
        
        return False
    
    def simple_search(self, query: str, days_back: int = 30) -> list[str]:
        """
        Simple text-based search through recent memories.
        
        Fast and efficient fallback when LLM is not available.
        
        Args:
            query: Search query string.
            days_back: How many days back to search.
        
        Returns:
            List of matching lines.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())
        matches = []
        
        # Search long-term memory
        long_term = self.read_long_term()
        if long_term:
            for line in long_term.split('\n'):
                if any(word in line.lower() for word in query_words if len(word) > 2):
                    matches.append(f"[MEMORY.md] {line.strip()}")
        
        # Search recent daily notes
        today = datetime.now().date()
        for i in range(days_back):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                for line in content.split('\n'):
                    if any(word in line.lower() for word in query_words if len(word) > 2):
                        matches.append(f"[{date_str}] {line.strip()}")
        
        return matches[:50]  # Limit results
    
    # ========== Security & Validation ==========
    
    def _validate_path(self, path: Path) -> bool:
        """
        Validate that a path is within the memory directory.
        
        Prevents path traversal attacks.
        """
        try:
            resolved = path.resolve()
            memory_resolved = self.memory_dir.resolve()
            return resolved.is_relative_to(memory_resolved)
        except (ValueError, OSError):
            return False
    
    def _validate_content(self, content: str) -> str:
        """
        Validate and sanitize content.
        
        Args:
            content: Content to validate.
        
        Returns:
            Sanitized content.
        
        Raises:
            ValueError: If content is too large or invalid.
        """
        max_size = 8192
        if self._config and hasattr(self._config, 'memory'):
            max_size = getattr(self._config.memory, 'max_content_size', 8192)
        
        if len(content.encode('utf-8')) > max_size:
            raise ValueError(f"Content exceeds maximum size of {max_size} bytes")
        
        # HTML escape to prevent injection
        content = html.escape(content, quote=False)
        
        # Remove potential script tags
        content = re.sub(r'</?script[^>]*>', '', content, flags=re.IGNORECASE)
        
        return content
    
    # ========== Mem0-Inspired Lifecycle Management ==========
    
    def _append_to_section(self, content: str, section_name: str, new_items: list[str]) -> str:
        """
        Append items to an existing section, or create section if not exists.
        
        Args:
            content: The full MEMORY.md content.
            section_name: Section header (without ##).
            new_items: List of items to append (will be prefixed with "- ").
        
        Returns:
            Updated content with items appended to the correct section.
        """
        if not new_items:
            return content
        
        new_lines = "\n".join([f"- {item}" for item in new_items])
        
        # Find existing section (## Section_Name or ## Section_Name (date))
        section_pattern = rf"(## {re.escape(section_name)}(?:\s*\([^)]*\))?\n)"
        match = re.search(section_pattern, content, re.IGNORECASE)
        
        if match:
            # Find the end of this section (next ## or end of file)
            section_start = match.end()
            next_section = re.search(r"\n## ", content[section_start:])
            
            if next_section:
                # Insert before next section
                insert_pos = section_start + next_section.start()
                return content[:insert_pos] + new_lines + "\n" + content[insert_pos:]
            else:
                # Append at end
                return content.rstrip() + "\n" + new_lines
        else:
            # Create new section at end
            section_header = f"\n\n## {section_name}\n"
            return content.rstrip() + section_header + new_lines
    
    def _replace_in_section(self, content: str, old_fact: str, new_fact: str) -> str:
        """
        Replace an old fact with a new one in MEMORY.md.
        
        Args:
            content: The full MEMORY.md content.
            old_fact: The fact to replace (without "- " prefix).
            new_fact: The new fact to insert.
        
        Returns:
            Updated content with the fact replaced.
        """
        # Try to find and replace the line
        old_line_pattern = rf"^- {re.escape(old_fact)}$"
        new_line = f"- {new_fact}"
        
        updated = re.sub(old_line_pattern, new_line, content, flags=re.MULTILINE)
        if updated == content:
            # If exact match failed, try fuzzy match (first 50 chars)
            if len(old_fact) > 50:
                partial = old_fact[:50]
                old_line_pattern = rf"^- {re.escape(partial)}[^\n]*$"
                updated = re.sub(old_line_pattern, new_line, content, flags=re.MULTILINE)
        
        return updated
    
    async def lifecycle_update(
        self,
        new_facts: list[str],
        category: str = "general"
    ) -> dict[str, list[str]]:
        """
        Mem0-inspired lifecycle management: ADD/UPDATE/DELETE/NOOP.
        
        Compares new facts against existing memories and determines the
        appropriate action for each fact.
        
        Args:
            new_facts: List of new facts to process.
            category: Category for organizing facts.
        
        Returns:
            Dictionary with keys: 'add', 'update', 'delete', 'noop'
            Each contains a list of facts that underwent that operation.
        """
        if not new_facts:
            return {"add": [], "update": [], "delete": [], "noop": []}
        
        # Check if lifecycle is enabled
        if self._config and hasattr(self._config, 'enable_lifecycle'):
            if not self._config.enable_lifecycle:
                # Fallback to simple append
                return {"add": new_facts, "update": [], "delete": [], "noop": []}
        
        existing_content = self.read_long_term()
        
        logger.debug(f"Lifecycle: existing={len(existing_content) if existing_content else 0} bytes, llm={self._llm is not None}")
        
        if not existing_content or not self._llm:
            # No existing content or no LLM - just add all
            logger.info("No existing memory or LLM unavailable, adding all facts")
            
            # Use smart section append
            if new_facts:
                if existing_content:
                    updated = self._append_to_section(existing_content, category.title(), new_facts)
                else:
                    # Create initial structure
                    updated = f"# Long-term Memory\n\n## {category.title()}\n"
                    updated += "\n".join([f"- {fact}" for fact in new_facts])
                self.write_long_term(updated)
            
            return {"add": new_facts, "update": [], "delete": [], "noop": []}
        
        try:
            # Ask LLM to classify each fact
            facts_text = "\n".join([f"{i+1}. {fact}" for i, fact in enumerate(new_facts)])
            
            response = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory lifecycle manager. For each new fact, determine:\n"
                            "- ADD: Completely new information\n"
                            "- UPDATE: Updates or extends existing information\n"
                            "- DELETE: Contradicts existing information (mark which fact to delete)\n"
                            "- NOOP: Duplicate or irrelevant\n\n"
                            "Output format:\n"
                            "ADD: <fact number>\n"
                            "UPDATE: <fact number> (updates: <existing fact reference>)\n"
                            "DELETE: <existing fact> (because: <new fact number>)\n"
                            "NOOP: <fact number>\n"
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Existing memory:\n{existing_content[:2000]}\n\n"
                            f"New facts:\n{facts_text}"
                        )
                    }
                ],
                max_tokens=500,
                temperature=0.2,
            )
            
            if not response or not response.content:
                # Fallback: add all
                return {"add": new_facts, "update": [], "delete": [], "noop": []}
            
            # Parse LLM response
            logger.debug(f"Lifecycle LLM response: {response.content[:500]}")
            result = {"add": [], "update": [], "delete": [], "noop": []}
            
            for line in response.content.split('\n'):
                line = line.strip().upper()
                
                if line.startswith('ADD:'):
                    # Extract fact number
                    match = re.search(r'(\d+)', line)
                    if match:
                        idx = int(match.group(1)) - 1
                        if 0 <= idx < len(new_facts):
                            result["add"].append(new_facts[idx])
                
                elif line.startswith('NOOP:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        idx = int(match.group(1)) - 1
                        if 0 <= idx < len(new_facts):
                            result["noop"].append(new_facts[idx])
                
                elif line.startswith('UPDATE:'):
                    match = re.search(r'(\d+)', line)
                    if match:
                        idx = int(match.group(1)) - 1
                        if 0 <= idx < len(new_facts):
                            result["update"].append(new_facts[idx])
                
                elif line.startswith('DELETE:'):
                    # Extract the fact to delete from existing memory
                    fact_to_delete = line.replace('DELETE:', '').strip()
                    if fact_to_delete:
                        result["delete"].append(fact_to_delete)
            
            # If parsing didn't match anything, default to ADD all facts
            total_parsed = sum(len(v) for v in result.values())
            if total_parsed == 0:
                logger.warning(f"Lifecycle parsing found no matches, defaulting to ADD")
                result["add"] = new_facts
            
            # Apply the changes
            if result["add"] or result["update"] or result["delete"]:
                updated_content = existing_content
                
                # Delete contradictions (remove entire lines)
                for fact in result["delete"]:
                    # Remove the line containing this fact
                    pattern = rf"^- [^\n]*{re.escape(fact[:30])}[^\n]*\n?"
                    updated_content = re.sub(pattern, "", updated_content, flags=re.MULTILINE | re.IGNORECASE)
                
                # Add new facts to category section
                if result["add"]:
                    updated_content = self._append_to_section(updated_content, category.title(), result["add"])
                
                # Update facts: replace old with new in same section
                # For updates, we append to the category (since we don't know which fact to replace)
                if result["update"]:
                    updated_content = self._append_to_section(updated_content, category.title(), result["update"])
                
                # Clean up empty lines
                updated_content = re.sub(r"\n{3,}", "\n\n", updated_content)
                
                # Write back
                self.write_long_term(updated_content)
                
                logger.info(
                    f"Lifecycle update: {len(result['add'])} added, "
                    f"{len(result['update'])} updated, {len(result['delete'])} deleted, "
                    f"{len(result['noop'])} skipped"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Lifecycle update failed: {e}, falling back to simple add")
            # Fallback: add all facts
            return {"add": new_facts, "update": [], "delete": [], "noop": []}
    
    # ========== JIT (Just-In-Time) Retrieval ==========
    
    def retrieve_relevant(
        self,
        query: str,
        max_results: int = 10,
        method: Literal["keyword", "date", "category"] = "keyword"
    ) -> str:
        """
        JIT (Just-In-Time) retrieval of relevant memories based on query.
        
        Instead of loading all memories, dynamically retrieve only what's
        relevant to the current context.
        
        Args:
            query: Query string (e.g., current user message).
            max_results: Maximum number of memory snippets to return.
            method: Retrieval method - 'keyword', 'date', or 'category'.
        
        Returns:
            Formatted string of relevant memories.
        """
        # Check if JIT is enabled
        if self._config and hasattr(self._config, 'memory'):
            if not getattr(self._config.memory, 'jit_retrieval', True):
                # Fallback to full context
                return self.get_memory_context()
            max_results = getattr(self._config.memory, 'jit_max_results', 10)
            method = getattr(self._config.memory, 'jit_method', 'keyword')
        
        if not query or len(query.strip()) < 3:
            # Query too short, return recent context
            return self.get_memory_context()
        
        if method == "keyword":
            return self._retrieve_by_keyword(query, max_results)
        elif method == "date":
            return self._retrieve_by_date(max_results)
        elif method == "category":
            return self._retrieve_by_category(query, max_results)
        else:
            return self.get_memory_context()
    
    def _retrieve_by_keyword(self, query: str, max_results: int) -> str:
        """
        Retrieve memories using keyword matching with TF-IDF-inspired scoring.
        """
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]
        
        if not query_words:
            return self.get_memory_context()
        
        # Build vocabulary from all memories
        all_memories = []
        
        # Long-term memory
        long_term = self.read_long_term()
        if long_term:
            for line in long_term.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    all_memories.append(("MEMORY.md", line))
        
        # Recent daily notes (last 7 days)
        today = datetime.now().date()
        for i in range(7):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        all_memories.append((date_str, line))
        
        # Score each memory
        scored = []
        for source, memory in all_memories:
            memory_lower = memory.lower()
            
            # Count matching words
            matches = sum(1 for word in query_words if word in memory_lower)
            
            if matches > 0:
                # Simple TF-IDF-inspired score
                # Higher score for more matches and shorter memories
                score = matches / (len(memory.split()) + 1)
                scored.append((score, source, memory))
        
        # Sort by score descending
        scored.sort(reverse=True)
        
        # Format top results
        if not scored:
            return ""
        
        results = []
        for score, source, memory in scored[:max_results]:
            results.append(f"[{source}] {memory}")
        
        return "\n".join(results)
    
    def _retrieve_by_date(self, max_results: int) -> str:
        """
        Retrieve most recent memories.
        """
        # Just return the most recent days
        return self.get_recent_memories(days=min(max_results, 7))
    
    def _retrieve_by_category(self, query: str, max_results: int) -> str:
        """
        Retrieve memories by category (if categorized in memory).
        
        Falls back to keyword matching.
        """
        # For now, use keyword method as fallback
        # In the future, we can add explicit category markers
        return self._retrieve_by_keyword(query, max_results)
