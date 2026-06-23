# Public Core Boundary Matrix

Status: current local MPL-2.0 public-core boundary
Date: 2026-06-23

This artifact records the current local public-core boundary after the approved MPL-2.0 cleanup. It does not authorize external publication, repository visibility changes, package or registry publishing, commits, pushes, PRs, tags, releases, or history rewriting.

## Public Core

| path_or_concept | disposition | reason | remaining_gate |
| --- | --- | --- | --- |
| MPL-2.0 `LICENSE`, `NOTICE`, README/package license metadata | public_core | The user approved local MPL-2.0 public-core readiness. | Publication still requires separate approval. |
| Generic MCP server and read-only tool surface | public_core | Health, discovery, style listing, validation, inspection, rendering, artifact collection, and docs generation are reusable Graph Hub behavior. | Keep write tools gated and verify MCP smoke/tests. |
| Generic `project_config.yaml` contracts and scaffolds | public_core | Project contracts and scaffolds are generic and do not require private research data. | Keep examples synthetic/public-safe. |
| Public journal styles | public_core | Live target formats are `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`. | Release checker and style tests must remain green. |
| Release checker and provenance scanner | public_core | The checker remains the conservative gate for public-core readiness. | Do not weaken or bypass to pass. |
| Root, runtime-root, allowed-data-root, and write-tool trust model | public_core | These safety boundaries are central to agent-triggered rendering. | Security review before publication. |

## Outside Public Core

| path_or_concept | disposition | reason | remaining_gate |
| --- | --- | --- | --- |
| Project-specific datasets | excluded | Real research data is not part of the reusable source core. | Separate explicit approval and notices. |
| Unpublished workflow notes and manuscript assets | excluded | These may contain private research context or unpublished know-how. | Separate private-content review. |
| Credentials and local runtime state | excluded | Secrets and runtime caches must not be distributed. | Never publish. |
| Internal style packs and private project markers | excluded | Public style/profile surfaces have been generalized or removed. | Release checker must remain clean except denylist fixtures. |
| Public mirror, visibility change, registry/package release, tag, GitHub release | external_action | These are externally visible actions outside this cleanup. | Explicit publication approval. |
| Commit, push, PR, rebase, reset, force-push, history rewrite | git_side_effect | These mutate repository or remote state. | Explicit user request/approval. |

## Stop Condition

Stop before external publication, remote visibility changes, package or registry uploads, pushes, PRs, commits, tags, releases, history rewrites, or exporting excluded private material.
