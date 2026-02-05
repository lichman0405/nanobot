# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Token Usage Tracking System
- **Usage Tracker Module** (`nanobot/usage/tracker.py`)
  - Track token usage for all LLM calls (prompt tokens, completion tokens, total tokens)
  - Aggregate statistics by session, by date, and overall
  - Persistent storage in JSON format (`~/.nanobot/usage/stats.json`)
  - Support for querying and exporting usage data

- **Usage Alerts**
  - Configurable daily and per-session token limits
  - Warning messages when limits are exceeded (non-blocking)
  - Alert logging for monitoring

- **Usage CLI Commands**
  - `nanobot usage` - Display overall token usage statistics
  - `nanobot usage --session <id>` - Show usage for a specific session
  - `nanobot usage --today` - Show today's usage
  - `nanobot usage --week` - Show this week's usage
  - `nanobot usage sessions` - List all sessions with usage data
  - `nanobot usage --export <file>` - Export statistics to JSON
  - `nanobot usage --clear` - Clear all usage data (with confirmation)

- **Configuration Management Commands**
  - `nanobot config show` - Display current configuration summary
  - `nanobot config setup-provider` - Interactive LLM provider setup wizard (including Ollama local/cloud)
  - `nanobot config setup-web-search` - Configure web search tools (Brave Search, Ollama Web Search)
  - `nanobot config setup-alerts` - Configure usage alerts interactively
  - `nanobot config edit` - Open config file in default editor

#### Ollama Provider Support
- **Ollama LLM Provider** (`nanobot/providers/ollama_provider.py`)
  - Full support for **Ollama local models** (via localhost:11434)
  - Full support for **Ollama Cloud models** (via https://ollama.com)
  - Auto-detection of cloud vs local mode based on `baseUrl` or `apiKey`
  - Cloud authentication via `Authorization: Bearer <api_key>` header
  - Compatible with LLMProvider interface
  - Token counting from Ollama metrics (`prompt_eval_count`, `eval_count`)
  - Tool calling support
  - Configurable base URL and timeout

- **Ollama Web Search Tool** (`nanobot/agent/tools/web.py`)
  - New `ollama_web_search` tool using Ollama Cloud's web search API
  - Works alongside existing Brave Search (`web_search`)
  - Allows users to choose between multiple search providers
  - Requires Ollama Cloud API key (get at https://ollama.com/settings/keys)
  - Consistent output format with other search tools

- **Tool Usage Display**
  - Shows which tools were used in each session
  - Displays usage count for each tool (e.g., `web_fetch (12x)`)
  - Logged at INFO level after task completion

#### Long-term Memory System Enhancements
- **Mem0-Inspired Lifecycle Management** (`nanobot/agent/memory.py`)
  - ADD/UPDATE/DELETE/NOOP intelligent fact management
  - Prevents duplicate memories and contradictions
  - LLM-powered comparison with keyword fallback
  - Automatic merging of related facts
  - Contradiction detection and removal
  
- **JIT (Just-In-Time) Retrieval**
  - Dynamic memory loading based on current query
  - Three retrieval methods: keyword, date, category
  - TF-IDF-inspired scoring for relevance ranking
  - Faster context building (loads only relevant memories)
  - Reduced token usage compared to loading all memories
  
- **Security Enhancements**
  - Path validation to prevent traversal attacks
  - Content sanitization (HTML escaping, size limits)
  - Resource cleanup for proper file handle management
  - Configurable max content size (default: 8KB)
  
- **Enhanced Memory Tools**
  - `remember` tool now uses lifecycle management
  - `recall` tool supports JIT retrieval
  - Auto-extraction integrated with lifecycle
  
- **Additional Configuration Options**
  - `enable_lifecycle` - Toggle Mem0-style management
  - `update_threshold` - Similarity threshold for updates
  - `delete_contradictions` - Auto-remove conflicts
  - `jit_retrieval` - Enable JIT loading
  - `jit_method` - Choose retrieval strategy
  - `jit_max_results` - Limit loaded memories
  - `max_content_size` - Security size limit

### Changed
- **Agent Loop**: Integrated automatic token usage tracking for all LLM calls
- **Agent Loop**: Added tool usage tracking and summary display
- **Agent Loop**: Enhanced auto-extraction with Mem0 lifecycle management
- **Memory System**: Upgraded from simple storage to intelligent lifecycle management
  - RememberTool now uses ADD/UPDATE/DELETE/NOOP logic
  - Auto-extraction prevents duplicate and contradicting facts
  - JIT retrieval reduces context size and improves relevance
- **Context Builder**: Added JIT memory retrieval support
  - Optionally loads only relevant memories based on current query
  - Configurable retrieval methods (keyword, date, category)
- **Session Manager**: Extended to store usage metadata
- **Configuration Schema**: Added `usage_alert` and `ollama` configuration sections
- **Configuration Schema**: Extended `memory` configuration with lifecycle and JIT options
- **Web Tools**: Now supports dual search providers (Brave + Ollama)
- **Status Command**: Enhanced to show Ollama and usage alert status
- **Config Commands**: Streamlined configuration workflow
  - Merged `setup-ollama` into `setup-provider` for clearer separation of concerns
  - Provider layer (LLM): setup-provider handles all LLM providers including Ollama local/cloud
  - Tool layer (Web Search): setup-web-search handles web search tools
  - Improved UX with intelligent API key reuse
  - Clear mode selection for Ollama (local vs cloud)

### Fixed
- **Ollama Provider**: Fixed tool_calls argument format incompatibility
  - Ollama SDK expects arguments as dict objects, not JSON strings
  - Added `_preprocess_messages()` to convert OpenAI format to Ollama format
  - Resolves validation errors when using tool calling with Ollama Cloud models
- **Ollama Configuration**: Clarified local vs cloud mode configuration
  - Added explicit `mode` field to distinguish between local and cloud usage
  - Separate settings for `base_url` (local) and `api_key` (cloud)
  - Better validation and error messages for missing cloud API key
- **Performance**: Optimized usage tracker to batch writes (every 10 records)
  - Reduces I/O overhead in high-throughput scenarios
  - Previous behavior: write on every single track() call
- **Code Quality**: Fixed import statements organization
  - Moved `asyncio`, `json` imports to file top level
  - Added missing `logger` import in web.py
- **Configuration Display**: Fixed Ollama status check in `config show` command
  - Now correctly checks `enabled` flag instead of `api_base`
- **Model Selection**: Fixed default model logic for Ollama provider
  - Respects user's configured model in `agents.defaults.model`
  - Only falls back to `ollama.default_model` if not set

### Removed
- **`nanobot config setup-ollama`** - Merged into `setup-provider` for better organization
  - Ollama configuration now handled in the unified provider setup wizard
  - Reduces command redundancy and improves user experience

### Configuration
New configuration options in `~/.nanobot/config.json`:
```json
{
  "usage_alert": {
    "enabled": false,
    "daily_limit": 1000000,
    "session_limit": 100000
  },
  "providers": {
    "ollama": {
      "enabled": false,
      "mode": "local",           // "local" or "cloud"
      "base_url": "http://localhost:11434",  // for local mode
      "api_key": "",             // required for cloud mode
      "default_model": "qwen3:4b",
      "timeout": 120
    }
  },
  "tools": {
    "web": {
      "ollama_search": {
        "enabled": false,
        "api_key": "",
        "max_results": 5
      }
    }
  },
  "memory": {
    // === Extraction ===
    "auto_extract": true,
    "max_facts_per_extraction": 3,
    
    // === Deduplication ===
    "smart_dedupe": false,
    
    // === Consolidation ===
    "weekly_consolidate": true,
    "consolidate_day": "sunday",
    
    // === Lifecycle (NEW!) ===
    "enable_lifecycle": true,       // Mem0-inspired ADD/UPDATE/DELETE/NOOP
    "update_threshold": 0.7,
    "delete_contradictions": true,
    
    // === JIT Retrieval (NEW!) ===
    "jit_retrieval": true,          // Just-In-Time memory loading
    "jit_method": "keyword",        // "keyword", "date", or "category"
    "jit_max_results": 10,
    
    // === Security (NEW!) ===
    "max_content_size": 8192        // Max bytes per memory entry
  }
}
```

## [0.1.3.post4] - 2026-02-01

### Added
- Initial release of nanobot
- Core agent loop with tool execution
- Support for multiple LLM providers (OpenRouter, Anthropic, OpenAI, etc.)
- Chat channels: Telegram, WhatsApp
- File system tools, shell execution, web search/fetch
- Session management and memory
- Cron job scheduling
- Heartbeat service

[Unreleased]: https://github.com/HKUDS/nanobot/compare/v0.1.3.post4...HEAD
[0.1.3.post4]: https://github.com/HKUDS/nanobot/releases/tag/v0.1.3.post4
