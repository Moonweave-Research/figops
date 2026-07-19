# Repository surface audit

Last checked: 2026-07-15

This note records the current public/private boundary for the FigOps repository.
It is separate from the PyPI package gate: the package artifacts are public, and
the full repository technical release gate now passes after marker sanitization,
workflow-doc relocation, and public style-pack registry splitting.

## Result summary

| Check | Result |
| --- | --- |
| Secret scan | Pass: `gitleaks detect --source . --redact` found no leaks across 287 commits. |
| Suspicious tracked filenames | Pass: no tracked env/key/token/credential-style filenames found. |
| Tracked ignored files | Pass: `git ls-files -ci --exclude-standard` is empty. |
| Public wheel/sdist surface | Pass: `scripts/public_package_surface.py` reports no blockers. |
| Full repository public gate | Pass: `scripts/check_public_release.py` reports no blockers. |
| GitHub repository metadata | Updated for FigOps with PyPI homepage and focused topics. |
| Social preview asset | Added at `docs/assets/figops-social-preview.png`. |

## What is safe today

- Public PyPI distribution of the built wheel/sdist is allowed.
- The package manifest prunes repo-only docs, tests, examples, and agent files
  from the public artifacts.
- GitHub Release assets are safe to share as package artifacts.

## Repository public gate

`python scripts/check_public_release.py` currently passes for the repository.
The remaining public-release decision is not a technical blocker: it is the
normal owner/advisor/university/IP approval recorded in
[public-release-decision-record.md](./public-release-decision-record.md).

Completed blocker families:

- internal/private style packs split out of the public style-pack registry;
- internal project/style markers replaced with public-safe aliases outside the
  release-check fixtures;
- workflow protocol docs moved from the legacy private path to
  `docs/internal/protocols/`;
- `0.19.0` was published and the source metadata subsequently advanced to the
  `0.20.0` release-candidate line; published artifacts remain at `0.19.0` until
  release promotion is explicitly approved and completed.

Current structured status:

```bash
python scripts/public_core_inventory.py --status --format markdown
python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
```

Expected current shape: public package distribution is allowed, repository
public release is allowed by the technical gate, and remaining publication
approval is external release management rather than a script blocker.

Record those confirmations in
[public-release-decision-record.md](./public-release-decision-record.md) before
changing repository visibility.

Before changing repository visibility to public, confirm the non-technical
ownership/IP approvals and keep the public-release gate green on the final
release candidate.

## Tracked files to reconsider before a public repo release

These files are useful for local agent/development operations but are not needed
by normal package users:

- `AGENTS.md`
- `Claude.md`
- `GEMINI.md`
- `SUB_AGENTS.md`
- `Research_Central_Architecture.md`
- `task.md`
- historical design docs under `docs/02-design/`, `docs/internal/protocols/`, and
  `docs/superpowers/`

Keep reviewing them when public-facing docs are edited; the current release gate
no longer finds private markers in them.

## Local ignored clutter observed

The following local/generated paths are ignored and not tracked, so they are not
a repository leak:

- `.demo_graphs/`
- `.omo/`
- `.omx/`
- `.playwright-mcp/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.venv/`
- `.codegraph/`
- `dist/` and `build/`
- example `.build_state.json` files

They can be deleted locally for disk cleanup, but deleting them is not required
for repository safety.

## Commands used

```bash
git ls-files -ci --exclude-standard
gitleaks detect --source . --redact --report-format json
python scripts/public_core_inventory.py --status --format markdown
python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
python scripts/public_core_inventory.py --status --include-blockers
python scripts/check_public_release.py
python scripts/public_package_surface.py
```
