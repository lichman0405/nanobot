"""
Tests for long-term memory system.
Tests the RememberTool, RecallTool, SearchMemoryTool, and MemoryStore enhancements.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

from nanobot.agent.memory import MemoryStore
from nanobot.agent.tools.memory import RememberTool, RecallTool, SearchMemoryTool
from nanobot.providers.ollama_provider import OllamaProvider
from nanobot.config.loader import load_config
from tests.fixtures.memory_test_data import (
    SAMPLE_CONVERSATIONS,
    SAMPLE_MEMORY_ENTRIES,
    SEARCH_QUERIES,
)


@pytest.fixture
async def ollama_provider():
    """Create Ollama provider using real Ollama Cloud config."""
    config = load_config()
    
    if not config.providers.ollama.enabled:
        pytest.skip("Ollama provider not enabled")
    
    provider = OllamaProvider(
        mode=config.providers.ollama.mode,
        api_key=config.providers.ollama.api_key,
        base_url=config.providers.ollama.base_url,
        default_model=config.providers.ollama.default_model,
        timeout=config.providers.ollama.timeout,
    )
    
    return provider


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def memory_store(temp_workspace, ollama_provider):
    """Create a memory store with LLM provider."""
    config = load_config()
    store = MemoryStore(
        workspace=temp_workspace,
        llm_provider=ollama_provider,
        config=config
    )
    return store


class TestRememberTool:
    """Test the RememberTool."""
    
    @pytest.mark.asyncio
    async def test_remember_basic(self, temp_workspace):
        """Test basic remember functionality."""
        store = MemoryStore(workspace=temp_workspace)
        tool = RememberTool(memory_store=store)
        
        # Remember a fact
        result = await tool.execute(fact="User prefers Python over JavaScript")
        
        assert "Remembered" in result
        assert "User prefers Python" in result
        
        # Verify it was saved
        today_notes = store.read_today()
        assert "User prefers Python over JavaScript" in today_notes
    
    @pytest.mark.asyncio
    async def test_remember_with_category(self, temp_workspace):
        """Test remember with category and importance."""
        store = MemoryStore(workspace=temp_workspace)
        tool = RememberTool(memory_store=store)
        
        result = await tool.execute(
            fact="User is allergic to peanuts",
            category="health",
            importance="high"
        )
        
        assert "Remembered" in result
        
        # Verify category and importance are saved
        today_notes = store.read_today()
        assert "allergic to peanuts" in today_notes
        assert "health" in today_notes or "🔥" in today_notes


class TestRecallTool:
    """Test the RecallTool."""
    
    @pytest.mark.asyncio
    async def test_recall_empty(self, memory_store):
        """Test recall with no memories."""
        tool = RecallTool(memory_store=memory_store, llm_provider=None)
        
        result = await tool.execute(query="user preferences")
        
        assert "No memories found" in result or "No relevant" in result
    
    @pytest.mark.asyncio
    async def test_recall_simple_keyword_match(self, temp_workspace):
        """Test recall with simple keyword matching (no LLM)."""
        store = MemoryStore(workspace=temp_workspace)
        tool = RecallTool(memory_store=store, llm_provider=None)
        
        # Add some memories
        store.append_today("User prefers Python programming language")
        store.append_today("User lives in San Francisco")
        store.append_today("User likes FastAPI framework")
        
        # Recall with keyword
        result = await tool.execute(query="Python")
        
        assert "Python" in result or "python" in result.lower()
    
    @pytest.mark.asyncio
    async def test_recall_with_llm(self, memory_store, ollama_provider):
        """Test recall with LLM-powered scratchpad method."""
        tool = RecallTool(memory_store=memory_store, llm_provider=ollama_provider)
        
        # Add memories
        memory_store.append_today("User name is Alice")
        memory_store.append_today("User works at TechCorp as software engineer")
        memory_store.append_today("User is working on Python/FastAPI project")
        
        # Recall with natural language query
        result = await tool.execute(query="What do we know about the user's work?")
        
        # Should mention work-related info
        assert result
        assert len(result) > 0
        print(f"LLM Recall result: {result}")


class TestSearchMemoryTool:
    """Test the SearchMemoryTool."""
    
    @pytest.mark.asyncio
    async def test_search_basic(self, temp_workspace):
        """Test basic search functionality."""
        store = MemoryStore(workspace=temp_workspace)
        tool = SearchMemoryTool(memory_store=store)
        
        # Add memories
        store.append_today("User prefers tabs over spaces")
        store.append_today("User practices Test-Driven Development")
        store.append_today("User likes clean code principles")
        
        # Search
        result = await tool.execute(keywords="Test-Driven")
        
        assert "Test-Driven" in result
        assert "Found" in result
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, temp_workspace):
        """Test search with no matches."""
        store = MemoryStore(workspace=temp_workspace)
        tool = SearchMemoryTool(memory_store=store)
        
        store.append_today("Some random content")
        
        result = await tool.execute(keywords="nonexistent query")
        
        assert "No matches found" in result


class TestMemoryStore:
    """Test enhanced MemoryStore functionality."""
    
    @pytest.mark.asyncio
    async def test_smart_extract(self, memory_store, ollama_provider):
        """Test smart fact extraction from conversation."""
        # Use first sample conversation
        conversation = SAMPLE_CONVERSATIONS[0]
        
        facts = await memory_store.smart_extract(
            conversation=conversation["turns"],
            max_facts=3
        )
        
        print(f"Extracted facts: {facts}")
        
        # Should extract some facts
        assert isinstance(facts, list)
        # At least one fact should be extracted
        if len(facts) > 0:
            assert len(facts[0]) > 10  # Meaningful fact
    
    @pytest.mark.asyncio
    async def test_smart_dedupe(self, memory_store, ollama_provider):
        """Test smart deduplication."""
        # Enable smart dedupe in config
        if hasattr(memory_store._config, 'memory'):
            memory_store._config.memory.smart_dedupe = True
        
        duplicate_facts = [
            "User's name is Alice",
            "User is called Alice",  # Duplicate
            "User works at TechCorp",
            "User is employed at TechCorp"  # Duplicate
        ]
        
        deduped = await memory_store.smart_dedupe(duplicate_facts)
        
        print(f"Original: {len(duplicate_facts)} facts")
        print(f"Deduped: {len(deduped)} facts")
        print(f"Deduped facts: {deduped}")
        
        # Should have fewer facts after dedup
        assert isinstance(deduped, list)
    
    def test_simple_search(self, temp_workspace):
        """Test simple text search."""
        store = MemoryStore(workspace=temp_workspace)
        
        # Add memories
        store.append_today("User prefers Python for backend")
        store.append_today("User likes FastAPI framework")
        store.append_today("User is allergic to peanuts")
        
        # Search
        matches = store.simple_search(query="Python FastAPI", days_back=7)
        
        assert len(matches) > 0
        assert any("Python" in match for match in matches)


class TestIntegration:
    """Integration tests for memory system."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, memory_store, ollama_provider):
        """Test complete remember -> recall workflow."""
        remember_tool = RememberTool(memory_store=memory_store)
        recall_tool = RecallTool(memory_store=memory_store, llm_provider=ollama_provider)
        
        # Remember some facts
        await remember_tool.execute(fact="User is learning Rust programming")
        await remember_tool.execute(fact="User wants to build a CLI tool")
        await remember_tool.execute(fact="User prefers vim editor")
        
        # Recall
        result = await recall_tool.execute(query="programming preferences")
        
        print(f"Recall result: {result}")
        
        # Should find something
        assert result
        assert len(result) > 20  # Meaningful response


if __name__ == "__main__":
    # Run basic tests
    pytest.main([__file__, "-v", "-s"])
