# FigOps MCP Tool Reference — compatibility profile

This file is generated from the live FigOps MCP registries.
Regenerate it with:

```bash
python hub_uv.py run python scripts/gen_tool_reference.py --write --profile compatibility
```

The freshness test fails if this committed file drifts from the registry output.

## Tools

### `figops.health`

Return FigOps server health and discovery status.

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
      "description": "Project scan root. Defaults to FigOps research root.",
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
    "exposed_tool_count": {
      "type": "integer"
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
    "preview_worker_limits": {
      "additionalProperties": false,
      "properties": {
        "base64_output_byte_limit": {
          "type": "integer"
        },
        "cpu_limit_enforced": {
          "type": "boolean"
        },
        "edge_limit": {
          "type": "integer"
        },
        "file_size_limit_enforced": {
          "type": "boolean"
        },
        "memory_limit_bytes": {
          "type": "integer"
        },
        "memory_limit_enforced": {
          "type": "boolean"
        },
        "memory_limit_limitation": {
          "type": [
            "string",
            "null"
          ]
        },
        "pixel_limit": {
          "type": "integer"
        },
        "process_tree_containment": {
          "type": "boolean"
        },
        "raw_output_byte_limit": {
          "type": "integer"
        },
        "source_byte_limit": {
          "type": "integer"
        },
        "timeout_seconds": {
          "type": "number"
        }
      },
      "type": "object"
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
    "surface_profile": {
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

### `figops.describe`

Describe registered FigOps tools, plot types, semantic checks, and render examples.

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

### `figops.list_styles`

Return canonical FigOps target formats, output formats, profiles, and aliases.

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

### `figops.list_projects`

Discover FigOps project configs without executing scripts or writing files.

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
      "description": "Project scan root. Defaults to FigOps research root.",
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

### `figops.inspect_project`

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
      "description": "Project scan root. Defaults to FigOps research root.",
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
    "structure_audit": {
      "additionalProperties": false,
      "properties": {
        "findings": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "graph": {
          "type": "object"
        },
        "proposed_changes": {
          "items": {
            "type": "object"
          },
          "type": "array"
        },
        "roles": {
          "type": "object"
        },
        "schema_version": {
          "type": "string"
        },
        "status_code": {
          "type": "string"
        },
        "unknowns": {
          "items": {
            "type": "object"
          },
          "type": "array"
        }
      },
      "required": [
        "schema_version",
        "status_code",
        "roles",
        "graph",
        "findings",
        "unknowns",
        "proposed_changes"
      ],
      "type": "object"
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

### `figops.validate_project`

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
      "description": "Project scan root. Defaults to FigOps research root.",
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

### `figops.render_csv_graph`

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
    "annotations": {
      "description": "Point text/callout annotations plus rectangular region, hspan, and vspan overlays.",
      "items": {
        "anyOf": [
          {
            "additionalProperties": false,
            "properties": {
              "analysis_artifact_sha256": {
                "pattern": "^[0-9a-fA-F]{64}$",
                "type": "string"
              },
              "annotation_kind": {
                "default": "auto",
                "enum": [
                  "auto",
                  "literal",
                  "statistical_claim"
                ],
                "type": "string"
              },
              "arrow_to": {
                "properties": {
                  "x": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "y": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "x",
                  "y"
                ],
                "type": "object"
              },
              "arrowstyle": {
                "default": "->",
                "type": "string"
              },
              "avoid_overlap": {
                "default": false,
                "type": "boolean"
              },
              "calculation_evidence_id": {
                "minLength": 1,
                "type": "string"
              },
              "color": {
                "default": "black",
                "type": "string"
              },
              "connectionstyle": {
                "type": "string"
              },
              "placement_preset": {
                "enum": [
                  "above",
                  "below",
                  "left",
                  "right",
                  "upper_left",
                  "upper_right",
                  "lower_left",
                  "lower_right"
                ],
                "type": "string"
              },
              "test_metadata": {
                "additionalProperties": false,
                "properties": {
                  "model": {
                    "minLength": 1,
                    "type": "string"
                  },
                  "test_name": {
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "test_name",
                  "model"
                ],
                "type": "object"
              },
              "text": {
                "type": "string"
              },
              "x": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "xytext_offset": {
                "properties": {
                  "dx": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "dy": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "dx",
                  "dy"
                ],
                "type": "object"
              },
              "y": {
                "type": [
                  "number",
                  "string"
                ]
              }
            },
            "required": [
              "x",
              "y",
              "text"
            ],
            "type": "object"
          },
          {
            "additionalProperties": false,
            "properties": {
              "analysis_artifact_sha256": {
                "pattern": "^[0-9a-fA-F]{64}$",
                "type": "string"
              },
              "annotation_kind": {
                "default": "auto",
                "enum": [
                  "auto",
                  "literal",
                  "statistical_claim"
                ],
                "type": "string"
              },
              "arrow_to": {
                "properties": {
                  "x": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "y": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "x",
                  "y"
                ],
                "type": "object"
              },
              "arrowstyle": {
                "default": "->",
                "type": "string"
              },
              "avoid_overlap": {
                "default": false,
                "type": "boolean"
              },
              "calculation_evidence_id": {
                "minLength": 1,
                "type": "string"
              },
              "color": {
                "default": "black",
                "type": "string"
              },
              "connectionstyle": {
                "type": "string"
              },
              "placement_preset": {
                "enum": [
                  "above",
                  "below",
                  "left",
                  "right",
                  "upper_left",
                  "upper_right",
                  "lower_left",
                  "lower_right"
                ],
                "type": "string"
              },
              "test_metadata": {
                "additionalProperties": false,
                "properties": {
                  "model": {
                    "minLength": 1,
                    "type": "string"
                  },
                  "test_name": {
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "test_name",
                  "model"
                ],
                "type": "object"
              },
              "text": {
                "type": "string"
              },
              "x": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "xytext_offset": {
                "properties": {
                  "dx": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "dy": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "dx",
                  "dy"
                ],
                "type": "object"
              },
              "y": {
                "type": [
                  "number",
                  "string"
                ]
              }
            },
            "required": [
              "x",
              "y",
              "arrow_to"
            ],
            "type": "object"
          },
          {
            "additionalProperties": false,
            "properties": {
              "alpha": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "analysis_artifact_sha256": {
                "pattern": "^[0-9a-fA-F]{64}$",
                "type": "string"
              },
              "annotation_kind": {
                "default": "auto",
                "enum": [
                  "auto",
                  "literal",
                  "statistical_claim"
                ],
                "type": "string"
              },
              "calculation_evidence_id": {
                "minLength": 1,
                "type": "string"
              },
              "color": {
                "default": "black",
                "type": "string"
              },
              "region": {
                "properties": {
                  "xmax": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "xmin": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "ymax": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "ymin": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "xmin",
                  "xmax",
                  "ymin",
                  "ymax"
                ],
                "type": "object"
              },
              "test_metadata": {
                "additionalProperties": false,
                "properties": {
                  "model": {
                    "minLength": 1,
                    "type": "string"
                  },
                  "test_name": {
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "test_name",
                  "model"
                ],
                "type": "object"
              },
              "text": {
                "type": "string"
              }
            },
            "required": [
              "region"
            ],
            "type": "object"
          },
          {
            "additionalProperties": false,
            "properties": {
              "alpha": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "analysis_artifact_sha256": {
                "pattern": "^[0-9a-fA-F]{64}$",
                "type": "string"
              },
              "annotation_kind": {
                "default": "auto",
                "enum": [
                  "auto",
                  "literal",
                  "statistical_claim"
                ],
                "type": "string"
              },
              "calculation_evidence_id": {
                "minLength": 1,
                "type": "string"
              },
              "color": {
                "default": "black",
                "type": "string"
              },
              "hspan": {
                "properties": {
                  "ymax": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "ymin": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "ymin",
                  "ymax"
                ],
                "type": "object"
              },
              "test_metadata": {
                "additionalProperties": false,
                "properties": {
                  "model": {
                    "minLength": 1,
                    "type": "string"
                  },
                  "test_name": {
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "test_name",
                  "model"
                ],
                "type": "object"
              },
              "text": {
                "type": "string"
              }
            },
            "required": [
              "hspan"
            ],
            "type": "object"
          },
          {
            "additionalProperties": false,
            "properties": {
              "alpha": {
                "type": [
                  "number",
                  "string"
                ]
              },
              "analysis_artifact_sha256": {
                "pattern": "^[0-9a-fA-F]{64}$",
                "type": "string"
              },
              "annotation_kind": {
                "default": "auto",
                "enum": [
                  "auto",
                  "literal",
                  "statistical_claim"
                ],
                "type": "string"
              },
              "calculation_evidence_id": {
                "minLength": 1,
                "type": "string"
              },
              "color": {
                "default": "black",
                "type": "string"
              },
              "test_metadata": {
                "additionalProperties": false,
                "properties": {
                  "model": {
                    "minLength": 1,
                    "type": "string"
                  },
                  "test_name": {
                    "minLength": 1,
                    "type": "string"
                  }
                },
                "required": [
                  "test_name",
                  "model"
                ],
                "type": "object"
              },
              "text": {
                "type": "string"
              },
              "vspan": {
                "properties": {
                  "xmax": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "xmin": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "xmin",
                  "xmax"
                ],
                "type": "object"
              }
            },
            "required": [
              "vspan"
            ],
            "type": "object"
          }
        ]
      },
      "type": "array"
    },
    "axis_limits": {
      "additionalProperties": false,
      "properties": {
        "x": {
          "additionalProperties": false,
          "properties": {
            "max": {
              "type": "number"
            },
            "min": {
              "type": "number"
            }
          },
          "type": "object"
        },
        "y": {
          "additionalProperties": false,
          "properties": {
            "max": {
              "type": "number"
            },
            "min": {
              "type": "number"
            }
          },
          "type": "object"
        }
      },
      "type": "object"
    },
    "bar_error_column": {
      "type": "string"
    },
    "baseline_path": {
      "description": "Optional baseline figure path to compare the rendered output against.",
      "type": "string"
    },
    "calculation_evidence_path": {
      "description": "CSV input path under an allowed data root.",
      "type": "string"
    },
    "calculation_evidence_paths": {
      "items": {
        "description": "CSV input path under an allowed data root.",
        "type": "string"
      },
      "maxItems": 32,
      "type": "array"
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
    "compliance_mode": {
      "default": "validate",
      "enum": [
        "validate",
        "clamp"
      ],
      "type": "string"
    },
    "data_path": {
      "description": "CSV input path under an allowed data root.",
      "type": "string"
    },
    "declutter_mode": {
      "default": "none",
      "enum": [
        "none",
        "declutter"
      ],
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
    "fill_between": {
      "description": "Manual filled bands from point triplets or CSV x/y1/y2 columns.",
      "items": {
        "additionalProperties": false,
        "anyOf": [
          {
            "required": [
              "points"
            ]
          },
          {
            "required": [
              "x_column",
              "y1_column",
              "y2_column"
            ]
          }
        ],
        "properties": {
          "alpha": {
            "default": 0.2,
            "type": [
              "number",
              "string"
            ]
          },
          "band_kind": {
            "enum": [
              "literal",
              "confidence_interval"
            ],
            "type": "string"
          },
          "color": {
            "type": "string"
          },
          "label": {
            "type": "string"
          },
          "points": {
            "items": {
              "properties": {
                "x": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "y1": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "y2": {
                  "type": [
                    "number",
                    "string"
                  ]
                }
              },
              "required": [
                "x",
                "y1",
                "y2"
              ],
              "type": "object"
            },
            "minItems": 2,
            "type": "array"
          },
          "x_column": {
            "type": "string"
          },
          "y1_column": {
            "type": "string"
          },
          "y2_column": {
            "type": "string"
          },
          "zorder": {
            "type": [
              "number",
              "string"
            ]
          }
        },
        "type": "object"
      },
      "type": "array"
    },
    "fit_line": {
      "type": "boolean"
    },
    "fit_options": {
      "additionalProperties": false,
      "properties": {
        "ci_alpha": {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        "ci_label": {
          "type": "string"
        },
        "color": {
          "type": "string"
        },
        "label": {
          "type": "string"
        },
        "linestyle": {
          "type": "string"
        },
        "linewidth": {
          "exclusiveMinimum": 0,
          "type": "number"
        },
        "model": {
          "default": "linear",
          "enum": [
            "linear"
          ],
          "type": "string"
        },
        "zorder": {
          "type": "number"
        }
      },
      "type": "object"
    },
    "guide_curves": {
      "description": "Manual guide curves from point objects or parallel x/y arrays.",
      "items": {
        "anyOf": [
          {
            "required": [
              "points"
            ]
          },
          {
            "required": [
              "x",
              "y"
            ]
          }
        ],
        "properties": {
          "color": {
            "default": "black",
            "type": "string"
          },
          "label": {
            "type": "string"
          },
          "linestyle": {
            "type": "string"
          },
          "linewidth": {
            "type": [
              "number",
              "string"
            ]
          },
          "points": {
            "items": {
              "properties": {
                "x": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "y": {
                  "type": [
                    "number",
                    "string"
                  ]
                }
              },
              "required": [
                "x",
                "y"
              ],
              "type": "object"
            },
            "minItems": 2,
            "type": "array"
          },
          "x": {
            "items": {
              "type": [
                "number",
                "string"
              ]
            },
            "minItems": 2,
            "type": "array"
          },
          "y": {
            "items": {
              "type": [
                "number",
                "string"
              ]
            },
            "minItems": 2,
            "type": "array"
          },
          "zorder": {
            "type": [
              "number",
              "string"
            ]
          }
        },
        "type": "object"
      },
      "type": "array"
    },
    "job_id": {
      "description": "Stable render job ID; auto-generated when omitted.",
      "type": "string"
    },
    "label_column": {
      "type": "string"
    },
    "label_map": {
      "additionalProperties": {
        "type": "string"
      },
      "type": "object"
    },
    "label_transform": {
      "default": "raw",
      "enum": [
        "raw",
        "legacy_compress"
      ],
      "type": "string"
    },
    "legend_layout": {
      "default": "auto",
      "enum": [
        "auto",
        "smart",
        "standard",
        "best",
        "top_outside",
        "right_outside"
      ],
      "type": "string"
    },
    "legend_options": {
      "additionalProperties": false,
      "properties": {
        "ncol": {
          "maximum": 8,
          "minimum": 1,
          "type": "integer"
        },
        "order": {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        "title": {
          "type": "string"
        }
      },
      "type": "object"
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
    "point_label_options": {
      "additionalProperties": false,
      "properties": {
        "fanout": {
          "default": "none",
          "enum": [
            "none",
            "compass"
          ],
          "type": "string"
        },
        "max_labels": {
          "minimum": 1,
          "type": "integer"
        },
        "offset": {
          "properties": {
            "dx": {
              "type": [
                "number",
                "string"
              ]
            },
            "dy": {
              "type": [
                "number",
                "string"
              ]
            }
          },
          "required": [
            "dx",
            "dy"
          ],
          "type": "object"
        },
        "priority_column": {
          "type": "string"
        },
        "skip_column": {
          "type": "string"
        }
      },
      "type": "object"
    },
    "profile": {
      "default": "baseline",
      "enum": [
        "base",
        "baseline",
        "cell",
        "cell_press",
        "default",
        "publication",
        "wiley"
      ],
      "type": "string"
    },
    "secondary_y": {
      "additionalProperties": false,
      "properties": {
        "axis_label": {
          "type": "string"
        },
        "column": {
          "type": "string"
        },
        "enabled": {
          "default": true,
          "type": "boolean"
        },
        "limits": {
          "additionalProperties": false,
          "properties": {
            "max": {
              "type": [
                "number",
                "string"
              ]
            },
            "min": {
              "type": [
                "number",
                "string"
              ]
            }
          },
          "type": "object"
        },
        "scale": {
          "default": "linear",
          "enum": [
            "linear",
            "log"
          ],
          "type": "string"
        },
        "series_label": {
          "type": "string"
        }
      },
      "type": "object"
    },
    "semantic_checks": {
      "description": "Optional per-column semantic constraints keyed by CSV column name.",
      "type": "object"
    },
    "series_column": {
      "type": "string"
    },
    "series_styles": {
      "additionalProperties": {
        "additionalProperties": false,
        "properties": {
          "alpha": {
            "type": [
              "number",
              "string"
            ]
          },
          "color": {
            "type": "string"
          },
          "edgecolor": {
            "type": "string"
          },
          "facecolor": {
            "type": "string"
          },
          "fill": {
            "enum": [
              "full",
              "filled",
              "none",
              "open"
            ],
            "type": "string"
          },
          "hatch": {
            "type": "string"
          },
          "label": {
            "type": "string"
          },
          "linestyle": {
            "type": "string"
          },
          "linewidth": {
            "type": [
              "number",
              "string"
            ]
          },
          "marker": {
            "type": "string"
          },
          "markeredgecolor": {
            "type": "string"
          },
          "markerfacecolor": {
            "type": "string"
          },
          "size": {
            "type": [
              "number",
              "string"
            ]
          },
          "zorder": {
            "type": [
              "number",
              "string"
            ]
          }
        },
        "type": "object"
      },
      "description": "Per-series style overrides keyed by exact series label.",
      "type": "object"
    },
    "significance_markers": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "analysis_artifact_sha256": {
            "pattern": "^[0-9a-fA-F]{64}$",
            "type": "string"
          },
          "calculation_evidence_id": {
            "minLength": 1,
            "type": "string"
          },
          "color": {
            "type": "string"
          },
          "h": {
            "type": "number"
          },
          "label": {
            "type": "string"
          },
          "test_metadata": {
            "additionalProperties": false,
            "properties": {
              "model": {
                "minLength": 1,
                "type": "string"
              },
              "test_name": {
                "minLength": 1,
                "type": "string"
              }
            },
            "required": [
              "test_name",
              "model"
            ],
            "type": "object"
          },
          "x1": {
            "type": "number"
          },
          "x2": {
            "type": "number"
          },
          "y": {
            "type": "number"
          }
        },
        "required": [
          "x1",
          "x2",
          "y",
          "label",
          "calculation_evidence_id",
          "analysis_artifact_sha256",
          "test_metadata"
        ],
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
        "neutral",
        "ppt",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    },
    "tick_style": {
      "additionalProperties": false,
      "properties": {
        "format": {
          "enum": [
            "default",
            "plain",
            "scientific",
            "compact"
          ],
          "type": "string"
        },
        "max_label_chars": {
          "minimum": 4,
          "type": "integer"
        },
        "rotation": {
          "type": "number"
        }
      },
      "type": "object"
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
    "x_scale": {
      "default": "linear",
      "enum": [
        "linear",
        "log"
      ],
      "type": "string"
    },
    "y_axis_label": {
      "type": "string"
    },
    "y_column": {
      "type": "string"
    },
    "y_scale": {
      "default": "linear",
      "enum": [
        "linear",
        "log"
      ],
      "type": "string"
    },
    "yerr_cap_width": {
      "default": 3.0,
      "minimum": 0,
      "type": "number"
    },
    "yerr_column": {
      "type": "string"
    },
    "yerr_minus_column": {
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
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/artifacts/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
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
    "calculation_evidence": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "claim_candidates": {
      "items": {
        "type": "object"
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
    "descriptive_overlays": {
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
    "evidence": {
      "type": "object"
    },
    "failure_stage": {
      "type": "string"
    },
    "geometry_diagnostics": {
      "additionalProperties": false,
      "properties": {
        "measurements": {
          "items": {
            "additionalProperties": false,
            "allOf": [
              {
                "else": {
                  "not": {
                    "required": [
                      "value"
                    ]
                  },
                  "required": [
                    "reason"
                  ]
                },
                "if": {
                  "properties": {
                    "availability": {
                      "const": "available"
                    }
                  }
                },
                "then": {
                  "not": {
                    "required": [
                      "reason"
                    ]
                  },
                  "required": [
                    "value"
                  ]
                }
              }
            ],
            "properties": {
              "availability": {
                "enum": [
                  "available",
                  "unavailable"
                ]
              },
              "metric_id": {
                "minLength": 1,
                "type": "string"
              },
              "reason": {
                "minLength": 1,
                "type": "string"
              },
              "scope": {
                "minLength": 1,
                "type": "string"
              },
              "unit": {
                "minLength": 1,
                "type": "string"
              },
              "value": {
                "type": [
                  "object",
                  "array",
                  "string",
                  "number",
                  "integer",
                  "boolean",
                  "null"
                ]
              }
            },
            "required": [
              "metric_id",
              "availability",
              "unit",
              "scope"
            ],
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "const": "geometry_diagnostics/2"
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
        "measurements",
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
    "label_transformations": {
      "type": "object"
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
    "mutation_ledger": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "output_path": {
      "type": "string"
    },
    "preview_resources": {
      "items": {
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/previews/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
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
    "statistical_claims": {
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

### `figops.render_csv_multipanel`

Render a multi-panel CSV-backed composite figure in an isolated runtime-root MCP job workspace.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "baseline_path": {
      "description": "Optional baseline figure path to compare the rendered output against.",
      "type": "string"
    },
    "cols": {
      "minimum": 1,
      "type": "integer"
    },
    "column_width": {
      "default": "double",
      "type": "string"
    },
    "compose_mode": {
      "default": "draft",
      "enum": [
        "draft",
        "manuscript"
      ],
      "type": "string"
    },
    "dry_run": {
      "default": false,
      "type": "boolean"
    },
    "font_scale": {
      "default": 1.0,
      "type": "number"
    },
    "job_id": {
      "description": "Stable render job ID; auto-generated when omitted.",
      "type": "string"
    },
    "layout_options": {
      "additionalProperties": false,
      "properties": {
        "gutter_h_mm": {
          "minimum": 0,
          "type": "number"
        },
        "gutter_v_mm": {
          "minimum": 0,
          "type": "number"
        },
        "height_ratios": {
          "items": {
            "exclusiveMinimum": 0,
            "type": "number"
          },
          "minItems": 1,
          "type": "array"
        },
        "hspace": {
          "minimum": 0,
          "type": "number"
        },
        "width_ratios": {
          "items": {
            "exclusiveMinimum": 0,
            "type": "number"
          },
          "minItems": 1,
          "type": "array"
        },
        "wspace": {
          "minimum": 0,
          "type": "number"
        }
      },
      "type": "object"
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
    "panel_height_mm": {
      "default": 65.0,
      "minimum": 1,
      "type": "number"
    },
    "panel_labels": {
      "default": true,
      "type": "boolean"
    },
    "panels": {
      "items": {
        "additionalProperties": false,
        "properties": {
          "annotations": {
            "description": "Point text/callout annotations plus rectangular region, hspan, and vspan overlays.",
            "items": {
              "anyOf": [
                {
                  "additionalProperties": false,
                  "properties": {
                    "analysis_artifact_sha256": {
                      "pattern": "^[0-9a-fA-F]{64}$",
                      "type": "string"
                    },
                    "annotation_kind": {
                      "default": "auto",
                      "enum": [
                        "auto",
                        "literal",
                        "statistical_claim"
                      ],
                      "type": "string"
                    },
                    "arrow_to": {
                      "properties": {
                        "x": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "y": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "x",
                        "y"
                      ],
                      "type": "object"
                    },
                    "arrowstyle": {
                      "default": "->",
                      "type": "string"
                    },
                    "avoid_overlap": {
                      "default": false,
                      "type": "boolean"
                    },
                    "calculation_evidence_id": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "color": {
                      "default": "black",
                      "type": "string"
                    },
                    "connectionstyle": {
                      "type": "string"
                    },
                    "placement_preset": {
                      "enum": [
                        "above",
                        "below",
                        "left",
                        "right",
                        "upper_left",
                        "upper_right",
                        "lower_left",
                        "lower_right"
                      ],
                      "type": "string"
                    },
                    "test_metadata": {
                      "additionalProperties": false,
                      "properties": {
                        "model": {
                          "minLength": 1,
                          "type": "string"
                        },
                        "test_name": {
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "test_name",
                        "model"
                      ],
                      "type": "object"
                    },
                    "text": {
                      "type": "string"
                    },
                    "x": {
                      "type": [
                        "number",
                        "string"
                      ]
                    },
                    "xytext_offset": {
                      "properties": {
                        "dx": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "dy": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "dx",
                        "dy"
                      ],
                      "type": "object"
                    },
                    "y": {
                      "type": [
                        "number",
                        "string"
                      ]
                    }
                  },
                  "required": [
                    "x",
                    "y",
                    "text"
                  ],
                  "type": "object"
                },
                {
                  "additionalProperties": false,
                  "properties": {
                    "analysis_artifact_sha256": {
                      "pattern": "^[0-9a-fA-F]{64}$",
                      "type": "string"
                    },
                    "annotation_kind": {
                      "default": "auto",
                      "enum": [
                        "auto",
                        "literal",
                        "statistical_claim"
                      ],
                      "type": "string"
                    },
                    "arrow_to": {
                      "properties": {
                        "x": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "y": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "x",
                        "y"
                      ],
                      "type": "object"
                    },
                    "arrowstyle": {
                      "default": "->",
                      "type": "string"
                    },
                    "avoid_overlap": {
                      "default": false,
                      "type": "boolean"
                    },
                    "calculation_evidence_id": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "color": {
                      "default": "black",
                      "type": "string"
                    },
                    "connectionstyle": {
                      "type": "string"
                    },
                    "placement_preset": {
                      "enum": [
                        "above",
                        "below",
                        "left",
                        "right",
                        "upper_left",
                        "upper_right",
                        "lower_left",
                        "lower_right"
                      ],
                      "type": "string"
                    },
                    "test_metadata": {
                      "additionalProperties": false,
                      "properties": {
                        "model": {
                          "minLength": 1,
                          "type": "string"
                        },
                        "test_name": {
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "test_name",
                        "model"
                      ],
                      "type": "object"
                    },
                    "text": {
                      "type": "string"
                    },
                    "x": {
                      "type": [
                        "number",
                        "string"
                      ]
                    },
                    "xytext_offset": {
                      "properties": {
                        "dx": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "dy": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "dx",
                        "dy"
                      ],
                      "type": "object"
                    },
                    "y": {
                      "type": [
                        "number",
                        "string"
                      ]
                    }
                  },
                  "required": [
                    "x",
                    "y",
                    "arrow_to"
                  ],
                  "type": "object"
                },
                {
                  "additionalProperties": false,
                  "properties": {
                    "alpha": {
                      "type": [
                        "number",
                        "string"
                      ]
                    },
                    "analysis_artifact_sha256": {
                      "pattern": "^[0-9a-fA-F]{64}$",
                      "type": "string"
                    },
                    "annotation_kind": {
                      "default": "auto",
                      "enum": [
                        "auto",
                        "literal",
                        "statistical_claim"
                      ],
                      "type": "string"
                    },
                    "calculation_evidence_id": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "color": {
                      "default": "black",
                      "type": "string"
                    },
                    "region": {
                      "properties": {
                        "xmax": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "xmin": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "ymax": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "ymin": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "xmin",
                        "xmax",
                        "ymin",
                        "ymax"
                      ],
                      "type": "object"
                    },
                    "test_metadata": {
                      "additionalProperties": false,
                      "properties": {
                        "model": {
                          "minLength": 1,
                          "type": "string"
                        },
                        "test_name": {
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "test_name",
                        "model"
                      ],
                      "type": "object"
                    },
                    "text": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "region"
                  ],
                  "type": "object"
                },
                {
                  "additionalProperties": false,
                  "properties": {
                    "alpha": {
                      "type": [
                        "number",
                        "string"
                      ]
                    },
                    "analysis_artifact_sha256": {
                      "pattern": "^[0-9a-fA-F]{64}$",
                      "type": "string"
                    },
                    "annotation_kind": {
                      "default": "auto",
                      "enum": [
                        "auto",
                        "literal",
                        "statistical_claim"
                      ],
                      "type": "string"
                    },
                    "calculation_evidence_id": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "color": {
                      "default": "black",
                      "type": "string"
                    },
                    "hspan": {
                      "properties": {
                        "ymax": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "ymin": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "ymin",
                        "ymax"
                      ],
                      "type": "object"
                    },
                    "test_metadata": {
                      "additionalProperties": false,
                      "properties": {
                        "model": {
                          "minLength": 1,
                          "type": "string"
                        },
                        "test_name": {
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "test_name",
                        "model"
                      ],
                      "type": "object"
                    },
                    "text": {
                      "type": "string"
                    }
                  },
                  "required": [
                    "hspan"
                  ],
                  "type": "object"
                },
                {
                  "additionalProperties": false,
                  "properties": {
                    "alpha": {
                      "type": [
                        "number",
                        "string"
                      ]
                    },
                    "analysis_artifact_sha256": {
                      "pattern": "^[0-9a-fA-F]{64}$",
                      "type": "string"
                    },
                    "annotation_kind": {
                      "default": "auto",
                      "enum": [
                        "auto",
                        "literal",
                        "statistical_claim"
                      ],
                      "type": "string"
                    },
                    "calculation_evidence_id": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "color": {
                      "default": "black",
                      "type": "string"
                    },
                    "test_metadata": {
                      "additionalProperties": false,
                      "properties": {
                        "model": {
                          "minLength": 1,
                          "type": "string"
                        },
                        "test_name": {
                          "minLength": 1,
                          "type": "string"
                        }
                      },
                      "required": [
                        "test_name",
                        "model"
                      ],
                      "type": "object"
                    },
                    "text": {
                      "type": "string"
                    },
                    "vspan": {
                      "properties": {
                        "xmax": {
                          "type": [
                            "number",
                            "string"
                          ]
                        },
                        "xmin": {
                          "type": [
                            "number",
                            "string"
                          ]
                        }
                      },
                      "required": [
                        "xmin",
                        "xmax"
                      ],
                      "type": "object"
                    }
                  },
                  "required": [
                    "vspan"
                  ],
                  "type": "object"
                }
              ]
            },
            "type": "array"
          },
          "axis_limits": {
            "additionalProperties": false,
            "properties": {
              "x": {
                "additionalProperties": false,
                "properties": {
                  "max": {
                    "type": "number"
                  },
                  "min": {
                    "type": "number"
                  }
                },
                "type": "object"
              },
              "y": {
                "additionalProperties": false,
                "properties": {
                  "max": {
                    "type": "number"
                  },
                  "min": {
                    "type": "number"
                  }
                },
                "type": "object"
              }
            },
            "type": "object"
          },
          "calculation_evidence_path": {
            "description": "CSV input path under an allowed data root.",
            "type": "string"
          },
          "calculation_evidence_paths": {
            "items": {
              "description": "CSV input path under an allowed data root.",
              "type": "string"
            },
            "maxItems": 32,
            "type": "array"
          },
          "ci_band": {
            "type": "boolean"
          },
          "compliance_mode": {
            "default": "validate",
            "enum": [
              "validate",
              "clamp"
            ],
            "type": "string"
          },
          "data_path": {
            "description": "CSV input path under an allowed data root.",
            "type": "string"
          },
          "declutter_mode": {
            "default": "none",
            "enum": [
              "none",
              "declutter"
            ],
            "type": "string"
          },
          "facet_column": {
            "type": "string"
          },
          "fill_between": {
            "description": "Manual filled bands from point triplets or CSV x/y1/y2 columns.",
            "items": {
              "additionalProperties": false,
              "anyOf": [
                {
                  "required": [
                    "points"
                  ]
                },
                {
                  "required": [
                    "x_column",
                    "y1_column",
                    "y2_column"
                  ]
                }
              ],
              "properties": {
                "alpha": {
                  "default": 0.2,
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "band_kind": {
                  "enum": [
                    "literal",
                    "confidence_interval"
                  ],
                  "type": "string"
                },
                "color": {
                  "type": "string"
                },
                "label": {
                  "type": "string"
                },
                "points": {
                  "items": {
                    "properties": {
                      "x": {
                        "type": [
                          "number",
                          "string"
                        ]
                      },
                      "y1": {
                        "type": [
                          "number",
                          "string"
                        ]
                      },
                      "y2": {
                        "type": [
                          "number",
                          "string"
                        ]
                      }
                    },
                    "required": [
                      "x",
                      "y1",
                      "y2"
                    ],
                    "type": "object"
                  },
                  "minItems": 2,
                  "type": "array"
                },
                "x_column": {
                  "type": "string"
                },
                "y1_column": {
                  "type": "string"
                },
                "y2_column": {
                  "type": "string"
                },
                "zorder": {
                  "type": [
                    "number",
                    "string"
                  ]
                }
              },
              "type": "object"
            },
            "type": "array"
          },
          "fit_line": {
            "type": "boolean"
          },
          "fit_options": {
            "additionalProperties": false,
            "properties": {
              "ci_alpha": {
                "maximum": 1,
                "minimum": 0,
                "type": "number"
              },
              "ci_label": {
                "type": "string"
              },
              "color": {
                "type": "string"
              },
              "label": {
                "type": "string"
              },
              "linestyle": {
                "type": "string"
              },
              "linewidth": {
                "exclusiveMinimum": 0,
                "type": "number"
              },
              "model": {
                "default": "linear",
                "enum": [
                  "linear"
                ],
                "type": "string"
              },
              "zorder": {
                "type": "number"
              }
            },
            "type": "object"
          },
          "guide_curves": {
            "description": "Manual guide curves from point objects or parallel x/y arrays.",
            "items": {
              "anyOf": [
                {
                  "required": [
                    "points"
                  ]
                },
                {
                  "required": [
                    "x",
                    "y"
                  ]
                }
              ],
              "properties": {
                "color": {
                  "default": "black",
                  "type": "string"
                },
                "label": {
                  "type": "string"
                },
                "linestyle": {
                  "type": "string"
                },
                "linewidth": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "points": {
                  "items": {
                    "properties": {
                      "x": {
                        "type": [
                          "number",
                          "string"
                        ]
                      },
                      "y": {
                        "type": [
                          "number",
                          "string"
                        ]
                      }
                    },
                    "required": [
                      "x",
                      "y"
                    ],
                    "type": "object"
                  },
                  "minItems": 2,
                  "type": "array"
                },
                "x": {
                  "items": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "minItems": 2,
                  "type": "array"
                },
                "y": {
                  "items": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "minItems": 2,
                  "type": "array"
                },
                "zorder": {
                  "type": [
                    "number",
                    "string"
                  ]
                }
              },
              "type": "object"
            },
            "type": "array"
          },
          "label_column": {
            "type": "string"
          },
          "label_map": {
            "additionalProperties": {
              "type": "string"
            },
            "type": "object"
          },
          "label_transform": {
            "default": "raw",
            "enum": [
              "raw",
              "legacy_compress"
            ],
            "type": "string"
          },
          "legend_layout": {
            "default": "auto",
            "enum": [
              "auto",
              "smart",
              "standard",
              "best",
              "top_outside",
              "right_outside"
            ],
            "type": "string"
          },
          "legend_options": {
            "additionalProperties": false,
            "properties": {
              "ncol": {
                "maximum": 8,
                "minimum": 1,
                "type": "integer"
              },
              "order": {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              "title": {
                "type": "string"
              }
            },
            "type": "object"
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
          "point_label_options": {
            "additionalProperties": false,
            "properties": {
              "fanout": {
                "default": "none",
                "enum": [
                  "none",
                  "compass"
                ],
                "type": "string"
              },
              "max_labels": {
                "minimum": 1,
                "type": "integer"
              },
              "offset": {
                "properties": {
                  "dx": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "dy": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "required": [
                  "dx",
                  "dy"
                ],
                "type": "object"
              },
              "priority_column": {
                "type": "string"
              },
              "skip_column": {
                "type": "string"
              }
            },
            "type": "object"
          },
          "secondary_y": {
            "additionalProperties": false,
            "properties": {
              "axis_label": {
                "type": "string"
              },
              "column": {
                "type": "string"
              },
              "enabled": {
                "default": true,
                "type": "boolean"
              },
              "limits": {
                "additionalProperties": false,
                "properties": {
                  "max": {
                    "type": [
                      "number",
                      "string"
                    ]
                  },
                  "min": {
                    "type": [
                      "number",
                      "string"
                    ]
                  }
                },
                "type": "object"
              },
              "scale": {
                "default": "linear",
                "enum": [
                  "linear",
                  "log"
                ],
                "type": "string"
              },
              "series_label": {
                "type": "string"
              }
            },
            "type": "object"
          },
          "series_column": {
            "type": "string"
          },
          "series_styles": {
            "additionalProperties": {
              "additionalProperties": false,
              "properties": {
                "alpha": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "color": {
                  "type": "string"
                },
                "edgecolor": {
                  "type": "string"
                },
                "facecolor": {
                  "type": "string"
                },
                "fill": {
                  "enum": [
                    "full",
                    "filled",
                    "none",
                    "open"
                  ],
                  "type": "string"
                },
                "hatch": {
                  "type": "string"
                },
                "label": {
                  "type": "string"
                },
                "linestyle": {
                  "type": "string"
                },
                "linewidth": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "marker": {
                  "type": "string"
                },
                "markeredgecolor": {
                  "type": "string"
                },
                "markerfacecolor": {
                  "type": "string"
                },
                "size": {
                  "type": [
                    "number",
                    "string"
                  ]
                },
                "zorder": {
                  "type": [
                    "number",
                    "string"
                  ]
                }
              },
              "type": "object"
            },
            "description": "Per-series style overrides keyed by exact series label.",
            "type": "object"
          },
          "significance_markers": {
            "items": {
              "additionalProperties": false,
              "properties": {
                "analysis_artifact_sha256": {
                  "pattern": "^[0-9a-fA-F]{64}$",
                  "type": "string"
                },
                "calculation_evidence_id": {
                  "minLength": 1,
                  "type": "string"
                },
                "color": {
                  "type": "string"
                },
                "h": {
                  "type": "number"
                },
                "label": {
                  "type": "string"
                },
                "test_metadata": {
                  "additionalProperties": false,
                  "properties": {
                    "model": {
                      "minLength": 1,
                      "type": "string"
                    },
                    "test_name": {
                      "minLength": 1,
                      "type": "string"
                    }
                  },
                  "required": [
                    "test_name",
                    "model"
                  ],
                  "type": "object"
                },
                "x1": {
                  "type": "number"
                },
                "x2": {
                  "type": "number"
                },
                "y": {
                  "type": "number"
                }
              },
              "required": [
                "x1",
                "x2",
                "y",
                "label",
                "calculation_evidence_id",
                "analysis_artifact_sha256",
                "test_metadata"
              ],
              "type": "object"
            },
            "type": "array"
          },
          "tick_style": {
            "additionalProperties": false,
            "properties": {
              "format": {
                "enum": [
                  "default",
                  "plain",
                  "scientific",
                  "compact"
                ],
                "type": "string"
              },
              "max_label_chars": {
                "minimum": 4,
                "type": "integer"
              },
              "rotation": {
                "type": "number"
              }
            },
            "type": "object"
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
          "x_scale": {
            "default": "linear",
            "enum": [
              "linear",
              "log"
            ],
            "type": "string"
          },
          "y_axis_label": {
            "type": "string"
          },
          "y_column": {
            "type": "string"
          },
          "y_scale": {
            "default": "linear",
            "enum": [
              "linear",
              "log"
            ],
            "type": "string"
          },
          "yerr_cap_width": {
            "default": 3.0,
            "minimum": 0,
            "type": "number"
          },
          "yerr_column": {
            "type": "string"
          },
          "yerr_minus_column": {
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
      },
      "minItems": 1,
      "type": "array"
    },
    "profile": {
      "default": "baseline",
      "enum": [
        "base",
        "baseline",
        "cell",
        "cell_press",
        "default",
        "publication",
        "wiley"
      ],
      "type": "string"
    },
    "rows": {
      "minimum": 1,
      "type": "integer"
    },
    "shared_legend": {
      "default": false,
      "type": "boolean"
    },
    "shared_legend_options": {
      "additionalProperties": false,
      "properties": {
        "ncol": {
          "maximum": 8,
          "minimum": 1,
          "type": "integer"
        },
        "order": {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        "position": {
          "default": "top",
          "enum": [
            "top",
            "bottom",
            "right"
          ],
          "type": "string"
        },
        "title": {
          "type": "string"
        }
      },
      "type": "object"
    },
    "target_format": {
      "default": "nature",
      "enum": [
        "acs",
        "cell",
        "default",
        "elsevier",
        "nature",
        "neutral",
        "ppt",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    }
  },
  "required": [
    "panels"
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
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/artifacts/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
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
    "calculation_evidence": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "claim_candidates": {
      "items": {
        "type": "object"
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
    "descriptive_overlays": {
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
    "evidence": {
      "type": "object"
    },
    "failure_stage": {
      "type": "string"
    },
    "geometry_diagnostics": {
      "additionalProperties": false,
      "properties": {
        "measurements": {
          "items": {
            "additionalProperties": false,
            "allOf": [
              {
                "else": {
                  "not": {
                    "required": [
                      "value"
                    ]
                  },
                  "required": [
                    "reason"
                  ]
                },
                "if": {
                  "properties": {
                    "availability": {
                      "const": "available"
                    }
                  }
                },
                "then": {
                  "not": {
                    "required": [
                      "reason"
                    ]
                  },
                  "required": [
                    "value"
                  ]
                }
              }
            ],
            "properties": {
              "availability": {
                "enum": [
                  "available",
                  "unavailable"
                ]
              },
              "metric_id": {
                "minLength": 1,
                "type": "string"
              },
              "reason": {
                "minLength": 1,
                "type": "string"
              },
              "scope": {
                "minLength": 1,
                "type": "string"
              },
              "unit": {
                "minLength": 1,
                "type": "string"
              },
              "value": {
                "type": [
                  "object",
                  "array",
                  "string",
                  "number",
                  "integer",
                  "boolean",
                  "null"
                ]
              }
            },
            "required": [
              "metric_id",
              "availability",
              "unit",
              "scope"
            ],
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "const": "geometry_diagnostics/2"
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
        "measurements",
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
    "label_transformations": {
      "type": "object"
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
    "mutation_ledger": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "operation_id": {
      "type": "string"
    },
    "output_path": {
      "type": "string"
    },
    "preview_resources": {
      "items": {
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/previews/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
      "type": "array"
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
    "statistical_claims": {
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

### `figops.render_project_figure`

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
        "publication",
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
      "description": "Project scan root. Defaults to FigOps research root.",
      "type": "string"
    },
    "target_format": {
      "enum": [
        "acs",
        "cell",
        "default",
        "elsevier",
        "nature",
        "neutral",
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
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/artifacts/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
      "type": "array"
    },
    "artifact_status": {
      "type": "string"
    },
    "baseline_comparison": {
      "type": "object"
    },
    "claim_inventory": {
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
    "evidence": {
      "type": "object"
    },
    "failure_stage": {
      "type": "string"
    },
    "figure_metadata": {
      "type": "object"
    },
    "geometry_diagnostics": {
      "additionalProperties": false,
      "properties": {
        "measurements": {
          "items": {
            "additionalProperties": false,
            "allOf": [
              {
                "else": {
                  "not": {
                    "required": [
                      "value"
                    ]
                  },
                  "required": [
                    "reason"
                  ]
                },
                "if": {
                  "properties": {
                    "availability": {
                      "const": "available"
                    }
                  }
                },
                "then": {
                  "not": {
                    "required": [
                      "reason"
                    ]
                  },
                  "required": [
                    "value"
                  ]
                }
              }
            ],
            "properties": {
              "availability": {
                "enum": [
                  "available",
                  "unavailable"
                ]
              },
              "metric_id": {
                "minLength": 1,
                "type": "string"
              },
              "reason": {
                "minLength": 1,
                "type": "string"
              },
              "scope": {
                "minLength": 1,
                "type": "string"
              },
              "unit": {
                "minLength": 1,
                "type": "string"
              },
              "value": {
                "type": [
                  "object",
                  "array",
                  "string",
                  "number",
                  "integer",
                  "boolean",
                  "null"
                ]
              }
            },
            "required": [
              "metric_id",
              "availability",
              "unit",
              "scope"
            ],
            "type": "object"
          },
          "type": "array"
        },
        "schema_version": {
          "const": "geometry_diagnostics/2"
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
        "measurements",
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
    "preview_resources": {
      "items": {
        "maxLength": 256,
        "pattern": "^figops://jobs/[A-Za-z0-9_-]{1,80}/previews/[A-Za-z0-9_.%:-]{1,240}/(?:0|[1-9][0-9]{0,2})$",
        "type": "string"
      },
      "maxItems": 256,
      "type": "array"
    },
    "project_id": {
      "type": "string"
    },
    "promotion_eligible": {
      "type": "boolean"
    },
    "provenance": {
      "type": "object"
    },
    "publication_status": {
      "enum": [
        "verified",
        "unverified"
      ],
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

### `figops.collect_artifacts`

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

### `figops.scaffold_project`

Plan or create a standard FigOps project scaffold.

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
        "neutral",
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

### `figops.normalize_project_structure`

Propose migration mappings or apply an explicitly reviewed copy-only structure plan.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "approved_mappings": {
      "description": "Explicit mappings accepted by the user after reviewing an adopt proposal.",
      "items": {
        "additionalProperties": false,
        "properties": {
          "destination": {
            "type": "string"
          },
          "role": {
            "type": "string"
          },
          "source": {
            "type": "string"
          }
        },
        "required": [
          "source",
          "destination",
          "role"
        ],
        "type": "object"
      },
      "type": "array"
    },
    "config_diff": {
      "description": "Reviewed typed project_config.yaml compare-and-swap edits.",
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "confirmation_token": {
      "description": "Exact token returned by the reviewed copy-only dry-run.",
      "type": "string"
    },
    "dry_run": {
      "default": true,
      "description": "Preview without writing files. Defaults True like scaffold_project and batch_check; the two render tools default dry_run False.",
      "type": "boolean"
    },
    "hardcoded_unresolved_references": {
      "description": "Unresolved dependencies that intentionally block apply.",
      "items": {},
      "type": "array"
    },
    "include_raw": {
      "default": false,
      "type": "boolean"
    },
    "move_policy": {
      "default": "adopt",
      "description": "adopt returns read-only proposals; copy requires approved_mappings. move and symlink remain accepted only to return a stable deprecation error.",
      "enum": [
        "adopt",
        "copy",
        "move",
        "symlink"
      ],
      "type": "string"
    },
    "overwrite": {
      "default": false,
      "description": "Deprecated compatibility argument; true always fails closed.",
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
    "confirmation_token": {
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
    "originals_preserved": {
      "type": "boolean"
    },
    "plan_digest": {
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
    "proposed_mappings": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "provenance_receipt": {
      "type": "object"
    },
    "resolution_hint": {
      "type": "string"
    },
    "rollback_journal": {
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
    "unresolved_proposals": {
      "items": {
        "type": "object"
      },
      "type": "array"
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

### `figops.batch_check`

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
      "description": "Project scan root. Defaults to FigOps research root.",
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

### `figops.evaluate_publication_readiness`

Evaluate an existing render job manifest into a read-only publication-readiness report.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "job_id": {
      "description": "Existing render job ID whose bounded manifest evidence will be evaluated.",
      "pattern": "^[A-Za-z0-9_-]{1,80}$",
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
    "readiness_report": {
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

## Frozen `graphhub.*` aliases

- `graphhub.health` → `figops.health`
- `graphhub.describe` → `figops.describe`
- `graphhub.list_styles` → `figops.list_styles`
- `graphhub.list_projects` → `figops.list_projects`
- `graphhub.inspect_project` → `figops.inspect_project`
- `graphhub.validate_project` → `figops.validate_project`
- `graphhub.render_csv_graph` → `figops.render_csv_graph`
- `graphhub.render_csv_multipanel` → `figops.render_csv_multipanel`
- `graphhub.render_project_figure` → `figops.render_project_figure`
- `graphhub.collect_artifacts` → `figops.collect_artifacts`
- `graphhub.scaffold_project` → `figops.scaffold_project`
- `graphhub.normalize_project_structure` → `figops.normalize_project_structure`
- `graphhub.batch_check` → `figops.batch_check`

## Plot Types

## Semantic Checks
