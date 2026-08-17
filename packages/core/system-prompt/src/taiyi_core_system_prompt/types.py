"""`taiyi_core_system_prompt.types` — public type surface.

1:1 Python port of the type declarations in upstream `@deepseek-ai/dsh-system-prompt/src/index.ts`.

Carries the data carriers the assembly pipeline depends on:

- :class:`ToolSchema` — provider-facing tool schema (mirrors `dsh-llm`'s `ToolSchema`)
- :data:`AssembleContext` — per-assembly context (scope + signal)
- :data:`PromptSection`, :data:`PromptContext` — registry inputs
- :data:`AssembledSection`, :data:`AssembledContext` — resolved registry inputs
- :data:`ToolProviderResult` — provider return shape
- :data:`PromptAssembly` — composed model input
- :data:`ContextSnapshotSection` — snapshot section returned by
  :func:`render_context_sections`
- :class:`Config` — pydantic settings for the :class:`Service`
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from taiyi_core_scope.scope import ScopeKey

__all__ = [
    "ToolSchema",
    "AssembleContext",
    "PromptSection",
    "PromptContext",
    "AssembledSection",
    "AssembledContext",
    "ToolProviderResult",
    "ContextSnapshotSection",
    "PromptAssembly",
    "PromptTextProvider",
    "VariableProvider",
    "Config",
]


# ---------------------------------------------------------------------------
# Tool schema (mirrors `@deepseek-ai/dsh-llm`'s `ToolSchema` for our local use)
# ---------------------------------------------------------------------------


class ToolSchema:
    """Tool schema visible to a model. Immutable frozen dataclass.

    Mirrors upstream `ToolSchema`. ``name`` is the unique tool identity;
    ``parameters`` is the detached tool-parameter payload (``structuredClone``).
    """

    __slots__ = ("name", "description", "parameters")

    def __init__(self, name: str, description: str, parameters: Any) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"ToolSchema(name={self.name!r}, description={self.description!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolSchema):
            return NotImplemented
        return (
            self.name == other.name
            and self.description == other.description
            and self.parameters == other.parameters
        )

    def __hash__(self) -> int:  # pragma: no cover — mutable semantics
        return hash((self.name, self.description, id(self.parameters)))


# ---------------------------------------------------------------------------
# Provider callables
# ---------------------------------------------------------------------------

PromptTextProvider = Callable[["AssembleContext"], str]
"""A section or context text resolved per assembly."""

VariableProvider = Callable[["AssembleContext"], "str | None"]
"""A variable value resolved per assembly; ``None`` means undefined."""


# ---------------------------------------------------------------------------
# AssembleContext — merge-extensible per-assembly context
# ---------------------------------------------------------------------------


class AssembleContext:
    """Per-assembly context used by every text and tool provider.

    Mirrors upstream ``AssembleContext``. The class is intentionally a
    mutable bag (matching upstream's interface — concrete consumers /
    extensions can attach arbitrary fields).
    """

    __slots__ = ("scope", "signal")

    def __init__(
        self,
        scope: ScopeKey | None = None,
        signal: Any | None = None,
    ) -> None:
        self.scope = scope
        self.signal = signal

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"AssembleContext(scope={self.scope!r}, signal={self.signal!r})"


# ---------------------------------------------------------------------------
# Registry inputs
# ---------------------------------------------------------------------------


class PromptSection:
    """One contributed section of the system prompt (registry input)."""

    __slots__ = ("name", "order", "text", "complete")

    def __init__(
        self,
        name: str,
        order: float,
        text: str | PromptTextProvider,
        complete: bool = False,
    ) -> None:
        self.name = name
        self.order = order
        self.text = text
        self.complete = complete

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        kind = "fn" if callable(self.text) else "str"
        return (
            f"PromptSection(name={self.name!r}, order={self.order!r}, "
            f"text=<{kind}>, complete={self.complete!r})"
        )


class PromptContext:
    """Dynamic model-context materialization (registry input)."""

    __slots__ = ("name", "order", "text")

    def __init__(
        self,
        name: str,
        order: float,
        text: str | PromptTextProvider,
    ) -> None:
        self.name = name
        self.order = order
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        kind = "fn" if callable(self.text) else "str"
        return (
            f"PromptContext(name={self.name!r}, order={self.order!r}, text=<{kind}>)"
        )


# ---------------------------------------------------------------------------
# Assembled contributions
# ---------------------------------------------------------------------------


class AssembledSection:
    """One section of an assembly with text resolved."""

    __slots__ = ("name", "text")

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"AssembledSection(name={self.name!r}, text=<{len(self.text)} chars>)"


class AssembledContext:
    """One resolved dynamic context contribution."""

    __slots__ = ("name", "text")

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"AssembledContext(name={self.name!r}, text=<{len(self.text)} chars>)"


class ContextSnapshotSection:
    """One rendered snapshot section returned by :func:`render_context_sections`."""

    __slots__ = ("name", "text")

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"ContextSnapshotSection(name={self.name!r}, text=<{len(self.text)} chars>)"


# ---------------------------------------------------------------------------
# Tool provider shape
# ---------------------------------------------------------------------------


class ToolProviderResult:
    """Return shape of a tool-schema provider.

    ``schemas`` are the visible schemas for THIS assembly; ``known_names``
    is the pre-restriction name universe for ``Config.toolOrder`` validation
    (defaults to ``schemas``' names).
    """

    __slots__ = ("schemas", "known_names")

    def __init__(
        self,
        schemas: list[ToolSchema],
        known_names: list[str] | None = None,
    ) -> None:
        self.schemas = list(schemas)
        self.known_names = list(known_names) if known_names is not None else None

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"ToolProviderResult(schemas=[{', '.join(s.name for s in self.schemas)}], "
            f"known_names={self.known_names!r})"
        )


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


class PromptAssembly:
    """Merge-extensible assembled model input.

    Sections and contexts remain uninterpolated until rendered; tools are
    already in canonical order.
    """

    __slots__ = ("sections", "contexts", "tools", "variables")

    def __init__(
        self,
        sections: list[AssembledSection],
        contexts: list[AssembledContext],
        tools: list[ToolSchema],
        variables: dict[str, str | None],
    ) -> None:
        self.sections = list(sections)
        self.contexts = list(contexts)
        self.tools = list(tools)
        self.variables = dict(variables)

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"PromptAssembly(sections={len(self.sections)}, "
            f"contexts={len(self.contexts)}, tools={len(self.tools)}, "
            f"variables={len(self.variables)})"
        )


# ---------------------------------------------------------------------------
# Plugin config (pydantic)
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """Plugin config: the deployment-authored fragment of the system prompt.

    Mirrors upstream `Config`. ``toolOrder`` defaults to ``None`` so omission
    is preserved (an explicit empty list still triggers the `<unlisted-tools>`
    marker check).
    """

    model_config = ConfigDict(extra="forbid")

    include_harness_identity: bool = Field(default=True)
    """Include the fixed DeepSeek Harness identity before the deployment persona (default true)."""

    include_runtime_context: bool = Field(default=True)
    """Include dynamic runtime-context snapshots in model history (default true)."""

    persona: str = Field(default="")
    """Deployment-wide order-0 persona template."""

    tool_order: list[str] | None = Field(default=None)
    """Model-facing tool names in order; ``<unlisted-tools>`` exactly once."""

    def to_upstream_kwargs(self) -> dict[str, Any]:
        """Return the dict form used by :class:`taiyi_core_system_prompt.service.SystemPrompt`."""
        return {
            "include_harness_identity": self.include_harness_identity,
            "include_runtime_context": self.include_runtime_context,
            "persona": self.persona,
            "tool_order": self.tool_order,
        }
