# Graph Hub MCP Tool Reference

This file is generated from the live Graph Hub MCP registries.
Regenerate it with:

```bash
uv run python scripts/gen_tool_reference.py --write
```

The freshness test fails if this committed file drifts from the registry output.

## Tools

### `graphhub.health`

Return Graph Hub server health and discovery status.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "discovery_status": {
      "type": "object"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "hub_path": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "python_executable": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "runtime_root": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_format_count": {
      "type": "integer"
    },
    "summary": {
      "type": "string"
    },
    "version": {
      "type": "string"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "write_tools_enabled": {
      "type": "boolean"
    }
  },
  "type": "object"
}
```

### `graphhub.describe`

Describe registered Graph Hub tools, plot types, semantic checks, and render examples.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {},
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "domain_helpers": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "plot_types": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "semantic_checks": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "tools": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.list_styles`

Return canonical Graph Hub target formats, output formats, profiles, and aliases.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {},
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "default_profile": {
      "type": "string"
    },
    "default_target_format": {
      "type": "string"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "output_formats": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "profile_aliases": {
      "type": "object"
    },
    "profiles": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_packs": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "summary": {
      "type": "string"
    },
    "target_formats": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.list_projects`

Discover Graph Hub project configs without executing scripts or writing files.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "include_ephemeral": {
      "default": false,
      "type": "boolean"
    },
    "include_invalid": {
      "default": true,
      "type": "boolean"
    },
    "include_quarantine": {
      "default": false,
      "type": "boolean"
    },
    "include_worktrees": {
      "default": false,
      "type": "boolean"
    },
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "projects": {
      "items": {
        "properties": {
          "classification": {
            "enum": [
              "ephemeral",
              "folder_role",
              "invalid",
              "legacy",
              "official",
              "quarantine",
              "unclassified"
            ],
            "type": "string"
          },
          "config_path": {
            "type": "string"
          },
          "declared_diagrams": {
            "type": "integer"
          },
          "declared_figures": {
            "type": "integer"
          },
          "errors": {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          "project_id": {
            "type": "string"
          },
          "project_root": {
            "type": "string"
          },
          "project_status": {
            "enum": [
              "active",
              "legacy"
            ],
            "type": "string"
          },
          "role": {
            "enum": [
              "archive",
              "docs",
              "exploratory",
              "master",
              "module",
              "raw_reservoir",
              "reference",
              "support",
              "theory",
              "unclassified"
            ],
            "type": "string"
          },
          "status": {
            "type": "string"
          },
          "target_format": {
            "type": "string"
          }
        },
        "type": "object"
      },
      "type": "array"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.inspect_project`

Summarize one project config without running analysis, plotting, or report writers.

**Input schema**

```json
{
  "additionalProperties": false,
  "oneOf": [
    {
      "required": [
        "project_id"
      ]
    },
    {
      "required": [
        "project_path"
      ]
    }
  ],
  "properties": {
    "include_naming_lint": {
      "default": false,
      "type": "boolean"
    },
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "project_id": {
      "description": "Discovered project ID; mutually exclusive with project_path, supply exactly one.",
      "type": "string"
    },
    "project_path": {
      "description": "Project path; mutually exclusive with project_id, supply exactly one.",
      "type": "string"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "canonical_docs_registry": {
      "type": "object"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "data_contract_summary": {
      "type": "object"
    },
    "diagram_outputs": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "experimental_conditions_summary": {
      "type": "object"
    },
    "failure_stage": {
      "type": "string"
    },
    "figure_outputs": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "figure_traceability_matrix": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "folder_role_summary": {
      "type": "object"
    },
    "folder_structure_status": {
      "type": "object"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "missing_inputs": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "missing_outputs": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "naming_lint": {
      "type": "object"
    },
    "normalization_needed": {
      "type": "boolean"
    },
    "operation_id": {
      "type": "string"
    },
    "pipeline_steps": {
      "type": "object"
    },
    "placeholder_report": {
      "type": "object"
    },
    "project_metadata": {
      "properties": {
        "config_path": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "project_root": {
          "type": "string"
        },
        "role": {
          "enum": [
            "master",
            "module"
          ],
          "type": "string"
        },
        "status": {
          "enum": [
            "active",
            "legacy"
          ],
          "type": "string"
        }
      },
      "type": "object"
    },
    "raw_integrity_status": {
      "type": "object"
    },
    "resolution_hint": {
      "type": "string"
    },
    "sample_registry_summary": {
      "type": "object"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_summary": {
      "type": "object"
    },
    "summary": {
      "type": "string"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.validate_project`

Run read-only config, data contract, style, and lockfile checks without executing scripts.

**Input schema**

```json
{
  "additionalProperties": false,
  "oneOf": [
    {
      "required": [
        "project_id"
      ]
    },
    {
      "required": [
        "project_path"
      ]
    }
  ],
  "properties": {
    "include_naming_lint": {
      "default": false,
      "type": "boolean"
    },
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "project_id": {
      "description": "Discovered project ID; mutually exclusive with project_path, supply exactly one.",
      "type": "string"
    },
    "project_path": {
      "description": "Project path; mutually exclusive with project_id, supply exactly one.",
      "type": "string"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    },
    "strict_lock": {
      "default": false,
      "type": "boolean"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "canonical_docs_registry": {
      "type": "object"
    },
    "config_errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "data_contract_errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "lockfile_status": {
      "type": "object"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "naming_lint": {
      "type": "object"
    },
    "operation_id": {
      "type": "string"
    },
    "placeholder_report": {
      "type": "object"
    },
    "project_status": {
      "enum": [
        "active",
        "legacy"
      ],
      "type": "string"
    },
    "raw_integrity_status": {
      "type": "object"
    },
    "recommended_next_action": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "summary": {
      "type": "string"
    },
    "valid": {
      "type": "boolean"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.render_csv_graph`

Render a CSV-backed graph in an isolated runtime-root MCP job workspace.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "aggregate": {
      "enum": [
        "mean",
        "median"
      ],
      "type": "string"
    },
    "annotate_values": {
      "default": false,
      "type": "boolean"
    },
    "bar_error_column": {
      "type": "string"
    },
    "baseline_path": {
      "description": "Optional baseline figure path to compare the rendered output against.",
      "type": "string"
    },
    "category_order": {
      "items": {
        "type": [
          "string",
          "number"
        ]
      },
      "type": "array"
    },
    "ci_band": {
      "type": "boolean"
    },
    "data_path": {
      "description": "CSV input path under an allowed data root.",
      "type": "string"
    },
    "dry_run": {
      "default": false,
      "type": "boolean"
    },
    "facet_column": {
      "type": "string"
    },
    "facet_ncols": {
      "minimum": 1,
      "type": "integer"
    },
    "facet_nrows": {
      "minimum": 1,
      "type": "integer"
    },
    "facet_order": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "facet_scales": {
      "default": "fixed",
      "enum": [
        "fixed",
        "free"
      ],
      "type": "string"
    },
    "fit_line": {
      "type": "boolean"
    },
    "job_id": {
      "description": "Stable render job ID; auto-generated when omitted.",
      "type": "string"
    },
    "output_format": {
      "default": "png",
      "enum": [
        "pdf",
        "png",
        "svg"
      ],
      "type": "string"
    },
    "overwrite": {
      "default": false,
      "type": "boolean"
    },
    "plot_type": {
      "default": "scatter",
      "enum": [
        "bar",
        "box",
        "facet",
        "heatmap",
        "line",
        "scatter",
        "violin",
        "xy"
      ],
      "type": "string"
    },
    "profile": {
      "default": "baseline",
      "enum": [
        "base",
        "baseline",
        "cell",
        "cell_press",
        "default",
        "premium",
        "resistance",
        "resistance_premium",
        "wiley"
      ],
      "type": "string"
    },
    "semantic_checks": {
      "description": "Optional per-column semantic constraints keyed by CSV column name.",
      "type": "object"
    },
    "significance_markers": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "target_format": {
      "default": "nature",
      "enum": [
        "acs",
        "cell",
        "default",
        "elsevier",
        "nature",
        "nature_surfur",
        "ppt",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    },
    "title": {
      "type": "string"
    },
    "x_axis_label": {
      "type": "string"
    },
    "x_column": {
      "type": "string"
    },
    "y_axis_label": {
      "type": "string"
    },
    "y_column": {
      "type": "string"
    },
    "z_column": {
      "type": "string"
    }
  },
  "required": [
    "data_path",
    "x_column",
    "y_column"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "artifact_status": {
      "type": "string"
    },
    "baseline_comparison": {
      "type": "object"
    },
    "calculation_checks": {
      "type": "object"
    },
    "config_path": {
      "type": "string"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "geometry_diagnostics": {
      "properties": {
        "checks": {
          "items": {
            "properties": {
              "data": {
                "type": "object"
              },
              "detail": {
                "type": "string"
              },
              "name": {
                "enum": [
                  "tick_label_overlaps",
                  "tick_label_crowding",
                  "artists_outside_axes",
                  "artists_outside_figure",
                  "legend_data_collision",
                  "axis_label_title_overlap",
                  "colorbar_overlap",
                  "blank_area_ratio",
                  "point_annotation_overlaps",
                  "artist_overlaps",
                  "legend_internal_overlaps",
                  "marker_marker_overlaps",
                  "text_axis_edge_proximity",
                  "legend_marker_consistency",
                  "label_offset_consistency",
                  "font_size_token_drift",
                  "journal_compliance"
                ],
                "type": "string"
              },
              "passed": {
                "type": [
                  "boolean",
                  "null"
                ]
              }
            },
            "required": [
              "name",
              "passed",
              "detail"
            ],
            "type": "object"
          },
          "type": "array"
        },
        "passed": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "schema_version": {
          "type": "string"
        },
        "warnings": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "passed",
        "checks",
        "warnings"
      ],
      "type": "object"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "job_id": {
      "type": "string"
    },
    "job_root": {
      "type": "string"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "layout_report": {
      "properties": {
        "clipped": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "density": {
          "type": "object"
        },
        "font_roles": {
          "type": "object"
        },
        "overlaps": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "passed": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "placement_consistency": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "render_errors": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "type": "string"
        },
        "warnings": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "passed",
        "overlaps",
        "clipped",
        "font_roles",
        "placement_consistency",
        "density",
        "render_errors",
        "warnings"
      ],
      "type": "object"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "output_path": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_summary": {
      "type": "object"
    },
    "summary": {
      "type": "string"
    },
    "visual_preflight_status": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.render_project_figure`

Render one configured project figure in an isolated runtime-root MCP job workspace.

**Input schema**

```json
{
  "additionalProperties": false,
  "oneOf": [
    {
      "required": [
        "project_id"
      ]
    },
    {
      "required": [
        "project_path"
      ]
    }
  ],
  "properties": {
    "baseline_path": {
      "description": "Optional baseline figure path to compare the rendered output against.",
      "type": "string"
    },
    "dry_run": {
      "default": false,
      "type": "boolean"
    },
    "figure_id": {
      "type": "string"
    },
    "figure_output": {
      "type": "string"
    },
    "job_id": {
      "description": "Stable render job ID; auto-generated when omitted.",
      "type": "string"
    },
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "output_format": {
      "enum": [
        "pdf",
        "png",
        "svg"
      ],
      "type": "string"
    },
    "overwrite": {
      "default": false,
      "type": "boolean"
    },
    "profile": {
      "enum": [
        "base",
        "baseline",
        "cell",
        "cell_press",
        "default",
        "premium",
        "resistance",
        "resistance_premium",
        "wiley"
      ],
      "type": "string"
    },
    "project_id": {
      "description": "Discovered project ID; mutually exclusive with project_path, supply exactly one.",
      "type": "string"
    },
    "project_path": {
      "description": "Project path; mutually exclusive with project_id, supply exactly one.",
      "type": "string"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    },
    "target_format": {
      "enum": [
        "acs",
        "cell",
        "default",
        "elsevier",
        "nature",
        "nature_surfur",
        "ppt",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "artifact_status": {
      "type": "string"
    },
    "baseline_comparison": {
      "type": "object"
    },
    "config_path": {
      "type": "string"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "figure_metadata": {
      "type": "object"
    },
    "geometry_diagnostics": {
      "properties": {
        "checks": {
          "items": {
            "properties": {
              "data": {
                "type": "object"
              },
              "detail": {
                "type": "string"
              },
              "name": {
                "enum": [
                  "tick_label_overlaps",
                  "tick_label_crowding",
                  "artists_outside_axes",
                  "artists_outside_figure",
                  "legend_data_collision",
                  "axis_label_title_overlap",
                  "colorbar_overlap",
                  "blank_area_ratio",
                  "point_annotation_overlaps",
                  "artist_overlaps",
                  "legend_internal_overlaps",
                  "marker_marker_overlaps",
                  "text_axis_edge_proximity",
                  "legend_marker_consistency",
                  "label_offset_consistency",
                  "font_size_token_drift",
                  "journal_compliance"
                ],
                "type": "string"
              },
              "passed": {
                "type": [
                  "boolean",
                  "null"
                ]
              }
            },
            "required": [
              "name",
              "passed",
              "detail"
            ],
            "type": "object"
          },
          "type": "array"
        },
        "passed": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "schema_version": {
          "type": "string"
        },
        "warnings": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "passed",
        "checks",
        "warnings"
      ],
      "type": "object"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "job_id": {
      "type": "string"
    },
    "job_root": {
      "type": "string"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "layout_report": {
      "properties": {
        "clipped": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "density": {
          "type": "object"
        },
        "font_roles": {
          "type": "object"
        },
        "overlaps": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "passed": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "placement_consistency": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "render_errors": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "type": "string"
        },
        "warnings": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "passed",
        "overlaps",
        "clipped",
        "font_roles",
        "placement_consistency",
        "density",
        "render_errors",
        "warnings"
      ],
      "type": "object"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "output_path": {
      "type": "string"
    },
    "project_id": {
      "type": "string"
    },
    "provenance": {
      "type": "object"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "selected_figure": {
      "type": "object"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "snapshot_project_path": {
      "type": "string"
    },
    "source_project_path": {
      "type": "string"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_summary": {
      "type": "object"
    },
    "summary": {
      "type": "string"
    },
    "visual_preflight_status": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.collect_artifacts`

Return artifact metadata for a completed MCP render job.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "baseline_path": {
      "description": "Optional baseline figure path to compare the rendered output against.",
      "type": "string"
    },
    "job_id": {
      "description": "Render job ID returned by a prior render call.",
      "type": "string"
    }
  },
  "required": [
    "job_id"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "artifact_status": {
      "type": "string"
    },
    "assemblies": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "baseline_comparison": {
      "type": "object"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "diagrams": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "figure_manifests": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "figure_metadata": {
      "type": "object"
    },
    "figures": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "job_id": {
      "type": "string"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "layout_report": {
      "properties": {
        "clipped": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "density": {
          "type": "object"
        },
        "font_roles": {
          "type": "object"
        },
        "overlaps": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "passed": {
          "type": [
            "boolean",
            "null"
          ]
        },
        "placement_consistency": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "render_errors": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "type": "string"
        },
        "warnings": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "passed",
        "overlaps",
        "clipped",
        "font_roles",
        "placement_consistency",
        "density",
        "render_errors",
        "warnings"
      ],
      "type": "object"
    },
    "logs": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "provenance": {
      "type": "object"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "visual_preflight_status": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.scaffold_project`

Plan or create a standard Graph Hub project scaffold.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "dry_run": {
      "default": true,
      "description": "Preview without writing files. Defaults True like normalize_project_structure and batch_check; the two render tools default dry_run False.",
      "type": "boolean"
    },
    "overwrite": {
      "default": false,
      "type": "boolean"
    },
    "project_name": {
      "type": "string"
    },
    "project_root": {
      "type": "string"
    },
    "target_format": {
      "default": "nature",
      "enum": [
        "acs",
        "cell",
        "default",
        "elsevier",
        "nature",
        "nature_surfur",
        "ppt",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    },
    "template": {
      "default": "standard",
      "enum": [
        "standard",
        "researchos"
      ],
      "type": "string"
    }
  },
  "required": [
    "project_name",
    "project_root"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "config_path": {
      "type": "string"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest": {
      "type": "object"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "planned_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "project_name": {
      "type": "string"
    },
    "project_root": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_summary": {
      "type": "object"
    },
    "summary": {
      "type": "string"
    },
    "validation": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.normalize_project_structure`

Plan or apply migration of an existing graph folder into standard Graph Hub structure.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "dry_run": {
      "default": true,
      "description": "Preview without writing files. Defaults True like scaffold_project and batch_check; the two render tools default dry_run False.",
      "type": "boolean"
    },
    "include_raw": {
      "default": false,
      "type": "boolean"
    },
    "move_policy": {
      "default": "copy",
      "enum": [
        "copy",
        "move",
        "symlink"
      ],
      "type": "string"
    },
    "overwrite": {
      "default": false,
      "type": "boolean"
    },
    "project_path": {
      "type": "string"
    }
  },
  "required": [
    "project_path"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "config_path": {
      "type": "string"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "manifest": {
      "type": "object"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "planned_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "project_root": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "style_summary": {
      "type": "object"
    },
    "summary": {
      "type": "string"
    },
    "validation": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `graphhub.batch_check`

Run a bounded project discovery and validation batch check with optional runtime manifest logging.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "batch_id": {
      "type": "string"
    },
    "dry_run": {
      "default": true,
      "type": "boolean"
    },
    "include_ephemeral": {
      "default": false,
      "type": "boolean"
    },
    "include_invalid": {
      "default": false,
      "type": "boolean"
    },
    "include_legacy": {
      "default": false,
      "type": "boolean"
    },
    "include_quarantine": {
      "default": false,
      "type": "boolean"
    },
    "include_worktrees": {
      "default": false,
      "type": "boolean"
    },
    "max_depth": {
      "default": 4,
      "maximum": 12,
      "minimum": 1,
      "type": "integer"
    },
    "max_projects": {
      "default": 20,
      "maximum": 50,
      "minimum": 1,
      "type": "integer"
    },
    "resume_manifest_path": {
      "type": "string"
    },
    "root": {
      "description": "Project scan root. Defaults to Graph Hub research root.",
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact_resources": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "batch_id": {
      "type": "string"
    },
    "batch_root": {
      "type": "string"
    },
    "checked_projects": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "created_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "error_category": {
      "enum": [
        "validation",
        "not_found",
        "internal",
        "disabled"
      ],
      "type": "string"
    },
    "error_code": {
      "type": "string"
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "failure_stage": {
      "type": "string"
    },
    "is_dry_run": {
      "type": "boolean"
    },
    "jsonrpc_code": {
      "type": "integer"
    },
    "latest_alias": {
      "type": "string"
    },
    "latest_dir": {
      "type": "string"
    },
    "log_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "manifest_path": {
      "type": "string"
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "modified_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "resolution_hint": {
      "type": "string"
    },
    "resumed_from": {
      "type": "string"
    },
    "script_output": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_paths": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "skipped_projects": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "status": {
      "enum": [
        "ok",
        "warning",
        "error"
      ],
      "type": "string"
    },
    "status_path": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "warnings": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

## Plot Types

### `bar`

**Capabilities**

```json
{
  "aggregate_methods": [
    "mean",
    "median"
  ],
  "supports_broken_axis": false,
  "supports_category_order": true,
  "supports_replicate_aggregation": true,
  "supports_series": true,
  "supports_single_series_error_column": true,
  "supports_yerr": true
}
```

**Argument schema**

```json
{
  "properties": {
    "aggregate": {
      "enum": [
        "mean",
        "median"
      ],
      "type": "string"
    },
    "bar_error_column": {
      "type": "string"
    },
    "category_order": {
      "items": {
        "type": [
          "string",
          "number"
        ]
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "aggregate": "mean",
    "bar_error_column": "sem",
    "category_order": [
      "day 0",
      "day 7",
      "day 14",
      "day 28"
    ],
    "data_path": "/path/to/data.csv",
    "job_id": "example-bar",
    "output_format": "png",
    "plot_type": "bar",
    "profile": "baseline",
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `box`

**Capabilities**

```json
{
  "shows_individual_points": true,
  "supports_broken_axis": false,
  "supports_category_order": true,
  "supports_series": false,
  "supports_yerr": false,
  "warns_small_n": true
}
```

**Argument schema**

```json
{
  "properties": {
    "category_order": {
      "items": {
        "type": [
          "string",
          "number"
        ]
      },
      "type": "array"
    },
    "x_column": {
      "type": "string"
    },
    "y_column": {
      "type": "string"
    }
  },
  "required": [
    "x_column",
    "y_column"
  ],
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "category_order": [
      "day 0",
      "day 7",
      "day 14",
      "day 28"
    ],
    "data_path": "/path/to/data.csv",
    "job_id": "example-box",
    "output_format": "png",
    "plot_type": "box",
    "profile": "baseline",
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `facet`

**Capabilities**

```json
{
  "base_plot_type": "line",
  "default_scales": "fixed",
  "free_scales": true,
  "shares_axes": true,
  "supports_broken_axis": false,
  "supports_facet_grid_shape": true,
  "supports_facet_order": true,
  "supports_faceting": true,
  "supports_series": true,
  "supports_yerr": true
}
```

**Argument schema**

```json
{
  "properties": {
    "facet_column": {
      "type": "string"
    },
    "facet_ncols": {
      "minimum": 1,
      "type": "integer"
    },
    "facet_nrows": {
      "minimum": 1,
      "type": "integer"
    },
    "facet_order": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "facet_scales": {
      "enum": [
        "fixed",
        "free"
      ],
      "type": "string"
    }
  },
  "required": [
    "facet_column"
  ],
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "data_path": "/path/to/data.csv",
    "facet_column": "facet",
    "facet_ncols": 2,
    "facet_order": [
      "control",
      "treated"
    ],
    "job_id": "example-facet",
    "output_format": "png",
    "plot_type": "facet",
    "profile": "baseline",
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `heatmap`

**Capabilities**

```json
{
  "supports_broken_axis": false,
  "supports_series": false,
  "supports_value_annotations": true,
  "supports_yerr": false,
  "supports_z": true
}
```

**Argument schema**

```json
{
  "properties": {
    "annotate_values": {
      "default": false,
      "type": "boolean"
    }
  },
  "required": [
    "z_column"
  ],
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "annotate_values": true,
    "data_path": "/path/to/data.csv",
    "job_id": "example-heatmap",
    "output_format": "png",
    "plot_type": "heatmap",
    "profile": "baseline",
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y",
    "z_column": "z"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `line`

**Capabilities**

```json
{
  "supports_broken_axis": true,
  "supports_ci_band": true,
  "supports_fit_line": true,
  "supports_series": true,
  "supports_significance_markers": true,
  "supports_statistical_overlays": true,
  "supports_yerr": true
}
```

**Argument schema**

```json
{
  "properties": {
    "ci_band": {
      "type": "boolean"
    },
    "fit_line": {
      "type": "boolean"
    },
    "significance_markers": {
      "type": "array"
    }
  },
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "ci_band": true,
    "data_path": "/path/to/data.csv",
    "fit_line": true,
    "job_id": "example-line",
    "output_format": "png",
    "plot_type": "line",
    "profile": "baseline",
    "significance_markers": [
      {
        "label": "p<0.05",
        "x1": 0,
        "x2": 1,
        "y": 2
      }
    ],
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `scatter`

**Capabilities**

```json
{
  "supports_broken_axis": true,
  "supports_ci_band": true,
  "supports_fit_line": true,
  "supports_series": true,
  "supports_significance_markers": true,
  "supports_statistical_overlays": true,
  "supports_yerr": true
}
```

**Argument schema**

```json
{
  "properties": {
    "ci_band": {
      "type": "boolean"
    },
    "fit_line": {
      "type": "boolean"
    },
    "significance_markers": {
      "type": "array"
    }
  },
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "ci_band": true,
    "data_path": "/path/to/data.csv",
    "fit_line": true,
    "job_id": "example-scatter",
    "output_format": "png",
    "plot_type": "scatter",
    "profile": "baseline",
    "significance_markers": [
      {
        "label": "p<0.05",
        "x1": 0,
        "x2": 1,
        "y": 2
      }
    ],
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `violin`

**Capabilities**

```json
{
  "falls_back_for_small_n": true,
  "shows_individual_points": true,
  "supports_broken_axis": false,
  "supports_category_order": true,
  "supports_series": false,
  "supports_yerr": false,
  "warns_small_n": true
}
```

**Argument schema**

```json
{
  "properties": {
    "category_order": {
      "items": {
        "type": [
          "string",
          "number"
        ]
      },
      "type": "array"
    },
    "x_column": {
      "type": "string"
    },
    "y_column": {
      "type": "string"
    }
  },
  "required": [
    "x_column",
    "y_column"
  ],
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "category_order": [
      "day 0",
      "day 7",
      "day 14",
      "day 28"
    ],
    "data_path": "/path/to/data.csv",
    "job_id": "example-violin",
    "output_format": "png",
    "plot_type": "violin",
    "profile": "baseline",
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

### `xy`

**Capabilities**

```json
{
  "supports_broken_axis": true,
  "supports_ci_band": true,
  "supports_fit_line": true,
  "supports_series": true,
  "supports_significance_markers": true,
  "supports_statistical_overlays": true,
  "supports_yerr": true
}
```

**Argument schema**

```json
{
  "properties": {
    "ci_band": {
      "type": "boolean"
    },
    "fit_line": {
      "type": "boolean"
    },
    "significance_markers": {
      "type": "array"
    }
  },
  "type": "object"
}
```

**Worked example**

```json
{
  "arguments": {
    "ci_band": true,
    "data_path": "/path/to/data.csv",
    "fit_line": true,
    "job_id": "example-xy",
    "output_format": "png",
    "plot_type": "xy",
    "profile": "baseline",
    "significance_markers": [
      {
        "label": "p<0.05",
        "x1": 0,
        "x2": 1,
        "y": 2
      }
    ],
    "target_format": "nature",
    "x_column": "x",
    "y_column": "y"
  },
  "tool": "graphhub.render_csv_graph"
}
```

## Semantic Checks

### `allow_null`

Require or allow null values in the target column.

**Schema**

```json
{
  "default": true,
  "type": "boolean"
}
```

**Example**

```json
{
  "y": {
    "allow_null": false
  }
}
```

### `axis_unit`

Validate that a configured axis unit conversion is compatible.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "current": {
    "axis_unit": {
      "data_unit": "mA",
      "display_unit": "A"
    }
  }
}
```

### `error_bar_source`

Declare and validate the source column used for error bars.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "mean": {
    "error_bar_source": {
      "column": "sem",
      "source": "sem"
    }
  }
}
```

### `expected_sample_count`

Require each configured group to have an exact or ranged expected count of non-null target values.

**Schema**

```json
{
  "oneOf": [
    {
      "required": [
        "count"
      ]
    },
    {
      "required": [
        "range"
      ]
    }
  ],
  "properties": {
    "count": {
      "minimum": 1,
      "type": "integer"
    },
    "group_by": {
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "type": "array"
    },
    "range": {
      "maxItems": 2,
      "minItems": 2,
      "prefixItems": [
        {
          "minimum": 1,
          "type": "integer"
        },
        {
          "minimum": 1,
          "type": "integer"
        }
      ],
      "type": "array"
    }
  },
  "required": [
    "group_by"
  ],
  "type": "object"
}
```

**Example**

```json
{
  "value": {
    "expected_sample_count": {
      "group_by": [
        "condition"
      ],
      "range": [
        3,
        5
      ]
    }
  }
}
```

### `grouped_cv`

Check coefficient of variation within configured groups.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "mean": {
    "grouped_cv": {
      "group_by": [
        "condition"
      ],
      "threshold": 0.15
    }
  }
}
```

### `linear_fit`

Validate a target column against an expected linear fit.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "y": {
    "linear_fit": {
      "intercept": 1.0,
      "slope": 2.0,
      "x_column": "x"
    }
  }
}
```

### `log_scale_positive`

Require positive values when the column will be plotted on a log scale.

**Schema**

```json
{
  "type": "boolean"
}
```

**Example**

```json
{
  "mean": {
    "log_scale_positive": true
  }
}
```

### `mean_sem`

Validate mean and SEM relationships from grouped replicate data.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "mean": {
    "mean_sem": {
      "group_by": [
        "condition"
      ],
      "sem_column": "sem"
    }
  }
}
```

### `min_replicates`

Require a minimum replicate count within groups.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "mean": {
    "min_replicates": {
      "group_by": [
        "condition"
      ],
      "n": 3
    }
  }
}
```

### `monotonic`

Require ordered values in the target column.

**Schema**

```json
{
  "enum": [
    "decreasing",
    "increasing",
    "nondecreasing",
    "nonincreasing"
  ],
  "type": "string"
}
```

**Example**

```json
{
  "time": {
    "monotonic": "increasing"
  }
}
```

### `monotonic_within_group`

Require ordered values in the target column within each configured group.

**Schema**

```json
{
  "properties": {
    "group_by": {
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "type": "array"
    },
    "mode": {
      "enum": [
        "decreasing",
        "increasing",
        "nondecreasing",
        "nonincreasing"
      ],
      "type": "string"
    }
  },
  "required": [
    "group_by",
    "mode"
  ],
  "type": "object"
}
```

**Example**

```json
{
  "time": {
    "monotonic_within_group": {
      "group_by": [
        "sample"
      ],
      "mode": "increasing"
    }
  }
}
```

### `outlier_flag`

Validate a boolean outlier flag column and maximum flagged fraction.

**Schema**

```json
{
  "type": "object"
}
```

**Example**

```json
{
  "y": {
    "outlier_flag": {
      "column": "outlier",
      "max_fraction": 0.25
    }
  }
}
```

### `range`

Require numeric values to fall within an inclusive [min, max] interval.

**Schema**

```json
{
  "maxItems": 2,
  "minItems": 2,
  "prefixItems": [
    {
      "type": "number"
    },
    {
      "type": "number"
    }
  ],
  "type": "array"
}
```

**Example**

```json
{
  "y": {
    "range": [
      0,
      1
    ]
  }
}
```

### `unique`

Require every value in the target column to be unique.

**Schema**

```json
{
  "type": "boolean"
}
```

**Example**

```json
{
  "sample_id": {
    "unique": true
  }
}
```

### `unit`

Validate actual_unit compatibility with an expected unit when Pint is installed.

**Schema**

```json
{
  "type": "string"
}
```

**Example**

```json
{
  "current": {
    "actual_unit": "mA",
    "unit": "A"
  }
}
```

### `unit_coherence`

Validate that declared related-column units combine to the target column's expected unit.

**Schema**

```json
{
  "properties": {
    "expected_unit": {
      "type": "string"
    },
    "terms": {
      "items": {
        "properties": {
          "column": {
            "type": "string"
          },
          "exponent": {
            "default": 1,
            "type": "integer"
          },
          "unit": {
            "type": "string"
          }
        },
        "required": [
          "column",
          "unit"
        ],
        "type": "object"
      },
      "minItems": 1,
      "type": "array"
    }
  },
  "required": [
    "expected_unit",
    "terms"
  ],
  "type": "object"
}
```

**Example**

```json
{
  "resistivity": {
    "unit_coherence": {
      "expected_unit": "ohm*cm",
      "terms": [
        {
          "column": "resistance",
          "unit": "ohm"
        },
        {
          "column": "area",
          "unit": "cm^2"
        },
        {
          "column": "thickness",
          "exponent": -1,
          "unit": "cm"
        }
      ]
    }
  }
}
```
