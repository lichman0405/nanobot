"""
Test fixtures for long-term memory testing.
Includes sample conversations, memory entries, and scratchpad data.
"""

# Sample conversation turns for extraction testing
SAMPLE_CONVERSATIONS = [
    {
        "session_id": "test:user123",
        "turns": [
            {"role": "user", "content": "My name is Alice and I work as a software engineer at TechCorp."},
            {"role": "assistant", "content": "Nice to meet you, Alice! It's great to talk with a software engineer."},
            {"role": "user", "content": "I'm currently working on a Python project using FastAPI."},
            {"role": "assistant", "content": "FastAPI is an excellent choice for building APIs. What kind of project is it?"},
        ],
        "expected_facts": [
            "User's name is Alice",
            "User works as a software engineer at TechCorp",
            "User is working on a Python project using FastAPI",
        ]
    },
    {
        "session_id": "test:user456",
        "turns": [
            {"role": "user", "content": "I prefer using tabs over spaces for indentation."},
            {"role": "assistant", "content": "I understand you prefer tabs. Many developers have strong preferences about indentation."},
            {"role": "user", "content": "Also, I always write tests before implementing features."},
            {"role": "assistant", "content": "That's Test-Driven Development (TDD). It's a solid practice!"},
        ],
        "expected_facts": [
            "User prefers tabs over spaces for indentation",
            "User practices Test-Driven Development (TDD)",
        ]
    },
    {
        "session_id": "test:user789",
        "turns": [
            {"role": "user", "content": "I live in San Francisco and I'm allergic to peanuts."},
            {"role": "assistant", "content": "Thanks for letting me know about your peanut allergy. I'll keep that in mind."},
            {"role": "user", "content": "I have a meeting every Monday at 9 AM."},
            {"role": "assistant", "content": "Got it, you have a recurring Monday morning meeting at 9 AM."},
        ],
        "expected_facts": [
            "User lives in San Francisco",
            "User is allergic to peanuts",
            "User has a meeting every Monday at 9 AM",
        ]
    }
]

# Sample memory entries for deduplication and search testing
SAMPLE_MEMORY_ENTRIES = [
    {
        "fact": "User's name is Alice",
        "timestamp": "2024-01-15T10:00:00Z",
        "source": "conversation",
        "confidence": 1.0,
    },
    {
        "fact": "User is called Alice",  # Duplicate of above
        "timestamp": "2024-01-15T11:00:00Z",
        "source": "conversation",
        "confidence": 0.9,
    },
    {
        "fact": "User works at TechCorp as a software engineer",
        "timestamp": "2024-01-15T10:05:00Z",
        "source": "conversation",
        "confidence": 1.0,
    },
    {
        "fact": "User is a software engineer at TechCorp",  # Duplicate
        "timestamp": "2024-01-15T12:00:00Z",
        "source": "conversation",
        "confidence": 0.95,
    },
    {
        "fact": "User prefers Python for backend development",
        "timestamp": "2024-01-16T14:00:00Z",
        "source": "conversation",
        "confidence": 0.8,
    },
    {
        "fact": "User likes using FastAPI framework",
        "timestamp": "2024-01-16T14:30:00Z",
        "source": "conversation",
        "confidence": 0.85,
    },
    {
        "fact": "User is allergic to peanuts",
        "timestamp": "2024-01-17T09:00:00Z",
        "source": "conversation",
        "confidence": 1.0,
    },
    {
        "fact": "User has a Monday 9 AM meeting",
        "timestamp": "2024-01-17T09:15:00Z",
        "source": "conversation",
        "confidence": 1.0,
    },
]

# Sample scratchpad entries (Anthropic method)
SAMPLE_SCRATCHPAD = {
    "test:user123": [
        "Alice - software engineer at TechCorp",
        "Working on Python/FastAPI project",
        "Last discussed API design patterns",
    ],
    "test:user456": [
        "Prefers tabs for indentation",
        "Practices TDD (Test-Driven Development)",
        "Interested in code quality",
    ],
    "test:user789": [
        "Lives in San Francisco",
        "⚠️ Allergic to peanuts",
        "Monday 9 AM recurring meeting",
    ]
}

# Expected deduplication results (using simple text similarity)
EXPECTED_DEDUPED_SIMPLE = [
    "User's name is Alice",  # Keep first occurrence
    "User works at TechCorp as a software engineer",  # Keep first
    "User prefers Python for backend development",
    "User likes using FastAPI framework",
    "User is allergic to peanuts",
    "User has a Monday 9 AM meeting",
]

# Sample queries for search testing
SEARCH_QUERIES = [
    {
        "query": "What is the user's name?",
        "expected_matches": ["User's name is Alice"],
        "search_method": "text",
    },
    {
        "query": "Where does the user work?",
        "expected_matches": ["User works at TechCorp as a software engineer"],
        "search_method": "text",
    },
    {
        "query": "allergies",
        "expected_matches": ["User is allergic to peanuts"],
        "search_method": "text",
    },
    {
        "query": "schedule Monday",
        "expected_matches": ["User has a Monday 9 AM meeting"],
        "search_method": "text",
    },
    {
        "query": "programming preferences",
        "expected_matches": [
            "User prefers Python for backend development",
            "User likes using FastAPI framework",
        ],
        "search_method": "text",
    },
]

# Sample consolidation input (weekly notes to consolidate)
WEEKLY_CONSOLIDATION_INPUT = [
    "2024-01-15: User mentioned working on Python project",
    "2024-01-16: User discussed FastAPI benefits",
    "2024-01-17: User shared meeting schedule",
    "2024-01-18: User asked about async programming",
    "2024-01-19: User completed FastAPI tutorial",
]

EXPECTED_CONSOLIDATED_OUTPUT = [
    "User is working on a Python project using FastAPI",
    "User has interest in async programming",
    "User has a Monday 9 AM recurring meeting",
]

# Error cases for testing robustness
ERROR_TEST_CASES = [
    {
        "description": "Empty conversation",
        "conversation": [],
        "expected_facts": [],
    },
    {
        "description": "No factual content",
        "conversation": [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "expected_facts": [],
    },
    {
        "description": "Very long message",
        "conversation": [
            {"role": "user", "content": "A" * 10000},
            {"role": "assistant", "content": "I see."},
        ],
        "expected_behavior": "should_truncate_or_handle_gracefully",
    },
]
