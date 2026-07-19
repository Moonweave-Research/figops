# Public release clearance checklist

The local release docs record `figops` as the public PyPI package name,
`0.19.0` as the pinned PyPI install example, and `0.19.0` as the pinned
GitHub Release wheel/sdist example. Public package
distribution uses Apache-2.0, and future PyPI/TestPyPI uploads go through the
guarded technical checklist plus the manual Trusted Publishing workflow.

This checklist is intentionally conservative. It is not legal advice; it is the
release gate that keeps the project safe while ownership and publication rights
are confirmed.

## Current recommendation

If the code owner, advisor, and university policy all allow open-source release,
use **Apache-2.0** as the default license candidate.

Why Apache-2.0 is the best default for this project:

- It is permissive, so academic collaborators and industry users can adopt it
  without copyleft obligations.
- It preserves copyright notices and attribution.
- It includes an explicit patent grant, which is useful for research tooling that
  may evolve alongside publishable methods.
- It is widely recognized by PyPI, GitHub, companies, and universities.

LICENSE/NOTICE are Apache-2.0 for package distribution. The repository owner
has authorized the v0.20.0 public release, including merge, tag, GitHub
Release, TestPyPI, and PyPI publication. The authoritative evidence is the
[PR #224 owner authorization](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221).

Even when the generated status reports a green repository technical gate and
zero technical blockers, that machine result is evidence rather than
authorization to publish, merge, tag, or release. The authoritative
`public-core-inventory.json` now records owner authorization plus a validated
HTTPS evidence reference; the generated status reads only that inventory, not
this checklist or the decision-record Markdown. Re-run technical gates for the
exact release commit before each irreversible publication step.

Use [public-release-decision-record.md](./public-release-decision-record.md) as
the human-readable mirror of the recorded authorization and its release scope.

## Recorded human/legal/release approval

The repository owner recorded that the required human, legal, and release
approvals are granted for v0.20.0. Before each future release that is not
covered by that authorization, confirm these items again:

1. Who owns the code: you personally, the lab, the university, a grant-funded
   project, or a mixed set of contributors?
2. Does your advisor approve public release under the selected license?
3. Does university policy allow you, as a graduate student, to apply that license
   before graduation?
4. Are there any thesis, manuscript, patent, or unpublished-data restrictions?
5. Are all non-synthetic research markers, private style packs, and internal
   workflow docs excluded from the public candidate?
6. Are dependency licenses compatible with the selected license and PyPI use?
7. Which PyPI organization/user owns `figops`, and who are the maintainers?

## Technical release gates

Run these before upload approval:

```bash
python scripts/public_core_inventory.py --status --format markdown
python scripts/public_core_inventory.py --status --format markdown --output docs/packaging/public-release-status.md
python scripts/public_core_inventory.py --status --include-blockers
python hub_uv.py run --locked python scripts/check_public_release.py
python hub_uv.py build --no-sources
python hub_uv.py run --locked python scripts/package_metadata_smoke.py
python hub_uv.py run --locked python scripts/public_package_surface.py
python hub_uv.py run --locked python scripts/consumer_install_smoke.py
python hub_uv.py run --locked --with twine python -m twine check dist/*
```

Expected for a private-repo / public-PyPI path: `guarded_pypi_upload.py` can pass once license and built artifacts are clean, while `check_public_release.py` may still report repo-only private docs/tests that are not shipped in the wheel or sdist.

## Safe current distribution path

Use PyPI for normal installs:

```bash
APPROVED_VERSION=0.19.0  # replace with the approved release version
python -m pip install "figops==$APPROVED_VERSION"
figops-mcp --smoke
```

Use the locally documented GitHub Release asset when you need the exact attached
artifact:

```bash
APPROVED_VERSION=0.19.0  # replace with the approved GitHub Release version
gh release download "v$APPROVED_VERSION" --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install "dist-release/figops-$APPROVED_VERSION-py3-none-any.whl"
figops-mcp --smoke
```

The pinned examples are local documentation anchors: PyPI remains pinned to
`0.19.0`, and the GitHub Release asset is also pinned to `0.19.0`. Update either
only after explicit release-maintainer approval and public index/release-asset
verification.

## Future public-release PRs

For PyPI release PRs, keep the scope narrow:

1. Rebuild from a clean tree.
2. Make `scripts/guarded_pypi_upload.py --repository testpypi` pass in dry-run mode.
3. Smoke-test installed commands from the built wheel, including `figops --init`.
4. Publish to TestPyPI first through `.github/workflows/publish.yml` with `repository=testpypi`.
5. Install-check from TestPyPI before publishing the same version to PyPI through the same workflow with `repository=pypi`.
6. Install-check from public PyPI after the workflow succeeds.

Do not combine this with broad feature work. See `docs/packaging/trusted-publishing.md` for the exact PyPI/TestPyPI pending publisher values and workflow commands.
