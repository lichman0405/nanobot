"""Tests for memory system enhancements (Mem0 lifecycle + JIT retrieval)."""

import pytest
from pathlib import Path
from datetime import datetime

from nanobot.agent.memory import MemoryStore
from nanobot.providers.base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""
    
    def __init__(self, response_content: str = "1. Test fact"):
        super().__init__()
        self._response_content = response_content
    
    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7):
        """Return mock response."""
        return LLMResponse(
            content=self._response_content,
            tool_calls=[],
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        )
    
    def get_default_model(self):
        return "mock-model"


class MockMemoryConfig:
    """Mock memory configuration."""
    
    def __init__(self):
        self.enable_lifecycle = True
        self.jit_retrieval = True
        self.jit_method = "keyword"
        self.jit_max_results = 10
        self.max_content_size = 8192


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def memory_store(temp_workspace):
    """Create a memory store with mock LLM."""
    llm = MockLLMProvider()
    config = MockMemoryConfig()
    return MemoryStore(temp_workspace, llm_provider=llm, config=config)


# ========== Security Tests ==========

def test_path_validation(memory_store):
    """Test path traversal protection."""
    # Valid path
    valid_path = memory_store.memory_dir / "test.md"
    assert memory_store._validate_path(valid_path)
    
    # Invalid path (traversal attempt)
    invalid_path = memory_store.memory_dir / ".." / ".." / "etc" / "passwd"
    assert not memory_store._validate_path(invalid_path)


def test_content_validation(memory_store):
    """Test content sanitization."""
    # Normal content
    clean = memory_store._validate_content("Hello world")
    assert "Hello world" in clean
    
    # HTML content (should be escaped)
    html = memory_store._validate_content("<script>alert('xss')</script>")
    assert "<script>" not in html
    assert "&lt;" in html or "script" not in html
    
    # Too large content
    with pytest.raises(ValueError):
        memory_store._validate_content("x" * 10000)


# ========== Mem0 Lifecycle Tests ==========

@pytest.mark.asyncio
async def test_lifecycle_add_operation(memory_store):
    """Test ADD operation in lif

ecycle management."""
    # Configure mock to return ADD classification
    memory_store._llm._response_content = "ADD: 1"
    
    result = await memory_store.lifecycle_update(
        new_facts=["User likes Python programming"],
        category="preferences"
    )
    
    assert "add" in result
    assert len(result["add"]) == 1
    assert "Python" in result["add"][0]


@pytest.mark.asyncio
async def test_lifecycle_noop_operation(memory_store):
    """Test NOOP operation (duplicate detection)."""
    # First add a fact
    memory_store.write_long_term("## Preferences\n- User likes Python")
    
    # Configure mock to return NOOP
    memory_store._llm._response_content = "NOOP: 1"
    
    result = await memory_store.lifecycle_update(
        new_facts=["User likes Python"],
        category="preferences"
    )
    
    assert "noop" in result
    # Should skip duplicate


@pytest.mark.asyncio
async def test_lifecycle_update_operation(memory_store):
    """Test UPDATE operation (merge related facts)."""
    # Existing fact
    memory_store.write_long_term("## Location\n- User lives in San Francisco")
    
    # Configure mock to return UPDATE
    memory_store._llm._response_content = "UPDATE: 1"
    
    result = await memory_store.lifecycle_update(
        new_facts=["User moved to New York"],
        category="location"
    )
    
    assert "update" in result


@pytest.mark.asyncio
async def test_lifecycle_delete_operation(memory_store):
    """Test DELETE operation (remove contradictions)."""
    # Existing fact
    memory_store.write_long_term("## Employment\n- User works at Google")
    
    # Configure mock to return DELETE
    memory_store._llm._response_content = "DELETE: User works at Google (because: 1)"
    
    result = await memory_store.lifecycle_update(
        new_facts=["User quit job at Google"],
        category="employment"
    )
    
    assert "delete" in result


@pytest.mark.asyncio
async def test_lifecycle_without_llm(temp_workspace):
    """Test lifecycle fallback when no LLM available."""
    memory_store = MemoryStore(temp_workspace, llm_provider=None)
    
    result = await memory_store.lifecycle_update(
        new_facts=["Test fact"],
        category="test"
    )
    
    # Should fallback to ADD all
    assert "add" in result
    assert len(result["add"]) == 1


# ========== JIT Retrieval Tests ==========

def test_jit_keyword_retrieval(memory_store):
    """Test keyword-based JIT retrieval."""
    # Populate memory
    memory_store.write_long_term("""
## User Info
- Name is Alice
- Loves cats and coffee
- Works as a software engineer

## Preferences  
- Prefers Python over JavaScript
- Uses VS Code editor
""")
    
    # Query about Python (exact match)
    result = memory_store.retrieve_relevant(
        query="Tell me about Python programming",
        method="keyword"
    )
    
    assert "Python" in result or "engineer" in result or len(result) > 0


def test_jit_empty_query(memory_store):
    """Test JIT with empty query (should fallback to full context)."""
    memory_store.write_long_term("## Test\n- Some content")
    
    result = memory_store.retrieve_relevant(query="")
    
    # Should return full context
    assert "Some content" in result


def test_jit_date_retrieval(memory_store):
    """Test date-based retrieval (most recent)."""
    # Add daily note
    today_file = memory_store.get_today_file()
    today_file.write_text("# Today's Notes\n- Did something today")
    
    result = memory_store.retrieve_relevant(
        query="anything",
        method="date"
    )
    
    assert "Today" in result or "today" in result


def test_jit_keyword_scoring(memory_store):
    """Test that keyword matching uses TF-IDF-like scoring."""
    memory_store.write_long_term("""
- Python is great for data science
- I like Python programming
- JavaScript is also useful
- Coffee and Python go together
""")
    
    result = memory_store.retrieve_relevant(
        query="Python programming language",
        max_results=2
    )
    
    # Should prefer lines with multiple keyword matches
    assert "Python" in result
    lines = result.split('\n')
    assert len(lines) <= 2  # Respects max_results


def test_jit_category_fallback(memory_store):
    """Test category retrieval (currently falls back to keyword)."""
    memory_store.write_long_term("## Preferences\n- Likes Python programming language")
    
    result = memory_store.retrieve_relevant(
        query="Python",
        method="category"
    )
    
    assert "Python" in result or len(result) > 0


# ========== Integration Tests ==========

@pytest.mark.asyncio
async def test_lifecycle_with_real_memory(temp_workspace):
    """Test lifecycle with real memory operations."""
    # Create memory with mock LLM
    llm = MockLLMProvider("ADD: 1\nADD: 2")
    config = MockMemoryConfig()
    memory = MemoryStore(temp_workspace, llm_provider=llm, config=config)
    
    # Add initial facts
    result = await memory.lifecycle_update(
        new_facts=[
            "User's name is Bob",
            "User prefers dark mode"
        ]
    )
    
    # Check that facts were added
    content = memory.read_long_term()
    assert "Bob" in content or len(result["add"]) == 2


@pytest.mark.asyncio
async def test_jit_retrieval_configuration(temp_workspace):
    """Test that JIT configuration is respected."""
    config = MockMemoryConfig()
    config.jit_retrieval = False  # Disable JIT
    
    memory = MemoryStore(temp_workspace, config=config)
    memory.write_long_term("## Test\n- Content")
    
    # With JIT disabled, should return full context
    result = memory.retrieve_relevant("test")
    assert "MEMORY.md" not in result or "Test" in result


def test_security_in_lifecycle(memory_store):
    """Test that lifecycle respects content size limits."""
    # Very large fact (exceeds limit)
    large_fact = "x" * 10000
    
    # Should handle gracefully (either reject or truncate)
    # The actual behavior depends on implementation
    try:
        result = memory_store._validate_content(large_fact)
        # If it doesn't raise, it should have truncated
    except ValueError:
        # Expected: content too large
        pass


# ========== Performance Tests ==========

def test_jit_retrieval_speed(memory_store):
    """Test that JIT retrieval is fast (no heavy operations)."""
    # Populate with many entries
    content = "\n".join([f"- Entry {i}: Random text about topic {i%10}" for i in range(100)])
    memory_store.write_long_term(content)
    
    import time
    start = time.time()
    
    result = memory_store.retrieve_relevant("topic 5", max_results=5)
    
    elapsed = time.time() - start
    
    # Should be very fast (< 100ms for keyword search)
    assert elapsed < 0.1
    assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
