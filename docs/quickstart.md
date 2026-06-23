# Quickstart: Clone to First Figure

This path uses only the generic Graph Hub defaults: no GDrive prefetch, no Athena bridge,
and generic project conventions. It should take less than 10 minutes on a machine with
Python 3.12 and `uv`.

## 1. Clone and Install

```bash
git clone https://github.com/Moonweave-Research/graph-making-hub.git
cd graph-making-hub
uv sync
```

Graph Hub is not published to a package registry in this local public-core path;
run commands from the checked-out repository unless a future release note says otherwise.

If you are already in a clone, start with:

```bash
uv sync
```

## 2. Check the Environment

```bash
uv run python graphhub_mcp_server.py doctor
uv run python graphhub_mcp_server.py --smoke
```

`doctor` may report warnings for optional `[io]` dependencies or disabled write tools. That is
normal for a first local run. The quickstart script below enables write tools only inside the
local `GraphHubMCPServer` instance it creates.

## 3. Scaffold and Render a CSV Figure

Create a disposable quickstart script:

```bash
mkdir -p .graphhub-quickstart
cat > .graphhub-quickstart/quickstart_render.py <<'PY'
from pathlib import Path
import csv
import sys

repo = Path(__file__).resolve().parents[1]
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))

from hub_core.mcp import GraphHubMCPServer


def main() -> int:
    root = Path(__file__).resolve().parent
    runtime = root / "runtime"
    project = root / "first_figure_project"
    runtime.mkdir(parents=True, exist_ok=True)

    server = GraphHubMCPServer(
        research_root=root,
        runtime_root=runtime,
        write_tools_enabled=True,
    )

    scaffold = server.call_tool(
        "graphhub.scaffold_project",
        {
            "project_name": "first_figure_project",
            "project_root": str(project),
            "target_format": "nature",
            "template": "standard",
            "dry_run": False,
            "overwrite": True,
        },
    )["structuredContent"]
    print(f"scaffold: {scaffold['status']} {scaffold['config_path']}")

    data = root / "response.csv"
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time_s", "response_au"])
        writer.writeheader()
        writer.writerows(
            [
                {"time_s": 0, "response_au": 0.10},
                {"time_s": 1, "response_au": 0.42},
                {"time_s": 2, "response_au": 0.73},
                {"time_s": 3, "response_au": 0.91},
            ]
        )

    render = server.call_tool(
        "graphhub.render_csv_graph",
        {
            "data_path": str(data),
            "x_column": "time_s",
            "y_column": "response_au",
            "plot_type": "line",
            "target_format": "nature",
            "profile": "baseline",
            "output_format": "png",
            "job_id": "quickstart-response",
            "overwrite": True,
            "title": "Quickstart response",
            "x_axis_label": "Time (s)",
            "y_axis_label": "Response (a.u.)",
        },
    )["structuredContent"]
    print(f"render: {render['status']}")
    print(render["output_path"])
    return 0 if render["status"] in {"ok", "warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
PY
```

Run it:

```bash
uv run python .graphhub-quickstart/quickstart_render.py
```

Expected result:

```text
scaffold: ok .../first_figure_project/project_config.yaml
render: ok
# or: render: warning
.../runtime/mcp_jobs/quickstart-response/results/figures/graph.png
```

`render: warning` is a successful render: Graph Hub created the figure and attached a
quality/layout warning for manual review. Open the printed PNG path to inspect the output.

## 4. Learn the Examples

- [Synthetic project tutorial](../examples/synthetic_project/README.md): renders one configured
  project figure from a public-safe CSV fixture.
- [Multipanel project tutorial](../examples/multipanel_project/README.md): assembles a public-safe
  three-panel SVG fixture.
- [Materials/polymer domain helper recipe](../examples/materials_polymer_recipe/README.md): runs
  reusable signal-processing and resistivity analysis helpers through the data contract before
  rendering a figure.
- [Tool reference](tools.md): generated MCP tool schemas, plot types, semantic checks, and examples.
- [MCP setup](mcp_setup.md): stdio client snippets, write-tool policy, and allowed-root policy.
- [Onboarding path](onboarding.md): the recommended sequence for a new lab member.
