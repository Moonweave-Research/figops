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

The GitHub release asset remains the supported pre-PyPI sharing path:

```bash
gh release download v0.17.3 --repo Moonweave-Research/figops --pattern '*.whl' --dir dist-release
python -m pip install dist-release/figops-0.17.3-py3-none-any.whl
figops-mcp --smoke
```

Maintainers should attach both built artifacts to each release and verify them:

```bash
gh release upload v0.17.3 dist/figops-0.17.3-py3-none-any.whl dist/figops-0.17.3.tar.gz
python scripts/github_release_asset_smoke.py
```

## Current distribution boundary

This repository can remain private/internal while the built FigOps wheel/sdist are distributed publicly under Apache-2.0. The full repository release gate may still report repo-only private docs/tests/internal style packs that are not shipped in the package artifacts.

Use the clearance checklist and structured blocker report before making the full repository public:

```bash
python scripts/public_core_inventory.py --status --include-blockers
```

See [public-release-clearance.md](./public-release-clearance.md) for the
license/IP approval checklist and the recommended Apache-2.0 path after
approval.

Before uploading to TestPyPI or PyPI, confirm all of the following:

1. LICENSE and NOTICE grant Apache-2.0 package distribution rights.
2. `python scripts/guarded_pypi_upload.py --repository testpypi` prints an upload command after package-artifact checks pass.
3. `scripts/check_public_release.py` is either passing for a public repository release, or its remaining blockers are confirmed to be private repo-only files excluded from the built wheel/sdist.
4. The desired PyPI project name is final. The current candidate name is
   `figops`; changing away from it would create a new distribution identity.
5. `uv build` succeeds, `python scripts/package_metadata_smoke.py` validates the package metadata/console scripts, and `twine check dist/*` passes.
6. `python scripts/consumer_install_smoke.py` proves a consumer-style wheel install can run `figops --help` and `figops-mcp --smoke`.
7. The PyPI or TestPyPI account has a verified email address and either Trusted Publishing or a scoped API token for upload.

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
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps figops==0.17.3
python scripts/guarded_pypi_upload.py --repository pypi
python scripts/guarded_pypi_upload.py --repository pypi --execute
```

The guarded uploader refuses to upload when distribution policy, license files, built artifacts, or package-surface scans are blocked. Do not bypass it from this repository.
