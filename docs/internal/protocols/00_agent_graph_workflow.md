# FigOps Agent Workflow

This protocol is for agents that use FigOps to make, inspect, or audit figures.
Its governing rule is simple: let the agent make scientific and visual choices,
and use FigOps to catch boundary, integrity, provenance, contract, and
unsupported-claim failures that the agent may miss.

FigOps is independent from Athena. Use another toolbox only for a separate
non-figure task, then bring the resulting data or cited calculation evidence
back to FigOps.

## Choose the smallest useful lane

- For a known, simple table, render directly with the appropriate available
  quick-chart capability.
- When the schema is unknown, inspect bounded data facts first. Do not require
  style, project, or capability discovery when the needed inputs are already
  known.
- For a complex figure, author or revise a declared project-local Python or R
  plotting script, then use the contained project render path. Never put source
  code or a command string in a render payload.
- Query health, styles, project metadata, or capability details only when that
  information is needed to resolve uncertainty.

A non-source-mutating render does not require a dry run. A successful render
response should be enough to locate its artifact, evidence, manifest, and
preview; do not add a metadata-collection call merely as ceremony.

## Visual evidence loop

Use one initial render, then continue with targeted revisions only while the
evidence shows meaningful progress toward the requested communication goal.

1. **Render once.** Preserve the user's data meaning, labels, and authored
   visual choices. Record the job and the returned artifact, evidence,
   manifest, and `preview_uri` references.
2. **Check objective evidence.** Before interpreting the picture, inspect the
   render status and failure stage, artifact integrity, declared outputs,
   provenance coverage, data-contract results, and statistical-claim linkage.
   Fix a hard failure before treating the artifact as a valid candidate.
3. **Retrieve the preview lazily.** Read the returned preview resource only
   when visual inspection is needed. Keep image bytes out of ordinary text
   responses and do not substitute a filesystem path or unverified binary for
   the bounded resource.
4. **Actually inspect the image.** Use visual capability to examine the
   rendered preview itself. Check whether the intended comparison is legible,
   labels retain their meaning, marks and annotations are visible, hierarchy
   communicates the intended story, and clipping or overlap is apparent. Do
   not infer these observations from metadata alone.
5. **Make an evidence-based decision.** Keep three things distinct: objective
   kernel evidence, findings from an explicitly selected policy, and visual
   observations made by the agent. State which evidence supports the decision
   and which judgment remains human-owned.
6. **Revise a specific cause.** If another render is warranted, change only the
   identified cause or a tightly related group of causes, render again, and
   compare the new evidence and preview with the prior candidate. Stop when the
   requested communication goal is met, a hard blocker remains, authorization
   for the next change is absent, or a user-owned decision is required.

Visible aesthetic preferences are not hard failures unless an explicit policy
or project contract makes them constraints. Conversely, a visually pleasing
image does not override corrupt artifacts, missing provenance, failed data
contracts, or unsupported statistical claims.

## Unavailable evidence is a result, not a pass

If the preview or another evidence item is `unavailable`, preserve its reason
and resolution hint. Unavailable never means passed, and it must not be silently
converted into a visual or integrity judgment.

- Try a stated safe resolution only when it stays inside the current task and
  trust boundary.
- If no bounded preview can be produced, report that the image was not visually
  reviewed. Do not claim that layout, legibility, or aesthetics were inspected
  from metadata.
- If visual judgment is essential and the preview remains unavailable, provide
  the verified non-visual evidence and ask the user or a human reviewer to
  inspect a safely exported artifact.
- `manual_review_needed=true` must be disclosed, but it does not prevent the
  agent from inspecting the preview or making a targeted revision. It reserves
  final scientific or venue acceptance for a human.

## Status and claim boundaries

- Treat a structured `status=error` result as evidence to diagnose, not as a
  successful render and not as missing output to hide.
- Follow a relevant `resolution_hint` when it addresses the observed failure,
  but choose the next action from the whole evidence set rather than a canned
  priority list.
- Never describe automatic checks as human approval. Clean automatic evidence
  still requires human judgment for scientific validity and final venue
  suitability.
- An inferential annotation is usable only when its calculation evidence,
  analysis-artifact hash, and test or model metadata are linked and verified.
- Preserve `manual_review_needed`, unavailable checks, advisories, and mutation
  records in the handoff.

## Write and source-mutation gates

Rendering and reading a bounded preview are not reasons to require a dry run.
Keep the stricter gate for operations that would modify project source,
normalize or migrate files, destructively replace an existing artifact, or
overwrite an immutable job:

1. inspect a proposed change or dry-run result when the operation supports one;
2. confirm that the user's request authorizes the specific mutation;
3. fail closed when write tools are disabled or the target escapes the allowed
   project/runtime boundary.

Stop and request direction before an unauthorized destructive mutation. Normal
edits to a project-local plotting script are allowed only when the user's task
already includes implementing or revising that script.

## Handoff

Report the artifact and preview references, render/evidence status, hard
failures, policy findings, visual observations, unavailable evidence, applied
mutations, provenance coverage, and any remaining human decision. If work stops
before the goal is met, name the concrete blocker, missing authorization, or
user-owned visual/scientific tradeoff. Do not invent an iteration limit as a
reason to stop useful work.
