# PyPI packaging readiness

FigOps now has enough Python packaging metadata to build a
wheel and source distribution for the current distribution name:

```bash
python -m build
# or
uv build
```

The install name from the current `pyproject.toml` is:

```bash
pip install figops
```

The installed console entry points are:

```bash
figops --help
figops-mcp --smoke
```

## Consumer install smoke

Before a package is shared outside the repository, build the wheel and run the
same console commands through an isolated consumer-style install path:

```bash
uv build
python scripts/consumer_install_smoke.py
```

This does not publish anything. It verifies that someone installing the built
wheel gets working `figops` and `figops-mcp` commands.


## Internal GitHub release distribution

Until the public license gate is resolved, the supported share path is a
GitHub release asset for people who already have repository access:

```bash
gh release download v0.17.1 --repo Moonweave-Research/figops --pattern '*.whl' --dir dist-release
python -m pip install dist-release/figops-0.17.1-py3-none-any.whl
figops-mcp --smoke
```

Maintainers should attach both built artifacts to each release and verify them:

```bash
gh release upload v0.17.1 dist/figops-0.17.1-py3-none-any.whl dist/figops-0.17.1.tar.gz
python scripts/github_release_asset_smoke.py
```

## Current distribution boundary

This repository is still private/internal. A GitHub release can be published for
internal FigOps use, but public PyPI upload is blocked until the distribution
policy changes.

Use the clearance checklist and structured blocker report before changing that
policy:

```bash
python scripts/public_core_inventory.py --status --include-blockers
```

See [public-release-clearance.md](./public-release-clearance.md) for the
license/IP approval checklist and the recommended Apache-2.0 path after
approval.

Before uploading to TestPyPI or PyPI, confirm all of the following:

1. LICENSE and NOTICE grant the intended public or source-available rights.
2. `scripts/check_public_release.py` passes for the release candidate.
3. The desired PyPI project name is final. The current candidate name is
   `figops`; changing away from it would create a new distribution identity.
4. `uv build` succeeds, `python scripts/package_metadata_smoke.py` validates the package metadata/console scripts, and `twine check dist/*` passes.
5. `python scripts/consumer_install_smoke.py` proves a consumer-style wheel install can run `figops --help` and `figops-mcp --smoke`.
6. The PyPI or TestPyPI account has a verified email address and a scoped API
   token for upload.

## Upload commands after policy approval

```bash
python - <<'PY'
import shutil
from pathlib import Path
shutil.rmtree(Path("dist"), ignore_errors=True)
PY
uv build
python scripts/package_metadata_smoke.py
python scripts/public_package_surface.py
python scripts/consumer_install_smoke.py
python scripts/github_release_asset_smoke.py
python scripts/guarded_pypi_upload.py --repository testpypi
python scripts/guarded_pypi_upload.py --repository testpypi --execute
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps figops==0.17.1
python scripts/guarded_pypi_upload.py --repository pypi
python scripts/guarded_pypi_upload.py --repository pypi --execute
```

The guarded uploader refuses to upload while `scripts/check_public_release.py`
is blocked. Do not bypass it from this private repository.
