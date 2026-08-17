"""taiyi-core-system-prompt — registry for ordered system sections, dynamic context,
tool schemas, and prompt variables.

1:1 Python port of `@deepseek-ai/dsh-system-prompt`. The Service composes a
system prompt from a deployment persona, a static ``harness:identity`` opener,
registered scoped :class:`PromptSection` entries, dynamic :class:`PromptContext`
contributions, and a cooperative assembly waterfall that ultimately yields a
:class:`PromptAssembly` for the model.

Public surface:

- :class:`SystemPrompt` — registry Service
- :class:`PromptLayer` — per-scope storage
- :class:`ToolSchema` — provider-facing tool schema
- :class:`AssembleContext` — per-assembly context
- :class:`PromptSection`, :class:`PromptContext` — registry inputs
- :class:`AssembledSection`, :class:`AssembledContext`, :class:`ContextSnapshotSection`
- :class:`ToolProviderResult`, :class:`PromptAssembly`
- :func:`render_prompt`, :func:`render_context_snapshot`,
  :func:`render_context_sections`, :func:`join_context_sections`
- :data:`PERSONA_SECTION`, :data:`PERSONA_ORDER`, :data:`TOOL_ORDER_REST`
- :class:`Config` — pydantic settings model
- :mod:`taiyi_core_system_prompt.plugin` — cordis plugin entry
"""

from __future__ import annotations

from taiyi_core_system_prompt.render import (
    PERSONA_ORDER,
    PERSONA_SECTION,
    TOOL_ORDER_REST,
    join_context_sections,
    order_tools,
    render_context_sections,
    render_context_snapshot,
    render_prompt,
    validate_tool_order,
)
from taiyi_core_system_prompt.service import PromptLayer, SystemPrompt
from taiyi_core_system_prompt.types import (
    AssembleContext,
    AssembledContext,
    AssembledSection,
    Config,
    ContextSnapshotSection,
    PromptAssembly,
    PromptContext,
    PromptSection,
    ToolProviderResult,
    ToolSchema,
)

# Bind the pydantic ``Config`` model onto the :class:`SystemPrompt` service
# after both symbols are defined so ``SystemPrompt._normalize_config`` can
# recognize pydantic config instances without an import cycle.
SystemPrompt._config_cls = Config

__version__ = "0.1.0"

__all__ = [
    # Constants
    "PERSONA_SECTION",
    "PERSONA_ORDER",
    "TOOL_ORDER_REST",
    # Render helpers
    "render_prompt",
    "render_context_snapshot",
    "render_context_sections",
    "join_context_sections",
    # Ordering helpers
    "validate_tool_order",
    "order_tools",
    # Service
    "PromptLayer",
    "SystemPrompt",
    # Types
    "AssembleContext",
    "AssembledContext",
    "AssembledSection",
    "Config",
    "ContextSnapshotSection",
    "PromptAssembly",
    "PromptContext",
    "PromptSection",
    "ToolProviderResult",
    "ToolSchema",
    # Meta
    "__version__",
]
