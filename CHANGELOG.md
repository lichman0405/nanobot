# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Git-like Memory Architecture**: A new memory system inspired by Git's data model
  - Immutable event ledger with content-addressable storage (SHA256)
  - Branch-based persona isolation for different contexts
  - LLM-driven autonomous memory management
  - Memory visualization with Mermaid diagrams
  - CLI commands: `nanobot memory log/branches/view/graph/checkout/stats/export`
- **Memory Tools for Agent**: 7 new tools for autonomous memory management
  - `memory_search`: Search memories by query, subject, scope
  - `memory_add`: Store subject-predicate-object triples
  - `memory_update`: Modify existing memories with history tracking
  - `memory_forget`: Soft-delete with reason preservation
  - `memory_branch`: Create/switch/list persona branches
  - `memory_history`: View commit history
  - `memory_consolidate`: Generate maintenance reports
- **Memory Export**: `nanobot memory export` command (JSON/Markdown formats)
- New modules in `nanobot/agent/memory/`:
  - `event.py`: MemoryEvent dataclass
  - `commit.py`: MemoryCommit dataclass
  - `branch.py`: MemoryBranch dataclass
  - `ledger.py`: EventLedger (immutable append-only storage)
  - `store.py`: MemoryStore (main interface)
  - `branches.py`: BranchManager (merge, cherry-pick)
  - `view.py`: MemoryView (materialized current state)
  - `controller.py`: MemoryController (LLM-driven decisions)
  - `visualize.py`: Visualization utilities

### Changed
- `nanobot/agent/context.py`: Updated to use new memory view for context building
- `nanobot/agent/loop.py`: Added MemoryController integration with `_process_for_memory()`
- Renamed `nanobot/agent/memory.py` → `memory_legacy.py`

### Technical Details
- Memory stored in `workspace/memory/events/` and `workspace/memory/commits/` as JSON files
- Each event/commit named by its SHA256 hash (16 chars)
- Supports: add, modify, forget, observe event types
- Scopes: permanent, session, temporary
- Full traceability with parent_id linking

## [0.1.0] - 2025-02-01

### Added
- Initial release of nanobot
- Core agent loop with tool execution
- LiteLLM provider for multi-model support
- Telegram and WhatsApp channels
- File, shell, web search, and spawn tools
- Session management
- Skills system
