"""`taiyi_core_system_prompt.render` — pure assembly-rendering utilities.

1:1 Python port of the rendering helpers in upstream
`@deepseek-ai/dsh-system-prompt/src/index.ts`:

- :func:`render_prompt` — interpolate sections and join with blank lines
- :func:`render_context_snapshot` — joint snapshot for one assembly
- :func:`render_context_sections` — per-context snapshot sections
- :func:`join_context_sections` — join pre-rendered snapshot sections
- :func:`interpolate` — strict ``{{variable}}`` interpolator
- :func:`validate_tool_order` / :func:`order_tools` / :func:`compare_tool_names`
  — tool-order helpers (kept module-private)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import cmp_to_key
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from taiyi_core_system_prompt.types import (
        AssembledContext,
        AssembledSection,
        ContextSnapshotSection,
        PromptAssembly,
        ToolSchema,
    )

__all__ = [
    # public constants
    "PERSONA_SECTION",
    "PERSONA_ORDER",
    "TOOL_ORDER_REST",
    # public render helpers
    "render_prompt",
    "render_context_snapshot",
    "render_context_sections",
    "join_context_sections",
    # public ordering helper
    "validate_tool_order",
    "order_tools",
]


# ---------------------------------------------------------------------------
# Constants (1:1 with upstream)
# ---------------------------------------------------------------------------

#: The deployment persona's section name. Exported because a composition can
#: replace this slot — an agent preset shadows the deployment's persona with
#: its own — and both sides naming the same section is what makes the
#: replacement work rather than duplicate.
PERSONA_SECTION = "deployment:persona"

#: Prompt order of the persona slot; the first section a model reads.
PERSONA_ORDER = 0

#: Reserved ``Config.toolOrder`` marker for unlisted tools.
TOOL_ORDER_REST = "<unlisted-tools>"

#: Valid variable names: how they are written between the braces.
_VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

#: A complete ``{{...}}`` reference group at the scan position.
_GROUP_AT = re.compile(r"^\{\{([^{}]*)\}\}")

# Re-export aliases for tests that need regex access.
VARIABLE_NAME = _VARIABLE_NAME
GROUP_AT = _GROUP_AT


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def render_prompt(assembly: PromptAssembly) -> str:
    """Interpolate strict ``{{variable}}`` references, drop empty sections,
    and join the rest with blank lines.

    Malformed, unknown, or undefined references throw; a lone ``{{`` without
    any later ``}}`` is literal prose, and substituted values are not scanned
    again.
    """
    sections: list[AssembledSection] = assembly.sections
    variables = assembly.variables
    parts: list[str] = []
    for section in sections:
        text = _interpolate(section, variables, "section")
        if len(text) > 0:
            parts.append(text)
    return "\n\n".join(parts)


def render_context_snapshot(assembly: PromptAssembly) -> str:
    """Render the complete dynamic context snapshot for the assembly."""
    return join_context_sections(render_context_sections(assembly))


def render_context_sections(assembly: PromptAssembly) -> list[ContextSnapshotSection]:
    """Return per-context snapshot sections after interpolation.

    ``render_context_snapshot`` joins these for the model; a consumer that
    presents the snapshot uses them to attribute each part to the subsystem
    that contributed it without re-splitting the joined prose.
    """
    variables = assembly.variables
    rendered: list[ContextSnapshotSection] = []
    for context in assembly.contexts:
        from taiyi_core_system_prompt.types import ContextSnapshotSection

        text = _interpolate(context, variables, "context")
        if len(text) > 0:
            rendered.append(ContextSnapshotSection(name=context.name, text=text))
    return rendered


def join_context_sections(
    sections: Iterable[ContextSnapshotSection],
) -> str:
    """Assemble the joint context snapshot from already-rendered sections.

    A caller that also needs the sections renders them once and joins here,
    so a request does not interpolate every context twice.
    """
    body = "\n\n".join(section.text for section in sections)
    if len(body) == 0:
        return ""
    return (
        "Current runtime context. This snapshot supersedes earlier "
        "runtime-context snapshots.\n\n" + body
    )


# ---------------------------------------------------------------------------
# Interpolate
# ---------------------------------------------------------------------------


def _interpolate(
    input_: AssembledSection | AssembledContext,
    variables: dict[str, str | None],
    kind: str,
) -> str:
    """Interpolate one section or context and attribute diagnostics to its kind."""
    text = input_.text
    result_parts: list[str] = []
    last = 0
    while True:
        open_idx = text.find("{{", last)
        if open_idx < 0:
            break
        group_match = _GROUP_AT.match(text[open_idx:])
        if group_match is None:
            # A later closing brace makes this malformed; otherwise literal prose.
            if text.find("}}", open_idx + 2) >= 0:
                head = text[open_idx : open_idx + 16]
                raise ValueError(
                    f'malformed prompt variable reference at "{head}…" in {kind} '
                    f'"{input_.name}" (references are complete simple {{name}} groups)'
                )
            result_parts.append(text[last : open_idx + 2])
            last = open_idx + 2
            continue
        # ``{{}}`` yields an empty name and follows the malformed-reference path.
        name = group_match.group(0)[2:-2]
        if not _VARIABLE_NAME.match(name):
            raise ValueError(
                f'malformed prompt variable reference "{{{{{name}}}}}" '
                f"in {kind} \"{input_.name}\" "
                f"(variable names match {str(_VARIABLE_NAME.pattern)})"
            )
        # Do not resolve unregistered names through Object.prototype.
        if name not in variables:
            known = list(variables.keys())
            joined = ", ".join(known) if known else "(none)"
            raise ValueError(
                f'unknown prompt variable "{{{{{name}}}}}" in {kind} '
                f'"{input_.name}"; registered variables: {joined}'
            )
        value = variables[name]
        if value is None:
            raise ValueError(
                f'prompt variable "{{{{{name}}}}}" has no value for this assembly '
                f'({kind} "{input_.name}")'
            )
        result_parts.append(text[last:open_idx] + value)
        last = open_idx + len(group_match.group(0))
    result_parts.append(text[last:])
    return "".join(result_parts)


# ---------------------------------------------------------------------------
# Tool-order helpers
# ---------------------------------------------------------------------------


def validate_tool_order(tool_order: list[str] | None) -> list[str] | None:
    """Validate duplicate names and the required :data:`TOOL_ORDER_REST` marker.

    Registered names are checked later because plugins have not loaded yet.
    """
    if tool_order is None:
        return None
    seen: set[str] = set()
    for name in tool_order:
        if name in seen:
            raise ValueError(f'toolOrder lists "{name}" more than once')
        seen.add(name)
    if TOOL_ORDER_REST not in seen:
        raise ValueError(
            f'toolOrder must contain the "{TOOL_ORDER_REST}" rest entry '
            "(where unlisted tools are inserted)"
        )
    return tool_order


def order_tools(
    tools: list[ToolSchema],
    tool_order: list[str] | None,
    known_names: set[str],
) -> list[ToolSchema]:
    """Apply configured tool order, inserting unlisted tools lexicographically
    at :data:`TOOL_ORDER_REST`.

    Unknown configured names fail; known but restricted names may be absent.
    """
    reserved = next((t for t in tools if t.name == TOOL_ORDER_REST), None)
    if reserved is not None:
        raise ValueError(
            f'tool provider returned reserved tool name "{TOOL_ORDER_REST}" '
            "(reserved for toolOrder's rest entry)"
        )
    if tool_order is None:
        return sorted(tools, key=cmp_to_key(compare_tool_names))
    unknown = [
        n for n in tool_order if n != TOOL_ORDER_REST and n not in known_names
    ]
    if unknown:
        names = ", ".join(f'"{n}"' for n in unknown)
        known_list = ", ".join(sorted(known_names)) or "(none)"
        suffix = "s" if len(unknown) > 1 else ""
        raise ValueError(
            f"toolOrder lists unregistered tool{suffix} {names}; "
            f"known tools: {known_list}"
        )
    listed = set(tool_order)
    rest = sorted(
        (t for t in tools if t.name not in listed),
        key=cmp_to_key(compare_tool_names),
    )
    out: list[ToolSchema] = []
    by_name = {t.name: t for t in tools}
    for name in tool_order:
        if name == TOOL_ORDER_REST:
            out.extend(rest)
        else:
            out.append(by_name[name])
    return out


def compare_tool_names(a: ToolSchema, b: ToolSchema) -> int:
    """Lexicographic (code-unit) name comparison — locale-independent.

    Returns -1, 0, or 1 so the result works with :func:`functools.cmp_to_key`.
    """
    if a.name < b.name:
        return -1
    if a.name > b.name:
        return 1
    return 0
