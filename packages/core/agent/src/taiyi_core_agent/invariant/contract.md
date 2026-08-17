# `taiyi_core_agent.invariant` — companion contract

This companion registers one rule. It is installed into the
`@deepseek-ai/dsh-invariants` plugin via the standard
`register(packageName, installer)` flow at companion-load time.

## `agent/status` no-op transition

Source: `src/invariant.ts`, single install on `'agent/status'` with
`global: true`.

The companion tracks the latest emitted status per `Agent` and **fails
on a repeated destination** — i.e. emitting `agent/status` with the same
`status` value twice in a row for the same agent is a contract violation.

A no-op transition is a contract violation because the loop guarantees
each transition is informative (`idle ⇄ running`). A silent repeat
indicates the caller dropped a step in the state machine, the loop is
double-emitting due to a regression, or a listener is rewriting the
emitted status field. None of these are recoverable without operator
intervention.
