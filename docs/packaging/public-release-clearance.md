# Public release clearance checklist

FigOps can already be shared as a private GitHub Release wheel with people who
have repository access. Public PyPI is a separate legal and product decision.
Do not treat a passing build as permission to publish.

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

Do not switch LICENSE/NOTICE until release authority is confirmed.

## Required human approvals

Before any TestPyPI or PyPI upload, record answers for these items:

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
gh release download v0.17.2 --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install dist-release/figops-0.17.2-py3-none-any.whl
figops-mcp --smoke
```

## First public-release PR after approval

Once approvals are recorded, the first public-release PR should do only these
things:

1. Replace LICENSE/NOTICE with the approved license text and attribution.
2. Remove or split private style packs and private docs from the public release
   candidate.
3. Make `scripts/guarded_pypi_upload.py --repository testpypi` pass in dry-run mode.
4. Rebuild and smoke-test the wheel/sdist.
5. Publish to TestPyPI first through `scripts/guarded_pypi_upload.py`.

Do not combine this with broad feature work.
