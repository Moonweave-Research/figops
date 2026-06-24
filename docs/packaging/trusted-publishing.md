# Trusted Publishing runbook

FigOps publishes to TestPyPI/PyPI through GitHub Actions Trusted Publishing,
not long-lived PyPI API tokens. The workflow is manual-only so the maintainer
chooses when a build is promoted.

## Why this path

- No PyPI username, password, or API token is stored in GitHub secrets.
- Only the publishing jobs receive `id-token: write` permission.
- The build/test/package checks run before any upload job starts.
- TestPyPI and PyPI use separate GitHub environments and separate PyPI
  publisher registrations.

## One-time PyPI/TestPyPI setup

Create pending publishers in both package indexes before running the workflow.
Use these exact values:

| Index | Project name | Owner | Repository | Workflow | Environment |
| --- | --- | --- | --- | --- | --- |
| TestPyPI | `figops` | `Moonweave-Research` | `figops` | `publish.yml` | `testpypi` |
| PyPI | `figops` | `Moonweave-Research` | `figops` | `publish.yml` | `pypi` |

Account pages:

- PyPI: <https://pypi.org/manage/account/publishing/>
- TestPyPI: <https://test.pypi.org/manage/account/publishing/>

TestPyPI and PyPI are separate services. A maintainer may need to create and
verify accounts on both.

## Manual release sequence

Run TestPyPI first:

```bash
gh workflow run publish.yml --repo Moonweave-Research/figops --ref main -f repository=testpypi
gh run list --repo Moonweave-Research/figops --workflow publish.yml --limit 1
```

After the TestPyPI workflow succeeds, check installability from a fresh virtual
environment. The extra PyPI index lets normal dependencies resolve from PyPI
while the FigOps artifact comes from TestPyPI:

```bash
python -m venv /tmp/figops-testpypi-venv
/tmp/figops-testpypi-venv/bin/python -m pip install --upgrade pip
/tmp/figops-testpypi-venv/bin/python -m pip download --no-deps \
  --index-url https://test.pypi.org/simple/ \
  figops==0.17.3 \
  -d /tmp/figops-testpypi-dist
/tmp/figops-testpypi-venv/bin/python -m pip install /tmp/figops-testpypi-dist/figops-0.17.3-py3-none-any.whl
/tmp/figops-testpypi-venv/bin/figops --help
/tmp/figops-testpypi-venv/bin/figops-mcp --smoke
/tmp/figops-testpypi-venv/bin/figops --init --project /tmp/figops-testpypi-project
```

Promote the same version to PyPI only after the TestPyPI smoke passes:

```bash
gh workflow run publish.yml --repo Moonweave-Research/figops --ref main -f repository=pypi
gh run list --repo Moonweave-Research/figops --workflow publish.yml --limit 1
```

Then verify the public install path:

```bash
python -m venv /tmp/figops-pypi-venv
/tmp/figops-pypi-venv/bin/python -m pip install --upgrade pip
/tmp/figops-pypi-venv/bin/python -m pip install figops==0.17.3
/tmp/figops-pypi-venv/bin/figops --help
/tmp/figops-pypi-venv/bin/figops-mcp --smoke
/tmp/figops-pypi-venv/bin/figops --init --project /tmp/figops-pypi-project
```

## Safety notes

- Do not paste PyPI/TestPyPI API tokens into chat, issues, PRs, or workflow
  files. This release path does not need them.
- Keep GitHub environment protection on `pypi` if you want a final manual
  approval before production upload.
- PyPI versions are immutable. If `figops==0.17.3` is uploaded with a bad
  artifact, fix forward with a new version instead of trying to replace it.
