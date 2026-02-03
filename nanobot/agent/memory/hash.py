"""Content-addressable hashing utilities."""

import hashlib
import json
from typing import Any


def compute_hash(data: dict[str, Any]) -> str:
    """
    Compute SHA256 hash of a dictionary.
    
    The dictionary is serialized to JSON with sorted keys for deterministic hashing.
    
    Args:
        data: Dictionary to hash.
    
    Returns:
        Hexadecimal SHA256 hash string (first 16 characters for brevity).
    """
    # Serialize with sorted keys for deterministic output
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    full_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    # Use first 16 chars for readability (still 64 bits of uniqueness)
    return full_hash[:16]


def compute_content_hash(content: str) -> str:
    """
    Compute SHA256 hash of a string content.
    
    Args:
        content: String to hash.
    
    Returns:
        Hexadecimal SHA256 hash string (first 16 characters).
    """
    full_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return full_hash[:16]
