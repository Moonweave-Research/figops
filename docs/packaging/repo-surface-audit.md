# Repository surface audit

Last checked: 2026-06-28

This note records the current public/private boundary for the FigOps repository.
It is separate from the PyPI package gate: the package artifacts are public, but
the full repository is still treated as private/internal until the blockers below
are intentionally removed or sanitized.

## Result summary

| Check | Result |
| --- | --- |
| Secret scan | Pass: `gitleaks detect --source . --redact` found no leaks across 287 commits. |
| Suspicious tracked filenames | Pass: no tracked env/key/token/credential-style filenames found. |
| Tracked ignored files | Pass: `git ls-files -ci --exclude-standard` is empty. |
| Public wheel/sdist surface | Pass: `scripts/public_package_surface.py` reports no blockers. |
| Full repository public gate | Blocked: internal docs, private markers, and internal style packs remain in the private repo. |
| GitHub repository metadata | Updated for FigOps with PyPI homepage and focused topics. |
| Social preview asset | Added at `docs/assets/figops-social-preview.png`. |

## What is safe today

- Public PyPI distribution of the built wheel/sdist is allowed.
- The package manifest prunes repo-only docs, tests, examples, and agent files
  from the public artifacts.
- GitHub Release assets are safe to share as package artifacts.

## Do not make the full repository public yet

`python scripts/check_public_release.py` currently blocks full-repo public release
because repo-only files still contain internal markers or private workflow docs.
That is expected under the current policy.

Main blocker families:

- internal/private style pack: `surfur_internal`;
- internal project/style markers in docs and tests;
- private workflow docs under `docs/hks/`;
- post-tag metadata drift after the latest release tag.

Current structured status:

```bash
python scripts/public_core_inventory.py --status --format markdown
python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
```

Expected current shape: public package distribution is allowed, repository
public release is blocked, and remaining repository blockers require explicit
confirmation before content is sanitized, moved, split, or version-bumped.

Record those confirmations in
[public-release-decision-record.md](./public-release-decision-record.md) before
changing repository visibility.

Before changing repository visibility to public, either remove/sanitize those
files or split a smaller public source repository from the private development
repository.

## Tracked files to reconsider before a public repo release

These files are useful for local agent/development operations but are not needed
by normal package users:

- `AGENTS.md`
- `Claude.md`
- `GEMINI.md`
- `SUB_AGENTS.md`
- `Research_Central_Architecture.md`
- `task.md`
- historical/private design docs under `docs/02-design/`, `docs/hks/`, and
  `docs/superpowers/`

Keep them private unless there is an explicit public-source release pass.

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
