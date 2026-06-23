# Candidate Public Core Patch Manifest

Status: current local cleanup manifest
Date: 2026-06-23

This manifest records the local MPL-2.0 public-core cleanup now present in the working tree. It is not a commit, PR, release note, public mirror, package publication, registry submission, or repository visibility change.

## Applied Local Cleanup Categories

- Replaced source license posture with MPL-2.0 public-core language in license, notice, README, and package metadata.
- Removed private/internal style packs and private style format/profile names from live public style registries.
- Limited public target formats to `nature`, `science`, `default`, `acs`, `rsc`, `elsevier`, `wiley`, and `cell`.
- Renamed the project-specific conventions adapter surface from `surfur` to generic `workspace`.
- Kept `scripts/check_public_release.py` conservative and verified it passes without weakening.
- Deleted tracked private workflow docs from the public-core surface.
- Regenerated or checked generated tool documentation where affected.
- Added/updated tests for public style, adapter, release-checker, and preset validation behavior.

## Private Marker Disposition

Private marker literals are not copied here. The only intended remaining occurrences are in the release checker and its tests as denylist fixtures. Any new occurrence outside those files is a release blocker.

## Verification Plan

Before handoff or commit, run:

```bash
uv run python scripts/check_public_release.py
uv run python graphhub_mcp_server.py --smoke
uv run python scripts/gen_tool_reference.py --check
uv run python -m pytest -q
GIT_MASTER=1 git diff --check
GIT_MASTER=1 git status --short
```

## Forbidden Actions

Still forbidden without explicit user approval:

- Publication, public mirror creation, repository visibility changes, package publishing, registry publishing, release-note publication, tag creation, or release creation.
- Commit, push, PR creation, reset, rebase, force-push, or history rewrite.
- Exporting excluded project-specific datasets, unpublished workflow notes, credentials, manuscript assets, or internal style packs.
