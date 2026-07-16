# FigOps MCP Tool Reference — v2 profile

This file is generated from the live FigOps MCP registries.
Regenerate it with:

```bash
python hub_uv.py run python scripts/gen_tool_reference.py --write --profile v2
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

Summarize capabilities or inspect one project's declared structure without writing files.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "kind": {
      "enum": [
        "tools",
        "plot_types",
        "semantic_checks",
        "domain_helpers",
        "project_structure"
      ],
      "type": "string"
    },
    "name": {
      "maxLength": 256,
      "minLength": 1,
      "type": "string"
    },
    "project_id": {
      "maxLength": 256,
      "minLength": 1,
      "type": "string"
    },
    "project_path": {
      "maxLength": 4096,
      "minLength": 1,
      "type": "string"
    }
  },
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": true,
  "properties": {
    "available_profiles": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "detail": {
      "type": [
        "object",
        "null"
      ]
    },
    "findings": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "graph": {
      "type": "object"
    },
    "kinds": {
      "items": {
        "type": "object"
      },
      "type": "array"
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
    "status": {
      "type": "string"
    },
    "status_code": {
      "type": "string"
    },
    "summary": {
      "type": "string"
    },
    "surface_profile": {
      "enum": [
        "v2",
        "compatibility"
      ],
      "type": "string"
    },
    "unknowns": {
      "items": {
        "type": "object"
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

### `figops.inspect_data`

Inspect an allowed CSV or TSV under declared sensitivity policy; undeclared, unspecified, and restricted data return metadata only.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "columns": {
      "items": {
        "maxLength": 512,
        "minLength": 1,
        "type": "string"
      },
      "maxItems": 256,
      "type": "array"
    },
    "data_path": {
      "maxLength": 4096,
      "minLength": 1,
      "type": "string"
    },
    "external_raw_id": {
      "description": "Required for value samples from a declared external_raw source; must match the descriptor id bound to its launcher-approved root.",
      "maxLength": 128,
      "minLength": 1,
      "type": "string"
    },
    "include_samples": {
      "default": false,
      "type": "boolean"
    },
    "sample_rows": {
      "default": 0,
      "maximum": 20,
      "minimum": 0,
      "type": "integer"
    }
  },
  "required": [
    "data_path"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "access_policy": {
      "additionalProperties": false,
      "properties": {
        "classification": {
          "enum": [
            "public",
            "internal",
            "restricted",
            "unspecified",
            "unknown"
          ],
          "type": "string"
        },
        "declaration_source": {
          "type": "string"
        },
        "external_raw_identity": {
          "type": "object"
        },
        "materialized_sha256_verified": {
          "type": "boolean"
        },
        "mode": {
          "enum": [
            "metadata_only",
            "bounded_values"
          ],
          "type": "string"
        },
        "reason_code": {
          "type": "string"
        },
        "samples_allowed": {
          "type": "boolean"
        },
        "samples_requested": {
          "type": "boolean"
        }
      },
      "required": [
        "classification",
        "declaration_source",
        "mode",
        "samples_requested",
        "samples_allowed",
        "reason_code"
      ],
      "type": "object"
    },
    "availability": {
      "type": "object"
    },
    "columns": {
      "items": {
        "type": "object"
      },
      "type": "array"
    },
    "limits": {
      "type": "object"
    },
    "sample_columns": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "samples": {
      "items": {
        "type": "array"
      },
      "type": "array"
    },
    "scan": {
      "type": [
        "object",
        "null"
      ]
    },
    "schema_version": {
      "type": "string"
    },
    "source": {
      "type": "object"
    },
    "status": {
      "enum": [
        "available",
        "unavailable"
      ],
      "type": "string"
    },
    "status_code": {
      "type": "string"
    },
    "truncation": {
      "type": "object"
    },
    "warnings": {
      "items": {
        "type": "object"
      },
      "type": "array"
    }
  },
  "type": "object"
}
```

### `figops.render_basic_csv`

Render one quick CSV chart with raw labels and no statistics DSL.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "data_path": {
      "maxLength": 4096,
      "minLength": 1,
      "type": "string"
    },
    "facet": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "job_id": {
      "maxLength": 80,
      "pattern": "^[A-Za-z0-9_-]{1,80}$",
      "type": "string"
    },
    "labels": {
      "additionalProperties": false,
      "properties": {
        "title": {
          "maxLength": 512,
          "type": "string"
        },
        "x_axis": {
          "maxLength": 512,
          "type": "string"
        },
        "y_axis": {
          "maxLength": 512,
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
        "scatter",
        "line",
        "bar"
      ],
      "type": "string"
    },
    "series": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "style_policy": {
      "default": "neutral",
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
    "validation_target": {
      "enum": [
        "acs",
        "cell",
        "elsevier",
        "nature",
        "rsc",
        "science",
        "wiley"
      ],
      "type": "string"
    },
    "x": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "y": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "data_path",
    "x",
    "y"
  ],
  "type": "object"
}
```

**Output schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "artifact": {
      "type": [
        "object",
        "null"
      ]
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "evidence": {
      "type": [
        "object",
        "null"
      ]
    },
    "job_id": {
      "type": "string"
    },
    "manifest_uri": {
      "type": [
        "string",
        "null"
      ]
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "preview_uri": {
      "type": [
        "string",
        "null"
      ]
    },
    "schema_version": {
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
    "summary": {
      "type": "string"
    },
    "tool": {
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

### `figops.render_project_script`

Render one configured project-local .py or .R figure; code and command strings are forbidden.

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
    "figure_id": {
      "maxLength": 512,
      "minLength": 1,
      "type": "string"
    },
    "figure_output": {
      "maxLength": 4096,
      "minLength": 1,
      "type": "string"
    },
    "job_id": {
      "maxLength": 80,
      "pattern": "^[A-Za-z0-9_-]{1,80}$",
      "type": "string"
    },
    "overwrite": {
      "default": false,
      "type": "boolean"
    },
    "project_id": {
      "description": "Discovered project ID; mutually exclusive with project_path, supply exactly one.",
      "type": "string"
    },
    "project_path": {
      "description": "Project path; mutually exclusive with project_id, supply exactly one.",
      "type": "string"
    },
    "style_policy": {
      "default": "neutral",
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
    "validation_target": {
      "enum": [
        "acs",
        "cell",
        "elsevier",
        "nature",
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
    "artifact": {
      "type": [
        "object",
        "null"
      ]
    },
    "errors": {
      "items": {
        "type": "string"
      },
      "type": "array"
    },
    "evidence": {
      "type": [
        "object",
        "null"
      ]
    },
    "job_id": {
      "type": "string"
    },
    "manifest_uri": {
      "type": [
        "string",
        "null"
      ]
    },
    "manual_review_needed": {
      "type": "boolean"
    },
    "preview_uri": {
      "type": [
        "string",
        "null"
      ]
    },
    "runtime_availability": {
      "type": "object"
    },
    "schema_version": {
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
    "summary": {
      "type": "string"
    },
    "tool": {
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

### `figops.audit_artifact`

Audit validated completed-job evidence with zero or more explicit policy packs.

**Input schema**

```json
{
  "additionalProperties": false,
  "properties": {
    "job_id": {
      "maxLength": 80,
      "pattern": "^[A-Za-z0-9_-]{1,80}$",
      "type": "string"
    },
    "policy_packs": {
      "default": [],
      "items": {
        "enum": [
          "publication-readiness-v1"
        ],
        "type": "string"
      },
      "maxItems": 1,
      "type": "array",
      "uniqueItems": true
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
    "artifact": {
      "type": [
        "object",
        "null"
      ]
    },
    "audit": {
      "type": "object"
    },
    "job_id": {
      "type": "string"
    },
    "manifest_uri": {
      "type": "string"
    },
    "preview_uri": {
      "type": [
        "string",
        "null"
      ]
    },
    "schema_version": {
      "type": "string"
    },
    "status": {
      "enum": [
        "blocked",
        "needs_revision",
        "needs_review"
      ],
      "type": "string"
    }
  },
  "type": "object"
}
```

## Plot Types

## Semantic Checks
