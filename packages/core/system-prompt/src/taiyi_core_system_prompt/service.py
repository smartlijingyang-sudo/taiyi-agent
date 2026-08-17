"""`taiyi_core_system_prompt.service` — registry Service for prompt assembly.

1:1 Python port of `@deepseek-ai/dsh-system-prompt/src/index.ts` `SystemPrompt`
class plus its supporting :class:`PromptLayer` storage.

Public surface exports:

- :class:`PromptLayer` — one scope's storage (sections, contexts,
  runtime-context suppressors, tool providers, variables)
- :class:`SystemPrompt` — the registry Service
"""

from __future__ import annotations

import copy
import inspect
import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from cordis import Context, Service
from taiyi_core_scope.scope import scope_target
from taiyi_core_scope.store import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)

from taiyi_core_system_prompt.render import (
    PERSONA_ORDER,
    PERSONA_SECTION,
    order_tools,
    validate_tool_order,
)
from taiyi_core_system_prompt.types import (
    AssembleContext,
    AssembledContext,
    AssembledSection,
    PromptAssembly,
    PromptContext,
    PromptSection,
    ToolProviderResult,
    ToolSchema,
)

if TYPE_CHECKING:
    pass


__all__ = [
    "PromptLayer",
    "ToolProvider",
    "VariableProviderCallable",
    "SystemPrompt",
]


# ---------------------------------------------------------------------------
# Local callables
# ---------------------------------------------------------------------------

ToolProvider = Callable[[AssembleContext], ToolProviderResult]
VariableProviderCallable = Callable[[AssembleContext], str | None]


# ---------------------------------------------------------------------------
# PromptLayer
# ---------------------------------------------------------------------------


class PromptLayer(ScopeLayer):
    """All prompt registrations owned by one global or scoped layer.

    Mirrors upstream ``PromptLayer`` which implements ``ScopeLayer``.
    Reports emptiness via :meth:`is_empty`.
    """

    __slots__ = (
        "sections",
        "contexts",
        "runtime_context_suppressors",
        "tool_providers",
        "variables",
    )

    def __init__(self, scope: Any | None) -> None:
        self.sections: NamedEntries[PromptSection] = NamedEntries(
            lambda name: ValueError(
                _duplicate_message(
                    scope,
                    "section",
                    name,
                    "agent.ctx",
                )
            )
        )
        self.contexts: NamedEntries[PromptContext] = NamedEntries(
            lambda name: ValueError(
                _duplicate_message(
                    scope,
                    "context",
                    name,
                    "agent.ctx",
                )
            )
        )
        self.runtime_context_suppressors: AnonymousEntries[bool] = AnonymousEntries()
        self.tool_providers: AnonymousEntries[ToolProvider] = AnonymousEntries()
        self.variables: NamedEntries[VariableProviderCallable] = NamedEntries(
            lambda name: ValueError(
                _duplicate_message(
                    scope,
                    "variable",
                    name,
                    "agent.ctx",
                )
            )
        )

    def is_empty(self) -> bool:
        """``True`` when this layer owns no prompt registrations."""
        return (
            self.sections.is_empty()
            and self.contexts.is_empty()
            and self.runtime_context_suppressors.is_empty()
            and self.tool_providers.is_empty()
            and self.variables.is_empty()
        )


def _duplicate_message(scope: Any | None, kind: str, name: str, override: str) -> str:
    if scope is None:
        return (
            f'prompt {kind} "{name}" is already registered '
            f"(for a per-agent override, register through that "
            f"agent's `{override}` instead)"
        )
    return f'prompt {kind} "{name}" is already registered in this scope'


# ---------------------------------------------------------------------------
# SystemPrompt Service
# ---------------------------------------------------------------------------


class SystemPrompt(Service):
    """Registry service for the prompt inputs assembled before each model step."""

    __slots__ = (
        "ctx",
        "_layers",
        "_tool_order",
    )

    # Bound at class definition so ``_normalize_config`` can recognize
    # pydantic config instances.
    _config_cls: Any = None

    def __init__(self, ctx: Context, config: Any = None) -> None:
        # Mirror upstream TS `SystemPrompt extends Service`; instantiate with
        # the supplied context and (pre-validated) config dict.
        normalized: dict[str, Any] = self._normalize_config(config)
        super().__init__(ctx)
        self._tool_order: list[str] | None = validate_tool_order(
            normalized.get("tool_order")
        )

        on_change = lambda: self._emit_change()  # noqa: E731

        self._layers = ScopedLayers(
            create_layer=lambda scope: PromptLayer(scope),
            on_change=on_change,
        )

        if normalized.get("include_harness_identity", True):
            self.section(
                PromptSection(
                    name="harness:identity",
                    order=-100,
                    text="You are an AI agent powered by DeepSeek Harness.",
                )
            )
        self.section(
            PromptSection(
                name=PERSONA_SECTION,
                order=PERSONA_ORDER,
                text=normalized.get("persona", "") or "",
            )
        )
        if not normalized.get("include_runtime_context", True):
            self.suppress_runtime_context()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def section(self, section: PromptSection) -> Callable[[], None]:
        """Register an ordered prompt section in the calling context's scope."""
        self._require_finite_order(section.order, "section", section.name)
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.sections.insert(section.name, section),
            label="systemPrompt.section()",
        )

    def context(self, context: PromptContext) -> Callable[[], None]:
        """Register ordered dynamic context in the calling context's scope."""
        self._require_finite_order(context.order, "context", context.name)
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.contexts.insert(context.name, context),
            label="systemPrompt.context()",
        )

    def suppress_runtime_context(self) -> Callable[[], None]:
        """Suppress every dynamic runtime-context contribution in scope."""
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.runtime_context_suppressors.append(True),
            label="systemPrompt.suppressRuntimeContext()",
        )

    def tools(self, provider: ToolProvider) -> Callable[[], None]:
        """Register a tool-schema provider in the calling context's scope."""
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.tool_providers.append(provider),
            label="systemPrompt.tools()",
        )

    def variable(
        self,
        name: str,
        provider: VariableProviderCallable,
    ) -> Callable[[], None]:
        """Register a prompt variable in the calling context's scope."""
        from taiyi_core_system_prompt.render import VARIABLE_NAME  # local import

        if not VARIABLE_NAME.match(name):
            raise ValueError(
                f'invalid prompt variable name "{name}" '
                f"(must match {VARIABLE_NAME.pattern!s})"
            )
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.variables.insert(name, provider),
            label="systemPrompt.variable()",
        )

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    async def assemble(
        self,
        context: AssembleContext | dict[str, Any] | None = None,
    ) -> PromptAssembly:
        """Assemble global and scoped providers, detach tool parameters,
        apply canonical ordering, then run the assembly waterfall.

        Scoped sections and variables shadow globals. The returned waterfall
        value is authoritative except that an effective complete section is
        restored afterwards as the sole prompt section.
        """
        ctx_obj: AssembleContext = self._coerce_assemble_context(context)
        scope = ctx_obj.scope

        scope_layers = self._layers.chain_layers(scope)
        runtime_context_suppressed = (
            not self._layers.global_layer.runtime_context_suppressors.is_empty()
            or any(
                not layer.runtime_context_suppressors.is_empty()
                for layer in scope_layers
            )
        )

        # Scoped variables shadow globals.
        variables: dict[str, str | None] = {}
        for name, provider in self._layers.global_layer.variables.entries():
            variables[name] = provider(ctx_obj)
        for layer in scope_layers:
            for name, provider in layer.variables.entries():
                variables[name] = provider(ctx_obj)

        section_by_name = self._layers.merge(scope, lambda layer: layer.sections)
        context_by_name = self._layers.merge(scope, lambda layer: layer.contexts)

        # Validate order against pre-restriction names while collecting visible schemas.
        providers_iter: list[ToolProvider] = [
            p
            for p in self._layers.global_layer.tool_providers.values()
        ]
        providers_iter.extend(
            p for layer in scope_layers for p in layer.tool_providers.values()
        )

        collected: list[ToolSchema] = []
        known_names: set[str] = set()
        for provider in providers_iter:
            result = provider(ctx_obj)
            schemas: list[ToolSchema] = [
                ToolSchema(
                    name=tool.name,
                    description=tool.description,
                    parameters=copy.deepcopy(tool.parameters),
                )
                for tool in result.schemas
            ]
            accepted_known = (
                result.known_names
                if result.known_names is not None
                else [s.name for s in schemas]
            )
            collected.extend(schemas)
            for nm in accepted_known:
                known_names.add(nm)

        section_definitions = sorted(
            section_by_name.values(), key=lambda s: s.order
        )
        complete_sections = [
            s for s in section_definitions if s.complete
        ]
        if len(complete_sections) > 1:
            raise ValueError(
                "multiple complete prompt sections are active: "
                + ", ".join(_json_string(s.name) for s in complete_sections)
            )

        complete_section: AssembledSection | None = None
        sections: list[AssembledSection] = []
        for section in section_definitions:
            text_value = _resolve_text(section.text, ctx_obj)
            assembled = AssembledSection(name=section.name, text=text_value)
            if section.complete:
                complete_section = AssembledSection(
                    name=assembled.name, text=assembled.text
                )
            sections.append(assembled)

        contexts: list[AssembledContext] = []
        if not runtime_context_suppressed:
            for entry in sorted(context_by_name.values(), key=lambda c: c.order):
                text_value = _resolve_text(entry.text, ctx_obj)
                contexts.append(AssembledContext(name=entry.name, text=text_value))

        assembly = PromptAssembly(
            sections=sections,
            contexts=contexts,
            tools=order_tools(collected, self._tool_order, known_names),
            variables=variables,
        )

        transformed = self._run_waterfall(scope, assembly, ctx_obj)
        if inspect.isawaitable(transformed):
            transformed = await transformed

        if complete_section is None and not runtime_context_suppressed:
            return transformed
        return PromptAssembly(
            sections=(
                [complete_section]
                if complete_section is not None
                else transformed.sections
            ),
            contexts=[] if runtime_context_suppressed else transformed.contexts,
            tools=transformed.tools,
            variables=transformed.variables,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_waterfall(
        self,
        scope: Any | None,
        assembly: PromptAssembly,
        ctx_obj: AssembleContext,
    ) -> Any:
        """Run the ``system-prompt/assemble`` waterfall. Coroutine-aware.

        Mirrors upstream ``ctx.waterfall(scopeTarget, 'system-prompt/assemble',
        assembly, context, () => Promise.resolve(assembly))``.
        """
        return self.ctx.waterfall(
            scope_target(self, scope),
            "system-prompt/assemble",
            assembly,
            ctx_obj,
            lambda: assembly,
        )

    def _emit_change(self) -> None:
        """Emit ``system-prompt/change`` unconditionally (mirror upstream)."""
        self.ctx.emit("system-prompt/change")

    @staticmethod
    def _require_finite_order(value: float, kind: str, name: str) -> None:
        if not _is_finite(value):
            raise TypeError(
                f'prompt {kind} "{name}" order must be a finite number'
            )

    @staticmethod
    def _coerce_assemble_context(value: Any) -> AssembleContext:
        if value is None:
            return AssembleContext()
        if isinstance(value, AssembleContext):
            return value
        if isinstance(value, dict):
            return AssembleContext(
                scope=value.get("scope"),
                signal=value.get("signal"),
            )
        raise TypeError(
            f"unsupported assemble context type: {type(value).__name__}"
        )

    @classmethod
    def _normalize_config(cls, config: Any) -> dict[str, Any]:
        """Normalize ``config`` (None / dict / pydantic) into a dict."""
        defaults = {
            "include_harness_identity": True,
            "include_runtime_context": True,
            "persona": "",
            "tool_order": None,
        }
        if config is None:
            return defaults
        if cls._config_cls is not None and isinstance(config, cls._config_cls):
            return {**defaults, **config.to_upstream_kwargs()}
        if isinstance(config, dict):
            merged = dict(defaults)
            merged.update(config)
            return merged
        raise TypeError(
            f"unsupported SystemPrompt config type: {type(config).__name__}"
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_finite(value: float) -> bool:
    if isinstance(value, bool):
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _resolve_text(value: str | Callable[[AssembleContext], str], ctx: AssembleContext) -> str:
    """Call ``value(ctx)`` if it's a callable, else return it unchanged."""
    if callable(value):
        return value(ctx)
    return value


def _json_string(value: str) -> str:
    """Mimic :func:`json.dumps` for a single string; tests have to compare errors."""
    import json

    return json.dumps(value)
