# Public repository release decision record

This record is the human-facing handoff checklist for turning the current
private development repository into a public-source repository. It mirrors,
but does not grant, the machine-readable authorization in
`public-core-inventory.json`. The generator does not parse approvals from this
Markdown file. It complements the generated release status snapshot in
[`public-release-status.md`](./public-release-status.md).

The current package distribution path is allowed. Repository owner
authorization for the v0.20.0 public release is recorded below and in the
authoritative inventory. A green machine gate remains evidence rather than the
source of authorization; re-run it for the exact commit selected for release.
The authoritative machine-readable authorization source is the inventory's
`repository_publication_approved` field together with one or more validated
`repository_publication_approval_evidence` HTTPS references. Both must be
present, and the referenced approvals must be reviewed before changing them.

## Current gate shape

Run this before editing the record:

```bash
python hub_uv.py run python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
python hub_uv.py run python scripts/public_core_inventory.py --status --include-blockers
```

Expected current shape after the owner-recorded approval:

- package distribution is allowed;
- the repository technical release gate is green with zero technical blockers;
- repository publication authorization is recorded with one HTTPS evidence
  reference;
- human/legal/release approval is owner-recorded, not inferred from machine
  technical gates.

## Recorded authorization

The authenticated repository owner `moonweave` recorded the following explicit
authorization on 2026-07-20:

- release scope: FigOps v0.20.0 from PR #224;
- authorized actions: merge, tag creation, GitHub Release, TestPyPI, and PyPI
  publication;
- approvals: required human, legal, and release approvals granted;
- evidence: [PR #224 owner authorization](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221).

This record mirrors the inventory JSON. It does not replace checking technical
evidence on the exact release commit, nor does it contain any credential.

## Decision coverage

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

## Decision log

Copy one row per decision or blocker family when approval is obtained. This
table is a human-readable mirror; after review, record the approved state and
its evidence references in the authoritative inventory JSON as a separate,
reviewed change.

| Date | Scope | Decision | Evidence link | Owner | Follow-up issue/PR |
| --- | --- | --- | --- | --- | --- |
| 2026-07-20 | v0.20.0 public release | Owner authorizes merge, tag, GitHub Release, TestPyPI, and PyPI publication; required human/legal/release approvals granted. | [PR #224 owner authorization](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221) | moonweave | PR #224 |

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
