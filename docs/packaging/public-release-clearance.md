# Public release clearance checklist

FigOps can already be shared as a GitHub Release wheel with people who have repository access. Public package distribution now uses Apache-2.0, and PyPI/TestPyPI uploads go through the guarded technical checklist plus the manual Trusted Publishing workflow.

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

LICENSE/NOTICE are now Apache-2.0 for package distribution. Keep the full repository private until repo-only private markers, docs, and internal style packs are intentionally separated or cleared.

## Required human approvals

Before any TestPyPI or PyPI upload, confirm these items:

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
python scripts/public_core_inventory.py --status --include-blockers
python scripts/check_public_release.py
uv build
python scripts/package_metadata_smoke.py
python scripts/public_package_surface.py
python scripts/consumer_install_smoke.py
uv run --with twine python -m twine check dist/*
```

Expected for a private-repo / public-PyPI path: `guarded_pypi_upload.py` can pass once license and built artifacts are clean, while `check_public_release.py` may still report repo-only private docs/tests that are not shipped in the wheel or sdist.

## Safe current distribution path

For now, use GitHub Release assets only:

```bash
gh release download v0.17.3 --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install dist-release/figops-0.17.3-py3-none-any.whl
figops-mcp --smoke
```

## First public-release PR after approval

For PyPI release PRs, keep the scope narrow:

1. Rebuild from a clean tree.
2. Make `scripts/guarded_pypi_upload.py --repository testpypi` pass in dry-run mode.
3. Smoke-test installed commands from the built wheel, including `figops --init`.
4. Publish to TestPyPI first through `.github/workflows/publish.yml` with `repository=testpypi`.
5. Install-check from TestPyPI before publishing the same version to PyPI through the same workflow with `repository=pypi`.

Do not combine this with broad feature work. See `docs/packaging/trusted-publishing.md` for the exact PyPI/TestPyPI pending publisher values and workflow commands.
