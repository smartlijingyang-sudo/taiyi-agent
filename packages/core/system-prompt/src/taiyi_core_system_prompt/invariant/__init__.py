"""taiyi_core_system_prompt.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of
:mod:`taiyi_core_system_prompt` so other packages in the taiyi workspace
can declare a stable dependency on the contract without coupling to the
implementation layout.

1:1 with upstream `packages/core/system-prompt/src/invariant.ts` (a barrel).
"""

from __future__ import annotations

from taiyi_core_system_prompt.render import (
    PERSONA_ORDER,
    PERSONA_SECTION,
    TOOL_ORDER_REST,
    join_context_sections,
    render_context_sections,
    render_context_snapshot,
    render_prompt,
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

__all__ = [
    # constants
    "PERSONA_SECTION",
    "PERSONA_ORDER",
    "TOOL_ORDER_REST",
    # render
    "render_prompt",
    "render_context_snapshot",
    "render_context_sections",
    "join_context_sections",
    # service
    "PromptLayer",
    "SystemPrompt",
    # types
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
]
