# Baseline Receipt

Workflow: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

Date: 2026-06-29

## git_status

Command:

```powershell
git status --short --branch
```

Result: exit 0

```text
## main...origin/main
?? docs/specs/2026-06-29-figops-review-remediation-workflow.md
?? docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json
```

## available_python_env

Command:

```powershell
python hub_uv.py --print-env
```

Result: exit 0

```text
RESEARCH_HUB_RUNTIME_ROOT=C:\Users\...\AppData\Local\FigOps
UV_PROJECT_ENVIRONMENT=C:\Users\...\AppData\Local\FigOps\uv_envs\figops
UV_CACHE_DIR=C:\Users\...\AppData\Local\FigOps\uv_cache
```

Bare Python executable:

```text
C:\Users\...\AppData\Local\Programs\Python\Python312\python.exe
```

Bare Python is not usable for the repo test/runtime path because `yaml` and
`pytest` are not installed there.

External FigOps venv Python:

```text
C:\Users\최문영\AppData\Local\FigOps\uv_envs\figops\Scripts\python.exe
```

External FigOps venv dependency probe: exit 0

```text
yaml 6.0.3
pytest 9.0.3
```

## blocked_commands

Command:

```powershell
python hub_uv.py run python orchestrator.py --list-projects
```

Result: exit 1

```text
Error: `uv` was not found on PATH. Install uv, then rerun this command, or use a Python environment with the FigOps dev dependencies installed.
```

Command:

```powershell
python -m pytest tests/test_runtime_paths.py tests/test_smoke.py -q
```

Result: exit 1

```text
No module named pytest
```

Command:

```powershell
python -c "import yaml"
```

Result: exit 1

```text
ModuleNotFoundError: No module named 'yaml'
```

Command:

```powershell
uv --version
```

Result: exit 1

```text
The term 'uv' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

No dependency installation was performed.

## r_runtime_status

Command:

```powershell
Rscript --version
```

Result: exit 1

```text
The term 'Rscript' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

R-dependent smoke coverage is expected to skip in this environment.

## initial_test_slice

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B orchestrator.py --list-projects
```

Result: exit 0

Summary: 3 valid example projects found; all currently report missing figures.

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B figops_mcp_server.py --smoke
```

Result: exit 0

```json
{"health_status": "ok", "status": "ok", "style_format_count": 10, "tool_surface": "figops_mcp"}
```

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_runtime_paths.py tests/test_uv_runtime.py tests/test_smoke.py -q -rs -p no:cacheprovider
```

Result: exit 0

```text
14 passed, 1 skipped in 0.42s
SKIPPED tests\test_smoke.py:33: R runtime + readr package required for full scaffold analysis step
```

Command:

```powershell
$p = Join-Path $env:LOCALAPPDATA 'FigOps/uv_envs/figops/Scripts/python.exe'
& $p -B -m pytest tests/test_mcp_rendering.py tests/test_journal_theme_layout.py -q -p no:cacheprovider
```

Result: exit 0

```text
167 passed, 2 skipped, 8 subtests passed in 74.09s (0:01:14)
```

## notes

- This baseline used the existing external FigOps venv and did not install or
  modify dependencies.
- The preferred `hub_uv.py run ...` path remains blocked until `uv` is available
  on PATH or an equivalent launcher change is made.
