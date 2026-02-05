"""Memory system for persistent agent memory."""

from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """
    Memory system for the agent.
    
    Supports daily notes (memory/YYYY-MM-DD.md) and long-term memory (MEMORY.md).
    Enhanced with smart extraction, deduplication, and consolidation.
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
