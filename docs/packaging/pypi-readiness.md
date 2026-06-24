# PyPI packaging readiness

Graph Making Hub / FigOps now has enough Python packaging metadata to build a
wheel and source distribution for the current distribution name:

```bash
python -m build
# or
uv build
```

The install name from the current `pyproject.toml` is:

```bash
pip install graph-making-hub
```

The installed console entry points are:

```bash
graphhub --help
graphhub-mcp --smoke
```

## Current distribution boundary

This repository is still private/internal. A GitHub release can be published for
internal FigOps use, but public PyPI upload is blocked until the distribution
policy changes.

Before uploading to TestPyPI or PyPI, confirm all of the following:

1. LICENSE and NOTICE grant the intended public or source-available rights.
2. `scripts/check_public_release.py` passes for the release candidate.
3. The desired PyPI project name is final. The current name is
   `graph-making-hub`; changing it to `figops` is a separate distribution
   identity decision.
4. `uv build` succeeds and `twine check dist/*` passes.
5. A clean environment can install the wheel and run `graphhub-mcp --smoke`.
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
python scripts/guarded_pypi_upload.py --repository testpypi
python scripts/guarded_pypi_upload.py --repository testpypi --execute
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps graph-making-hub==0.16.5
python scripts/guarded_pypi_upload.py --repository pypi
python scripts/guarded_pypi_upload.py --repository pypi --execute
```

The guarded uploader refuses to upload while `scripts/check_public_release.py`
is blocked. Do not bypass it from this private repository.
