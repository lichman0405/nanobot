"""
Memory controller - LLM-driven autonomous memory management.

This module implements the intelligent layer of the memory system, using LLM
to make decisions about:
- What to remember
- When to remember
- Which persona/branch to use
- How to resolve conflicts
"""

import json
from typing import Any
from dataclasses import dataclass

from nanobot.agent.memory.event import MemoryEvent, EventType, MemorySource
from nanobot.agent.memory.store import MemoryStore
from nanobot.providers.base import LLMProvider, LLMResponse


# Prompt templates for memory operations
SHOULD_REMEMBER_PROMPT = """Analyze the following conversation and determine if there is important information that should be stored as long-term memory.

Things worth remembering:
- User preferences (e.g., "I prefer dark mode", "I like Python")
- User facts (e.g., name, occupation, location, timezone)
- Project details (e.g., "this project uses Python 3.11")
- Task outcomes (e.g., "completed the migration to new API")
- Important decisions or agreements

Things NOT worth remembering:
- Greetings and casual chat
- One-time requests (e.g., "what's 2+2")
- Information already in memory
- Temporary context that won't be useful later

Current conversation:
{conversation}

Current memory context (what we already know):
{memory_context}

Respond in JSON format:
{{
  "should_remember": true/false,
  "reason": "brief explanation",
  "memories": [
    {{
      "subject": "who/what this is about",
      "predicate": "the relationship/action",
      "object": "the value/detail",
      "scope": "optional: context like 'work' or 'personal' or project name",
      "confidence": 0.0-1.0
    }}
  ]
}}

If should_remember is false, memories should be an empty list.
"""

DETECT_PERSONA_PROMPT = """Based on the current conversation, determine which persona/role is most appropriate for this interaction.

Available personas:
{personas}

Current conversation:
{conversation}

Current persona: {current_persona}

Consider:
- What kind of task is being discussed?
- What expertise is needed?
- Has the conversation topic shifted significantly?

Respond in JSON format:
{{
  "should_switch": true/false,
  "target_persona": "persona name or null if creating new",
  "new_persona_name": "name for new persona if creating",
  "new_persona_description": "description if creating new",
  "reason": "brief explanation"
}}
"""

RESOLVE_CONFLICT_PROMPT = """There is a conflict in memory. We have existing information that may contradict new information.

Existing memory:
- Subject: {old_subject}
- Predicate: {old_predicate}
- Object: {old_object}
- Recorded at: {old_timestamp}
- Source: {old_source}

New information:
- Subject: {new_subject}
- Predicate: {new_predicate}
- Object: {new_object}
- Source: {new_source}

Context from conversation:
{context}

Determine how to handle this conflict:
- "keep_old": Keep the existing memory, ignore new information
- "use_new": Update with new information (deprecate old)
- "both_valid": Both are valid in different contexts (different scopes)
- "ask_user": Unclear, should ask user for clarification

Respond in JSON format:
{{
  "action": "keep_old" | "use_new" | "both_valid" | "ask_user",
  "reason": "explanation",
  "scope_for_new": "if both_valid, what scope should new memory have"
}}
"""

GENERATE_COMMIT_MESSAGE_PROMPT = """Generate a brief, descriptive commit message for the following memory changes:

Changes:
{changes}

Context:
{context}

Respond with a single line commit message (max 72 chars), no quotes or formatting.
"""


@dataclass
class MemoryDecision:
    """Result of memory analysis."""
    should_remember: bool
    reason: str
    memories: list[dict[str, Any]]


@dataclass
class PersonaDecision:
    """Result of persona detection."""
    should_switch: bool
    target_persona: str | None
    new_persona_name: str | None
    new_persona_description: str | None
    reason: str


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""
    action: str  # keep_old, use_new, both_valid, ask_user
    reason: str
    scope_for_new: str | None


class MemoryController:
    """
    LLM-driven memory controller.
    
    Handles autonomous memory management including:
    - Deciding what to remember
    - Extracting structured memories from conversations
    - Detecting when to switch personas
    - Resolving memory conflicts
    """
    
    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str | None = None,
    ):
        self.store = store
        self.provider = provider
        self.model = model or provider.get_default_model()
    
    async def _call_llm(self, prompt: str) -> str:
        """Make an LLM call and return the response content."""
        response = await self.provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            temperature=0.3,  # Lower temperature for more consistent decisions
            max_tokens=1024,
        )
        return response.content or ""
    
    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling common issues."""
        # Try to find JSON in the response
        response = response.strip()
        
        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            response = "\n".join(lines)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON object
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end])
                except json.JSONDecodeError:
                    pass
            return {}
    
    async def analyze_for_memory(
        self,
        conversation: str,
        memory_context: str = "",
    ) -> MemoryDecision:
        """
        Analyze a conversation to determine if memories should be created.
        
        Args:
            conversation: The conversation text to analyze.
            memory_context: Current memory context for deduplication.
        
        Returns:
            MemoryDecision with results.
        """
        prompt = SHOULD_REMEMBER_PROMPT.format(
            conversation=conversation,
            memory_context=memory_context or "No existing memories.",
        )
        
        response = await self._call_llm(prompt)
        data = self._parse_json_response(response)
        
        return MemoryDecision(
            should_remember=data.get("should_remember", False),
            reason=data.get("reason", ""),
            memories=data.get("memories", []),
        )
    
    async def detect_persona(
        self,
        conversation: str,
        current_persona: str,
    ) -> PersonaDecision:
        """
        Detect if persona should be switched based on conversation.
        
        Args:
            conversation: Current conversation.
            current_persona: Name of current persona/branch.
        
        Returns:
            PersonaDecision with results.
        """
        # Get available personas
        branches = self.store.list_branches()
        personas = "\n".join([
            f"- {b.name}: {b.persona or 'No description'}"
            for b in branches
        ])
        
        prompt = DETECT_PERSONA_PROMPT.format(
            personas=personas,
            conversation=conversation,
            current_persona=current_persona,
        )
        
        response = await self._call_llm(prompt)
        data = self._parse_json_response(response)
        
        return PersonaDecision(
            should_switch=data.get("should_switch", False),
            target_persona=data.get("target_persona"),
            new_persona_name=data.get("new_persona_name"),
            new_persona_description=data.get("new_persona_description"),
            reason=data.get("reason", ""),
        )
    
    async def resolve_conflict(
        self,
        old_event: MemoryEvent,
        new_event: MemoryEvent,
        context: str = "",
    ) -> ConflictResolution:
        """
        Resolve a conflict between existing and new memory.
        
        Args:
            old_event: Existing memory event.
            new_event: New conflicting event.
            context: Conversation context.
        
        Returns:
            ConflictResolution with action to take.
        """
        prompt = RESOLVE_CONFLICT_PROMPT.format(
            old_subject=old_event.subject,
            old_predicate=old_event.predicate,
            old_object=old_event.object,
            old_timestamp=old_event.timestamp.isoformat(),
            old_source=old_event.source,
            new_subject=new_event.subject,
            new_predicate=new_event.predicate,
            new_object=new_event.object,
            new_source=new_event.source,
            context=context or "No additional context.",
        )
        
        response = await self._call_llm(prompt)
        data = self._parse_json_response(response)
        
        return ConflictResolution(
            action=data.get("action", "ask_user"),
            reason=data.get("reason", ""),
            scope_for_new=data.get("scope_for_new"),
        )
    
    async def generate_commit_message(
        self,
        events: list[MemoryEvent],
        context: str = "",
    ) -> str:
        """
        Generate a commit message for memory changes.
        
        Args:
            events: Events being committed.
            context: Conversation context.
        
        Returns:
            Generated commit message.
        """
        changes = "\n".join([
            f"- [{e.event_type}] {e.subject} {e.predicate} {e.object}"
            for e in events
        ])
        
        prompt = GENERATE_COMMIT_MESSAGE_PROMPT.format(
            changes=changes,
            context=context[:500] if context else "No context.",
        )
        
        response = await self._call_llm(prompt)
        # Clean up response
        message = response.strip().strip('"\'')
        # Truncate if too long
        if len(message) > 72:
            message = message[:69] + "..."
        
        return message or "Update memories"
    
    async def process_conversation(
        self,
        conversation: str,
        session_key: str | None = None,
    ) -> list[MemoryEvent]:
        """
        Process a conversation and automatically create memories.
        
        This is the main entry point for autonomous memory management.
        It analyzes the conversation, creates appropriate memories,
        handles persona switching, and commits the changes.
        
        Args:
            conversation: The conversation to process.
            session_key: Optional session identifier.
        
        Returns:
            List of created memory events.
        """
        # Get current memory context
        memory_context = self.store.view.to_context_string()
        
        # Analyze for memories
        decision = await self.analyze_for_memory(conversation, memory_context)
        
        if not decision.should_remember or not decision.memories:
            return []
        
        # Create events
        events = []
        for mem in decision.memories:
            event = MemoryEvent(
                event_type="add",
                subject=mem.get("subject", "unknown"),
                predicate=mem.get("predicate", "has"),
                object=mem.get("object", ""),
                scope=mem.get("scope"),
                confidence=mem.get("confidence", 0.8),
                source="agent_inferred",
                evidence=conversation[:500],  # Store snippet as evidence
            )
            
            # Check for conflicts
            existing = self.store.view.get(
                event.subject,
                event.predicate,
                event.scope,
            )
            
            if existing and existing.object != event.object:
                # Handle conflict
                resolution = await self.resolve_conflict(existing, event, conversation)
                
                if resolution.action == "keep_old":
                    continue  # Skip this event
                elif resolution.action == "use_new":
                    # Mark old as deprecated
                    deprecate_event = MemoryEvent(
                        event_type="deprecate",
                        subject=existing.subject,
                        predicate=existing.predicate,
                        object=existing.object,
                        scope=existing.scope,
                        parent_id=existing.id,
                        source="agent_inferred",
                    )
                    events.append(deprecate_event)
                elif resolution.action == "both_valid":
                    # Give new event a different scope
                    event.scope = resolution.scope_for_new
                elif resolution.action == "ask_user":
                    # For now, skip and let user decide later
                    # TODO: Add to pending queue
                    continue
            
            events.append(event)
        
        if not events:
            return []
        
        # Generate commit message
        message = await self.generate_commit_message(events, conversation)
        
        # Commit the memories
        self.store.commit(events, message)
        
        return events
    
    async def maybe_switch_persona(
        self,
        conversation: str,
    ) -> str | None:
        """
        Check if persona should be switched and perform the switch.
        
        Args:
            conversation: Current conversation.
        
        Returns:
            New persona name if switched, None otherwise.
        """
        current = self.store.get_current_branch()
        decision = await self.detect_persona(conversation, current)
        
        if not decision.should_switch:
            return None
        
        # Create new persona if needed
        if decision.new_persona_name:
            self.store.create_branch(
                decision.new_persona_name,
                persona=decision.new_persona_description,
            )
            self.store.switch_branch(decision.new_persona_name)
            return decision.new_persona_name
        
        # Switch to existing persona
        if decision.target_persona:
            if self.store.switch_branch(decision.target_persona):
                return decision.target_persona
        
        return None
