# Public repository release decision record

This record is the handoff checklist for turning the current private
development repository into a public-source repository. It complements the
generated release status snapshot in
[`public-release-status.md`](./public-release-status.md).

The current package distribution path is allowed. The full repository release
path is intentionally blocked until each decision below has an explicit owner,
resolution, and evidence link.

## Current gate shape

Run this before editing the record:

```bash
python hub_uv.py run python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
python hub_uv.py run python scripts/public_core_inventory.py --status --include-blockers
```

Expected current shape:

- package distribution is allowed;
- repository public release is blocked;
- all remaining blockers require human confirmation;
- no remaining blocker family is currently auto-fixable.

## Required decisions

| Decision | Owner | Required outcome before public repo release |
| --- | --- | --- |
| Release version | Release maintainer | Choose the next public version, then update package metadata, changelog, tag plan, and generated status together. |
| Repository visibility | Code owner | Decide whether the entire repository becomes public or the public release remains package-only. |
| Private marker handling | Code owner plus project owner | Choose one path for each flagged file: sanitize, relocate to a private repository, replace with synthetic examples, or keep the repository private. |
| Internal workflow docs | Code owner plus advisor | Move, sanitize, or explicitly keep private workflow documents out of the public repository candidate. |
| Internal style packs | Code owner plus style owner | Split private style packs into a private distribution, replace them with public-safe aliases, or keep the repository private. |
| License and IP approval | Code owner, advisor, institution policy owner | Confirm Apache-2.0 public-source rights and absence of thesis, manuscript, patent, grant, or unpublished-data restrictions. |
| Dependency/license review | Release maintainer | Confirm dependency licenses remain compatible with public-source release and package distribution. |
| Publishing ownership | Release maintainer | Confirm PyPI/TestPyPI maintainers, GitHub release permissions, and Trusted Publishing settings. |

## Decision log template

Copy one row per decision or blocker family when approval is obtained.

| Date | Scope | Decision | Evidence link | Owner | Follow-up issue/PR |
| --- | --- | --- | --- | --- | --- |
| TBD | release_version | TBD | TBD | TBD | TBD |
| TBD | repository_visibility | TBD | TBD | TBD | TBD |
| TBD | private_marker | TBD | TBD | TBD | TBD |
| TBD | private_workflow_doc | TBD | TBD | TBD | TBD |
| TBD | style_pack | TBD | TBD | TBD | TBD |
| TBD | license_ip | TBD | TBD | TBD | TBD |
| TBD | dependencies | TBD | TBD | TBD | TBD |
| TBD | publishing_ownership | TBD | TBD | TBD | TBD |

## Implementation workflow after decisions

Use this order once the decision log has enough evidence to proceed:

1. Refresh the generated status snapshot and detailed blockers.
2. Apply only approved moves, sanitization, version bumps, or splits.
3. Re-run the full repository public gate.
4. Rebuild package artifacts from a clean tree.
5. Run package metadata, package surface, consumer install, and release-asset smokes.
6. Run the full test suite and static checks.
7. Review the diff for accidental reintroduction of private markers or internal-only docs.
8. Commit, push, and merge only after the public repository gate is green or the release remains explicitly package-only.

## Verification commands

```bash
python hub_uv.py run python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
python hub_uv.py run python scripts/public_core_inventory.py --status --include-blockers
python hub_uv.py run python scripts/check_public_release.py
python hub_uv.py run python scripts/public_package_surface.py
python hub_uv.py run python scripts/package_metadata_smoke.py
python hub_uv.py run python scripts/consumer_install_smoke.py
python hub_uv.py run python -m pytest
python hub_uv.py run ruff check .
git diff --check
```

For package-only releases, `scripts/check_public_release.py` may remain blocked
by approved private-repository-only files. For full public repository release,
it must pass.
