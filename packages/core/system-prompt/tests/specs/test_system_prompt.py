"""1:1 tests for `taiyi_core_system_prompt` — render, types, service, plugin."""

from __future__ import annotations

import asyncio

import pytest
from cordis import Context

from taiyi_core_system_prompt import (
    PERSONA_ORDER,
    PERSONA_SECTION,
    TOOL_ORDER_REST,
    AssembleContext,
    AssembledContext,
    AssembledSection,
    Config,
    ContextSnapshotSection,
    PromptAssembly,
    PromptContext,
    PromptLayer,
    PromptSection,
    SystemPrompt,
    ToolProviderResult,
    ToolSchema,
    join_context_sections,
    order_tools,
    render_context_sections,
    render_context_snapshot,
    render_prompt,
    validate_tool_order,
)

# ===========================================================================
# Constants
# ===========================================================================


def test_persona_section_constant() -> None:
    assert PERSONA_SECTION == "deployment:persona"


def test_persona_order_constant() -> None:
    assert PERSONA_ORDER == 0


def test_tool_order_rest_constant() -> None:
    assert TOOL_ORDER_REST == "<unlisted-tools>"


# ===========================================================================
# Types
# ===========================================================================


def test_tool_schema_equality() -> None:
    a = ToolSchema(name="foo", description="d", parameters={"type": "object"})
    b = ToolSchema(name="foo", description="d", parameters={"type": "object"})
    assert a == b


def test_tool_schema_inequality() -> None:
    a = ToolSchema(name="foo", description="d", parameters={})
    b = ToolSchema(name="bar", description="d", parameters={})
    assert a != b


def test_tool_schema_eq_with_non_tool_schema() -> None:
    """Comparison with a non-ToolSchema returns ``NotImplemented`` (Python: False)."""
    a = ToolSchema(name="foo", description="d", parameters={})
    assert (a == "not-a-tool") is False


def test_assemble_context_basic() -> None:
    ctx = AssembleContext(scope=object(), signal=object())
    assert ctx.scope is not None
    assert ctx.signal is not None


def test_assembled_section_slots() -> None:
    s = AssembledSection(name="x", text="y")
    assert s.name == "x"
    assert s.text == "y"


def test_assembled_context_slots() -> None:
    s = AssembledContext(name="a", text="b")
    assert s.name == "a"
    assert s.text == "b"


def test_context_snapshot_section_slots() -> None:
    s = ContextSnapshotSection(name="x", text="y")
    assert s.name == "x"
    assert s.text == "y"


def test_prompt_section_default_complete_false() -> None:
    s = PromptSection(name="x", order=0, text="hi")
    assert s.complete is False


def test_prompt_section_complete_true() -> None:
    s = PromptSection(name="x", order=0, text="hi", complete=True)
    assert s.complete is True


def test_config_to_upstream_kwargs() -> None:
    cfg = Config(persona="hello")
    kw = cfg.to_upstream_kwargs()
    assert kw["persona"] == "hello"
    assert kw["include_harness_identity"] is True
    assert kw["include_runtime_context"] is True
    assert kw["tool_order"] is None


def test_config_rejects_extra_fields() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config(persona="x", unknown=1)  # type: ignore[call-arg]


# ===========================================================================
# validate_tool_order
# ===========================================================================


def test_validate_tool_order_none_returns_none() -> None:
    assert validate_tool_order(None) is None


def test_validate_tool_order_valid() -> None:
    order = [TOOL_ORDER_REST, "alpha", "beta"]
    assert validate_tool_order(order) is order


def test_validate_tool_order_duplicates_throws() -> None:
    with pytest.raises(ValueError, match='toolOrder lists "alpha" more than once'):
        validate_tool_order([TOOL_ORDER_REST, "alpha", "alpha"])


def test_validate_tool_order_missing_rest_throws() -> None:
    with pytest.raises(ValueError, match='toolOrder must contain'):
        validate_tool_order(["alpha", "beta"])


# ===========================================================================
# order_tools
# ===========================================================================


def _tools() -> list[ToolSchema]:
    return [
        ToolSchema(name="gamma", description="", parameters=None),
        ToolSchema(name="alpha", description="", parameters=None),
        ToolSchema(name="beta", description="", parameters=None),
    ]


def test_order_tools_none_sorts_lexicographically() -> None:
    out = order_tools(_tools(), None, set())
    assert [t.name for t in out] == ["alpha", "beta", "gamma"]


def test_order_tools_uses_configured_order() -> None:
    tools = _tools()
    out = order_tools(
        tools,
        ["beta", TOOL_ORDER_REST],
        {"alpha", "beta", "gamma"},
    )
    # "beta" listed first, then the rest (alpha, gamma) sorted.
    assert [t.name for t in out] == ["beta", "alpha", "gamma"]


def test_order_tools_reserved_name_throws() -> None:
    tools = [
        ToolSchema(name=TOOL_ORDER_REST, description="", parameters=None),
    ]
    with pytest.raises(
        ValueError, match="tool provider returned reserved tool name"
    ):
        order_tools(tools, None, set())


def test_order_tools_unknown_name_throws() -> None:
    with pytest.raises(
        ValueError, match="toolOrder lists unregistered tool"
    ):
        order_tools(_tools(), ["zeta", TOOL_ORDER_REST], {"alpha", "beta"})


def test_order_tools_unknown_name_pluralization() -> None:
    with pytest.raises(ValueError) as exc:
        order_tools(
            _tools(),
            ["zeta1", "zeta2", TOOL_ORDER_REST],
            {"alpha", "beta"},
        )
    msg = str(exc.value)
    # When there's more than one unknown, the message has plural form
    assert "tools" in msg


def test_compare_tool_names() -> None:
    a = ToolSchema(name="alpha", description="", parameters=None)
    b = ToolSchema(name="alpha", description="", parameters=None)
    c = ToolSchema(name="beta", description="", parameters=None)
    assert validate_tool_order  # sanity import
    from taiyi_core_system_prompt.render import compare_tool_names

    assert compare_tool_names(a, b) == 0
    assert compare_tool_names(a, c) == -1
    assert compare_tool_names(c, a) == 1


# ===========================================================================
# render_prompt
# ===========================================================================


def _assembly(
    sections: list[AssembledSection] | None = None,
    variables: dict[str, str | None] | None = None,
    contexts: list[AssembledContext] | None = None,
    tools: list[ToolSchema] | None = None,
) -> PromptAssembly:
    return PromptAssembly(
        sections=list(sections) if sections is not None else [],
        contexts=contexts or [],
        tools=tools or [],
        variables=variables or {},
    )


def test_render_prompt_basic_joining() -> None:
    a = _assembly(
        [
            AssembledSection(name="a", text="first"),
            AssembledSection(name="b", text="second"),
        ]
    )
    assert render_prompt(a) == "first\n\nsecond"


def test_render_prompt_drops_empty_sections() -> None:
    a = _assembly(
        [
            AssembledSection(name="a", text=""),
            AssembledSection(name="b", text="second"),
        ]
    )
    assert render_prompt(a) == "second"


def test_render_prompt_all_empty_returns_empty() -> None:
    a = _assembly(
        [
            AssembledSection(name="a", text=""),
            AssembledSection(name="b", text=""),
        ]
    )
    assert render_prompt(a) == ""


def test_render_prompt_interpolates_variables() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hello {{name}}")],
        variables={"name": "world"},
    )
    assert render_prompt(a) == "hello world"


def test_render_prompt_substituted_value_not_rescanned() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="prefix {{x}}")],
        variables={"x": "suffix {{y}}"},
    )
    assert render_prompt(a) == "prefix suffix {{y}}"


def test_render_prompt_unknown_variable_throws() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hello {{nope}}")],
        variables={},
    )
    with pytest.raises(ValueError, match="unknown prompt variable"):
        render_prompt(a)


def test_render_prompt_none_value_throws() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hi {{x}}")],
        variables={"x": None},
    )
    with pytest.raises(ValueError, match="has no value"):
        render_prompt(a)


def test_render_prompt_malformed_complete_throws() -> None:
    """`{{nam}}` matches the regex, but variables map doesn't have it → unknown."""
    a = _assembly(
        [AssembledSection(name="a", text="hello {{nam}}")],
    )
    with pytest.raises(ValueError, match="unknown prompt variable"):
        render_prompt(a)


def test_render_prompt_malformed_name_starts_with_digit_throws() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hello {{1xyz}}")],
    )
    with pytest.raises(ValueError, match="malformed prompt variable"):
        render_prompt(a)


def test_render_prompt_partial_group_with_brace_throws() -> None:
    """`{{a{b}}` has a brace inside the group; falls into the malformed branch."""
    a = _assembly(
        [AssembledSection(name="a", text="{{a{b}}")],
    )
    with pytest.raises(ValueError, match="malformed prompt variable reference at"):
        render_prompt(a)


def test_render_prompt_empty_name_throws() -> None:
    a = _assembly([AssembledSection(name="a", text="hello {{}} world")])
    with pytest.raises(ValueError, match="malformed prompt variable"):
        render_prompt(a)


def test_render_prompt_invalid_name_throws() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hello {{1invalid}} world")],
    )
    with pytest.raises(ValueError, match="malformed prompt variable"):
        render_prompt(a)


def test_render_prompt_invalid_name_with_dash_throws() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="hello {{a-b}} world")],
    )
    with pytest.raises(ValueError, match="malformed prompt variable"):
        render_prompt(a)


def test_render_prompt_lone_open_brace_literal() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="this {{ has no closing")],
    )
    assert render_prompt(a) == "this {{ has no closing"


def test_render_prompt_known_vars_listed_in_error() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="{{missing}}")],
        variables={"other": "x"},
    )
    with pytest.raises(ValueError, match="registered variables: other"):
        render_prompt(a)


def test_render_prompt_no_known_variables_message() -> None:
    a = _assembly(
        [AssembledSection(name="a", text="{{missing}}")],
        variables={},
    )
    with pytest.raises(ValueError, match=r"registered variables: \(none\)"):
        render_prompt(a)


# ===========================================================================
# render_context_snapshot / render_context_sections / join_context_sections
# ===========================================================================


def test_render_context_snapshot_joins_with_intro() -> None:
    a = _assembly(
        contexts=[
            AssembledContext(name="c1", text="foo"),
            AssembledContext(name="c2", text="bar"),
        ]
    )
    out = render_context_snapshot(a)
    assert out.startswith("Current runtime context.")
    assert "foo" in out
    assert "bar" in out


def test_render_context_snapshot_empty_assembly() -> None:
    a = _assembly(contexts=[])
    assert render_context_snapshot(a) == ""


def test_render_context_sections_filters_empties() -> None:
    a = _assembly(
        contexts=[
            AssembledContext(name="c1", text=""),
            AssembledContext(name="c2", text="bar"),
        ]
    )
    sections = render_context_sections(a)
    assert [s.name for s in sections] == ["c2"]
    assert sections[0].text == "bar"


def test_render_context_sections_uses_assembly_variables() -> None:
    a = _assembly(
        contexts=[AssembledContext(name="c1", text="hello {{name}}")],
        variables={"name": "world"},
    )
    sections = render_context_sections(a)
    assert sections[0].text == "hello world"


def test_join_context_sections_empty() -> None:
    assert join_context_sections([]) == ""


def test_join_context_sections_single() -> None:
    sections = [ContextSnapshotSection(name="c1", text="hi")]
    assert join_context_sections(sections) == (
        "Current runtime context. This snapshot supersedes earlier "
        "runtime-context snapshots.\n\nhi"
    )


def test_join_context_sections_multiple() -> None:
    sections = [
        ContextSnapshotSection(name="c1", text="hi"),
        ContextSnapshotSection(name="c2", text="there"),
    ]
    out = join_context_sections(sections)
    assert "hi" in out
    assert "there" in out
    assert "hi\n\nthere" in out


# ===========================================================================
# PromptLayer
# ===========================================================================


def test_prompt_layer_initial_state_is_empty() -> None:
    layer = PromptLayer(None)
    assert layer.is_empty() is True


def test_prompt_layer_not_empty_after_section() -> None:
    layer = PromptLayer(None)
    layer.sections.insert("a", PromptSection(name="a", order=0, text="x"))
    assert layer.is_empty() is False


def test_prompt_layer_scope_owned_error_message() -> None:
    layer = PromptLayer(None)
    layer.sections.insert("a", PromptSection(name="a", order=0, text="x"))
    with pytest.raises(ValueError, match='prompt section "a" is already registered'):
        layer.sections.insert("a", PromptSection(name="a", order=0, text="y"))


def test_prompt_layer_scoped_error_message() -> None:
    layer = PromptLayer(object())
    layer.sections.insert("a", PromptSection(name="a", order=0, text="x"))
    with pytest.raises(
        ValueError, match='prompt section "a" is already registered in this scope'
    ):
        layer.sections.insert("a", PromptSection(name="a", order=0, text="y"))


def test_prompt_layer_context_duplicate_message_global() -> None:
    layer = PromptLayer(None)
    layer.contexts.insert("c", PromptContext(name="c", order=0, text="x"))
    with pytest.raises(ValueError, match='prompt context "c" is already registered'):
        layer.contexts.insert("c", PromptContext(name="c", order=0, text="y"))


def test_prompt_layer_variable_duplicate_message_global() -> None:
    layer = PromptLayer(None)
    layer.variables.insert("v", lambda _ctx: "x")
    with pytest.raises(ValueError, match='prompt variable "v" is already registered'):
        layer.variables.insert("v", lambda _ctx: "y")


def test_prompt_layer_anonymous_sections_independent() -> None:
    layer = PromptLayer(None)
    layer.runtime_context_suppressors.append(True)
    assert layer.is_empty() is False
    undo = layer.tool_providers.append(lambda _ctx: ToolProviderResult(schemas=[]))
    assert layer.is_empty() is False
    undo()
    # After disposing tool provider, only suppressors remain
    assert not layer.runtime_context_suppressors.is_empty()
    assert layer.tool_providers.is_empty()


# ===========================================================================
# SystemPrompt construction & basic assemble
# ===========================================================================


def _run(coro):
    return asyncio.run(coro)


async def _assemble(svc: SystemPrompt, ctx: Context, **kw) -> PromptAssembly:
    return await svc.assemble(AssembleContext(**kw) if kw else None)


class _BoundListener:
    """Listener callable; cordis prepends the dispatch context as the first arg."""

    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    def __call__(self, _this, *_args, **_kw) -> None:
        self.sink.append("change")


def test_system_prompt_default_register_harness_identity_and_persona() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        layers = svc._layers  # noqa: SLF001 — exercises internal registry
        assert layers.global_layer.sections.has("harness:identity")
        assert layers.global_layer.sections.has(PERSONA_SECTION)
    finally:
        _run(ctx.dispose())


def test_system_prompt_custom_persona() -> None:
    ctx = Context()
    cfg = Config(persona="I am a custom agent.")
    svc = SystemPrompt(ctx, config=cfg.to_upstream_kwargs())
    try:
        section = svc._layers.global_layer.sections.get(PERSONA_SECTION)  # noqa: SLF001
        assert section is not None
        assert section.text == "I am a custom agent."
    finally:
        _run(ctx.dispose())


def test_system_prompt_config_can_omit_harness_identity() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={"include_harness_identity": False, "persona": "x"},
    )
    try:
        assert not svc._layers.global_layer.sections.has("harness:identity")  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_default_suppresses_runtime_context() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={"include_runtime_context": False},
    )
    try:
        assert not svc._layers.global_layer.runtime_context_suppressors.is_empty()  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_default_keeps_runtime_context_active() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        assert svc._layers.global_layer.runtime_context_suppressors.is_empty()  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_section_register_and_unregister() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config={"persona": ""})
    try:
        dispose = svc.section(
            PromptSection(name="s2", order=10, text="tool guide")
        )
        assert svc._layers.global_layer.sections.has("s2")  # noqa: SLF001
        dispose()
        assert not svc._layers.global_layer.sections.has("s2")  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_context_register_and_unregister() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        dispose = svc.context(PromptContext(name="snapshot", order=0, text="ctx"))
        assert svc._layers.global_layer.contexts.has("snapshot")  # noqa: SLF001
        dispose()
        assert not svc._layers.global_layer.contexts.has("snapshot")  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_section_non_finite_order_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(TypeError, match='prompt section "bad" order must be a finite number'):
            svc.section(PromptSection(name="bad", order=float("inf"), text="x"))
    finally:
        _run(ctx.dispose())


def test_system_prompt_section_nan_order_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(TypeError, match='prompt section "bad"'):
            svc.section(PromptSection(name="bad", order=float("nan"), text="x"))
    finally:
        _run(ctx.dispose())


def test_system_prompt_context_non_finite_order_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(TypeError, match='prompt context "c" order must be a finite number'):
            svc.context(PromptContext(name="c", order=float("inf"), text="x"))
    finally:
        _run(ctx.dispose())


def test_system_prompt_variable_validates_name() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(
            ValueError, match='invalid prompt variable name "1bad"'
        ):
            svc.variable("1bad", lambda _ctx: "v")
    finally:
        _run(ctx.dispose())


def test_system_prompt_variable_invalid_dash_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(ValueError, match='invalid prompt variable name "a-b"'):
            svc.variable("a-b", lambda _ctx: "v")
    finally:
        _run(ctx.dispose())


def test_system_prompt_variable_register_and_unregister() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        dispose = svc.variable("name", lambda _ctx: "world")
        assert svc._layers.global_layer.variables.has("name")  # noqa: SLF001
        dispose()
        assert not svc._layers.global_layer.variables.has("name")  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_tools_register_and_unregister() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        dispose = svc.tools(lambda _ctx: ToolProviderResult(schemas=[]))
        assert not svc._layers.global_layer.tool_providers.is_empty()  # noqa: SLF001
        dispose()
        assert svc._layers.global_layer.tool_providers.is_empty()  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_suppress_runtime_context_register() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        dispose = svc.suppress_runtime_context()
        assert not svc._layers.global_layer.runtime_context_suppressors.is_empty()  # noqa: SLF001
        dispose()
    finally:
        _run(ctx.dispose())


def test_system_prompt_section_duplicate_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(ValueError, match="already registered"):
            svc.section(PromptSection(name="dup", order=10, text="a"))
            svc.section(PromptSection(name="dup", order=20, text="b"))
    finally:
        _run(ctx.dispose())


# ===========================================================================
# SystemPrompt.assemble
# ===========================================================================


def test_assemble_returns_default_harness_plus_persona() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config={"persona": "You are a helpful AI."})
    try:
        assembly = _run(_assemble(svc, ctx))
        names = [s.name for s in assembly.sections]
        assert names == ["harness:identity", "deployment:persona"]
        texts = [s.text for s in assembly.sections]
        assert texts[0] == "You are an AI agent powered by DeepSeek Harness."
        assert texts[1] == "You are a helpful AI."
    finally:
        _run(ctx.dispose())


def test_assemble_sorts_sections_by_ascending_order() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "p",
            "include_harness_identity": False,
        },
    )
    try:
        svc.section(PromptSection(name="z", order=50, text="z"))
        svc.section(PromptSection(name="y", order=-50, text="y"))
        svc.section(PromptSection(name="x", order=0, text="x"))
        assembly = _run(_assemble(svc, ctx))
        assert [s.name for s in assembly.sections] == [
            "y",
            "deployment:persona",
            "x",
            "z",
        ]
    finally:
        _run(ctx.dispose())


def test_assemble_with_text_provider() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config={"persona": "p", "include_harness_identity": False})
    try:
        captured: dict[str, AssembleContext] = {}

        def _resolve(actx: AssembleContext) -> str:
            captured["ctx"] = actx
            return "computed"

        svc.section(PromptSection(name="dynamic", order=10, text=_resolve))
        assembly = _run(_assemble(svc, ctx))
        assert len(assembly.sections) == 2
        assert assembly.sections[1].text == "computed"
        assert captured["ctx"] is not None
    finally:
        _run(ctx.dispose())


def test_assemble_with_callable_context_provider() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config={"persona": "p", "include_harness_identity": False})
    try:
        svc.context(
            PromptContext(name="dynctx", order=10, text=lambda _a: "ctx-text")
        )
        assembly = _run(_assemble(svc, ctx))
        assert assembly.contexts[0].text == "ctx-text"
    finally:
        _run(ctx.dispose())


def test_assemble_resolves_variables() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config={"persona": "p", "include_harness_identity": False})
    try:
        svc.section(PromptSection(name="hi", order=0, text="hi {{name}}"))
        svc.variable("name", lambda _a: "world")
        assembly = _run(_assemble(svc, ctx))
        assert assembly.variables["name"] == "world"
        rendered = render_prompt(assembly)
        assert rendered == "p\n\nhi world"
    finally:
        _run(ctx.dispose())


def test_assemble_shadows_global_section_in_scope() -> None:
    """A scoped registration of the same name shadows the global one."""
    ctx = Context()
    global_svc = SystemPrompt(
        ctx,
        config={
            "persona": "global-persona",
            "include_harness_identity": False,
        },
    )

    from taiyi_core_scope.scope import create_scope

    key = object()
    scope = create_scope(ctx, key)
    scoped_svc = SystemPrompt(scope.ctx)
    try:
        # Register the same name in BOTH layers; the scoped layer wins.
        global_svc.section(
            PromptSection(name="unique", order=10, text="global-text")
        )
        scoped_svc.section(
            PromptSection(name="unique", order=10, text="scoped-text")
        )
        # Without a scope → global
        global_assembly = _run(global_svc.assemble())
        unique_global = next(s for s in global_assembly.sections if s.name == "unique")
        assert unique_global.text == "global-text"
        # With a scope → scoped wins
        scoped_assembly = _run(scoped_svc.assemble(AssembleContext(scope=key)))
        unique_scoped = next(
            s for s in scoped_assembly.sections if s.name == "unique"
        )
        assert unique_scoped.text == "scoped-text"
    finally:
        _run(scope.dispose())
        _run(ctx.dispose())


def test_assemble_scoped_variable_shadows_global() -> None:
    """A scoped variable registration shadows a global one of the same name."""
    ctx = Context()
    global_svc = SystemPrompt(
        ctx,
        config={"persona": "p", "include_harness_identity": False},
    )
    global_svc.section(PromptSection(name="hi", order=0, text="hi {{name}}"))
    global_svc.variable("name", lambda _a: "global")

    from taiyi_core_scope.scope import create_scope

    key = object()
    scope = create_scope(ctx, key)
    scoped_svc = SystemPrompt(scope.ctx)
    scoped_svc.variable("name", lambda _a: "scoped")
    try:
        # Global assemble sees the global variable.
        global_assembly = _run(global_svc.assemble())
        assert global_assembly.variables["name"] == "global"
        # Scoped assemble sees the scoped override.
        scoped_assembly = _run(scoped_svc.assemble(AssembleContext(scope=key)))
        assert scoped_assembly.variables["name"] == "scoped"
    finally:
        _run(scope.dispose())
        _run(ctx.dispose())


def test_assemble_section_non_finite_value_types_throws() -> None:
    """Non-numeric order values raise ``TypeError`` from the validation helper."""
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        # ``True`` is rejected by the ``bool`` guard inside ``_is_finite``.
        with pytest.raises(TypeError):
            svc.section(PromptSection(name="bad", order=True, text="x"))  # type: ignore[arg-type]
    finally:
        _run(ctx.dispose())


def test_assemble_section_unconvertible_order_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(TypeError):
            svc.section(
                PromptSection(
                    name="bad",
                    order=object(),  # type: ignore[arg-type]
                    text="x",
                )
            )
    finally:
        _run(ctx.dispose())


def test_assemble_complete_section_replaces_sections() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "fallback",
            "include_harness_identity": False,
        },
    )
    try:
        svc.section(
            PromptSection(
                name="override",
                order=0,
                text="I am the complete prompt.",
                complete=True,
            )
        )
        assembly = _run(_assemble(svc, ctx))
        assert len(assembly.sections) == 1
        assert assembly.sections[0].name == "override"
        assert assembly.sections[0].text == "I am the complete prompt."
    finally:
        _run(ctx.dispose())


def test_assemble_multiple_complete_sections_throws() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "p",
            "include_harness_identity": False,
        },
    )
    try:
        svc.section(
            PromptSection(name="c1", order=0, text="x", complete=True)
        )
        svc.section(
            PromptSection(name="c2", order=10, text="y", complete=True)
        )
        with pytest.raises(ValueError, match="multiple complete prompt sections"):
            _run(_assemble(svc, ctx))
    finally:
        _run(ctx.dispose())


def test_assemble_collects_tools_from_providers() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        svc.tools(
            lambda _ctx: ToolProviderResult(
                schemas=[ToolSchema(name="t1", description="d", parameters=None)],
                known_names=["t1"],
            )
        )
        assembly = _run(_assemble(svc, ctx))
        assert [t.name for t in assembly.tools] == ["t1"]
    finally:
        _run(ctx.dispose())


def test_assemble_applies_tool_order_with_rest() -> None:
    ctx = Context()
    cfg = Config(
        persona="p",
        include_harness_identity=False,
        tool_order=["zzz", TOOL_ORDER_REST],
    )
    svc = SystemPrompt(ctx, config=cfg.to_upstream_kwargs())
    try:
        svc.tools(
            lambda _ctx: ToolProviderResult(
                schemas=[
                    ToolSchema(name="alpha", description="", parameters=None),
                    ToolSchema(name="beta", description="", parameters=None),
                    ToolSchema(name="zzz", description="", parameters=None),
                ],
                known_names=["alpha", "beta", "zzz"],
            )
        )
        assembly = _run(_assemble(svc, ctx))
        # zzz listed first, then the rest sorted: alpha, beta
        assert [t.name for t in assembly.tools] == ["zzz", "alpha", "beta"]
    finally:
        _run(ctx.dispose())


def test_assemble_unknown_tool_in_config_throws() -> None:
    ctx = Context()
    cfg = Config(
        persona="p",
        include_harness_identity=False,
        tool_order=["alpha", "missing", TOOL_ORDER_REST],
    )
    svc = SystemPrompt(ctx, config=cfg.to_upstream_kwargs())
    try:
        svc.tools(
            lambda _ctx: ToolProviderResult(
                schemas=[ToolSchema(name="alpha", description="", parameters=None)],
            )
        )
        with pytest.raises(ValueError, match="toolOrder lists unregistered tool"):
            _run(_assemble(svc, ctx))
    finally:
        _run(ctx.dispose())


def test_assemble_runtime_context_suppressed_empty() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "p",
            "include_harness_identity": False,
            "include_runtime_context": False,
        },
    )
    try:
        svc.context(PromptContext(name="c", order=10, text="ctx"))
        assembly = _run(_assemble(svc, ctx))
        assert assembly.contexts == []
    finally:
        _run(ctx.dispose())


def test_assemble_runtime_context_kept_by_default() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "p",
            "include_harness_identity": False,
        },
    )
    try:
        svc.context(PromptContext(name="c", order=10, text="ctx"))
        assembly = _run(_assemble(svc, ctx))
        assert assembly.contexts[0].text == "ctx"
    finally:
        _run(ctx.dispose())


def test_assemble_detaches_tool_parameters() -> None:
    """The assembly holds a ``copy.deepcopy`` snapshot of tool parameters."""
    ctx = Context()

    def _prov(_ctx: AssembleContext) -> ToolProviderResult:
        # Return a fresh dict each call so we can verify the snapshot is detached.
        return ToolProviderResult(
            schemas=[
                ToolSchema(name="t1", description="d", parameters={"x": 1}),
            ],
        )

    try:
        svc = SystemPrompt(ctx)
        svc.tools(_prov)
        listener_params: list = []

        def _capture(_self, assembly: PromptAssembly, _a, nxt):
            listener_params.append(assembly.tools[0].parameters)
            return nxt()

        ctx.on("system-prompt/assemble", _capture)
        _run(_assemble(svc, ctx))
        # Snapshot is detached: a later mutation of the provider's dict does not
        # leak into the captured snapshot.
        provider_dict = {"x": 1}
        svc.tools(lambda _a: ToolProviderResult(
            schemas=[ToolSchema(name="t1", description="d", parameters=provider_dict)]
        ))
        provider_dict["x"] = 999
        assembly = _run(_assemble(svc, ctx))
        assert assembly.tools[0].parameters == {"x": 1}
    finally:
        _run(ctx.dispose())


def test_assemble_emits_change_on_register() -> None:
    """Registering a section after listeners wired up emits ``system-prompt/change``."""
    ctx = Context()
    svc = SystemPrompt(ctx, config={"include_harness_identity": False, "persona": ""})
    try:
        seen: list[str] = []
        listener = _BoundListener(seen)

        ctx.on("system-prompt/change", listener)
        svc.section(PromptSection(name="s", order=0, text="x"))
        assert seen == ["change"]
    finally:
        _run(ctx.dispose())


def test_assemble_runs_waterfall_listeners() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={"persona": "p", "include_harness_identity": False},
    )

    captured: list[PromptAssembly] = []

    def _listener(_self, assembly: PromptAssembly, _actx: AssembleContext, nxt):
        captured.append(assembly)
        return assembly

    try:
        ctx.on("system-prompt/assemble", _listener)
        assembly = _run(_assemble(svc, ctx))
        assert captured, "waterfall listener should have been invoked"
        assert assembly.sections[0].text == "p"
    finally:
        _run(ctx.dispose())


def test_assemble_waterfall_listener_transforms_assembly() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={"persona": "p", "include_harness_identity": False},
    )

    def _extra_listener(
        _self,
        assembly: PromptAssembly,
        _actx: AssembleContext,
        nxt,
    ):
        assembly.variables["injected"] = "yes"
        return nxt()

    try:
        ctx.on("system-prompt/assemble", _extra_listener)
        assembly = _run(_assemble(svc, ctx))
        assert assembly.variables.get("injected") == "yes"
    finally:
        _run(ctx.dispose())


def test_assemble_complete_with_suppressed_context() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={
            "persona": "p",
            "include_harness_identity": False,
            "include_runtime_context": False,
        },
    )
    try:
        svc.section(
            PromptSection(name="prompt", order=0, text="COMPLETE", complete=True)
        )
        svc.context(PromptContext(name="ctx", order=10, text="should-not-appear"))
        assembly = _run(_assemble(svc, ctx))
        assert len(assembly.sections) == 1
        assert assembly.contexts == []
    finally:
        _run(ctx.dispose())


def test_assemble_with_no_persona_substitution_default_persona() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        assembly = _run(_assemble(svc, ctx))
        persona = next(s for s in assembly.sections if s.name == PERSONA_SECTION)
        assert persona.text == ""
    finally:
        _run(ctx.dispose())


# ===========================================================================
# SystemPrompt config validation
# ===========================================================================


def test_system_prompt_rejects_unsupported_config_type() -> None:
    ctx = Context()
    with pytest.raises(TypeError, match="unsupported SystemPrompt config type"):
        SystemPrompt(ctx, config=42)  # type: ignore[arg-type]


def test_system_prompt_accepts_pydantic_config() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx, config=Config(persona="hello"))
    try:
        assert svc._layers.global_layer.sections.has(PERSONA_SECTION)  # noqa: SLF001
    finally:
        _run(ctx.dispose())


def test_system_prompt_assemble_context_coercion_dict() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:

        async def _go() -> PromptAssembly:
            return await svc.assemble({"scope": None, "signal": None})  # type: ignore[arg-type]

        result = _run(_go())
        assert isinstance(result, PromptAssembly)
    finally:
        _run(ctx.dispose())


def test_system_prompt_assemble_context_coercion_invalid() -> None:
    ctx = Context()
    svc = SystemPrompt(ctx)
    try:
        with pytest.raises(TypeError, match="unsupported assemble context type"):
            _run(svc.assemble(42))  # type: ignore[arg-type]
    finally:
        _run(ctx.dispose())


# ===========================================================================
# Plugin
# ===========================================================================


def test_setup_is_a_plugin_instance() -> None:
    from cordis import Plugin

    from taiyi_core_system_prompt.plugin import setup

    assert isinstance(setup, Plugin)


def test_plugin_installs_system_prompt_on_ctx() -> None:

    from taiyi_core_system_prompt.plugin import setup

    ctx = Context()
    try:
        dispose = _run(setup.setup(ctx, {}))
        svc = ctx.system_prompt  # type: ignore[attr-defined]
        assert isinstance(svc, SystemPrompt)
        dispose()
    finally:
        _run(ctx.dispose())


def test_plugin_accepts_none_config() -> None:

    from taiyi_core_system_prompt.plugin import setup

    ctx = Context()
    try:
        dispose = _run(setup.setup(ctx))
        svc = ctx.system_prompt  # type: ignore[attr-defined]
        assert isinstance(svc, SystemPrompt)
        dispose()
    finally:
        _run(ctx.dispose())


def test_plugin_accepts_dict_config() -> None:

    from taiyi_core_system_prompt.plugin import setup

    ctx = Context()
    try:
        dispose = _run(
            setup.setup(ctx, {"persona": "agent-x", "include_harness_identity": False})
        )
        svc = ctx.system_prompt  # type: ignore[attr-defined]
        assert isinstance(svc, SystemPrompt)
        dispose()
    finally:
        _run(ctx.dispose())


def test_plugin_accepts_pydantic_config() -> None:

    from taiyi_core_system_prompt.plugin import setup

    ctx = Context()
    try:
        dispose = _run(setup.setup(ctx, Config(persona="agent-y")))
        svc = ctx.system_prompt  # type: ignore[attr-defined]
        assert isinstance(svc, SystemPrompt)
        dispose()
    finally:
        _run(ctx.dispose())


def test_plugin_rejects_invalid_config_type() -> None:

    from taiyi_core_system_prompt.plugin import setup

    ctx = Context()
    try:
        with pytest.raises(TypeError, match="unsupported system-prompt config type"):
            _run(setup.setup(ctx, "not-a-config"))  # type: ignore[arg-type]
    finally:
        _run(ctx.dispose())


def test_make_ctx_fixture_disposes(make_ctx) -> None:
    """The ``make_ctx`` fixture auto-disposes its Context at teardown."""
    from taiyi_core_system_prompt import SystemPrompt

    svc = SystemPrompt(make_ctx, config={"persona": "fixture-test"})
    section = svc._layers.global_layer.sections.get(PERSONA_SECTION)  # noqa: SLF001
    assert section is not None
    assert section.text == "fixture-test"


# ===========================================================================
# Invariant companion (barrel)
# ===========================================================================


def test_invariant_barrel_reexports_public_surface() -> None:
    from taiyi_core_system_prompt import invariant as inv

    expected = {
        "PERSONA_SECTION",
        "PERSONA_ORDER",
        "TOOL_ORDER_REST",
        "render_prompt",
        "render_context_snapshot",
        "render_context_sections",
        "join_context_sections",
        "PromptLayer",
        "SystemPrompt",
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
    }
    for name in expected:
        assert hasattr(inv, name), f"invariant missing {name!r}"


def test_invariant_symbols_match_implementation() -> None:
    from taiyi_core_system_prompt import invariant as inv
    from taiyi_core_system_prompt.service import PromptLayer as _ImplPL
    from taiyi_core_system_prompt.service import SystemPrompt as _ImplSP
    from taiyi_core_system_prompt.types import PromptSection as _ImplPS

    assert inv.PromptLayer is _ImplPL
    assert inv.SystemPrompt is _ImplSP
    assert inv.PromptSection is _ImplPS


# ===========================================================================
# End-to-end waterfall
# ===========================================================================


def test_assemble_end_to_end_with_listener() -> None:
    ctx = Context()
    svc = SystemPrompt(
        ctx,
        config={"persona": "p", "include_harness_identity": False},
    )

    seen: list[str] = []

    async def _listener(_self, assembly: PromptAssembly, _a, nxt):
        seen.append("got")
        return assembly

    try:
        ctx.on("system-prompt/assemble", _listener)
        assembly = _run(_assemble(svc, ctx))
        assert seen == ["got"]
        assert assembly.sections[0].text == "p"
    finally:
        _run(ctx.dispose())
