"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseModel):
    """WhatsApp channel configuration."""
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class AgentDefaults(BaseModel):
    """Default agent configuration."""
    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent configuration."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""
    api_key: str = ""
    api_base: str | None = None


class OllamaConfig(BaseModel):
    """Ollama provider configuration with local/cloud mode support."""
    enabled: bool = False
    mode: str = "local"  # "local" or "cloud"
    # Local mode settings
    base_url: str = "http://localhost:11434"
    # Cloud mode settings  
    api_key: str = ""
    # Common settings
    default_model: str = "qwen3:4b"
    timeout: int = 120


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)


class GatewayConfig(BaseModel):
    """Gateway/server configuration."""
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""
    api_key: str = ""  # Brave Search API key
    max_results: int = 5


class OllamaWebSearchConfig(BaseModel):
    """Ollama web search tool configuration."""
    enabled: bool = False
    api_key: str = ""  # Ollama API key for web search
    base_url: str = "https://ollama.com"  # Ollama endpoint (cloud or local)
    max_results: int = 5


class WebToolsConfig(BaseModel):
    """Web tools configuration."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    ollama_search: OllamaWebSearchConfig = Field(default_factory=OllamaWebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell exec tool configuration."""
    timeout: int = 60
    restrict_to_workspace: bool = False  # If true, block commands accessing paths outside workspace


class UsageAlertConfig(BaseModel):
    """Token usage alert configuration."""
    enabled: bool = False
    daily_limit: int = 1000000  # Daily token limit
    session_limit: int = 100000  # Per-session token limit


class MemoryConfig(BaseModel):
    """Long-term memory system configuration."""
    
    # Auto-extraction
    auto_extract: bool = True
    extract_trigger: str = "end_of_conversation"  # "end_of_conversation" or "turn_count"
    max_facts_per_extraction: int = 3
    
    # Smart deduplication (uses LLM calls, disabled by default)
    smart_dedupe: bool = False
    dedupe_method: str = "llm"  # "llm" or "simple"
    
    # Consolidation
    weekly_consolidate: bool = True
    consolidate_day: str = "sunday"
    keep_daily_notes_days: int = 30
    
    # Search
    search_method: str = "text"  # "text", "fts5", "semantic"
    use_scratchpad: bool = True  # Anthropic scratchpad method for recall
    
    # Mem0-inspired lifecycle management (ADD/UPDATE/DELETE/NOOP)
    enable_lifecycle: bool = True
    update_threshold: float = 0.7  # Similarity threshold for updates
    delete_contradictions: bool = True
    
    # JIT (Just-In-Time) retrieval
    jit_retrieval: bool = True
    jit_method: str = "keyword"  # "keyword", "date", "category"
    jit_max_results: int = 10
    
    # Security
    max_content_size: int = 8192  # Max size in bytes for content validation


class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)


class Config(BaseSettings):
    """Root configuration for nanobot."""
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    usage_alert: UsageAlertConfig = Field(default_factory=UsageAlertConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    
    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()
    
    def get_api_key(self) -> str | None:
        """Get API key in priority order: OpenRouter > Anthropic > OpenAI > Gemini > Zhipu > Groq > vLLM."""
        return (
            self.providers.openrouter.api_key or
            self.providers.anthropic.api_key or
            self.providers.openai.api_key or
            self.providers.gemini.api_key or
            self.providers.zhipu.api_key or
            self.providers.groq.api_key or
            self.providers.vllm.api_key or
            None
        )
    
    def get_api_base(self) -> str | None:
        """Get API base URL if using OpenRouter, Zhipu or vLLM."""
        if self.providers.openrouter.api_key:
            return self.providers.openrouter.api_base or "https://openrouter.ai/api/v1"
        if self.providers.zhipu.api_key:
            return self.providers.zhipu.api_base
        if self.providers.vllm.api_base:
            return self.providers.vllm.api_base
        return None
    
    class Config:
        env_prefix = "NANOBOT_"
        env_nested_delimiter = "__"
