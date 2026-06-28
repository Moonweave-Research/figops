"""Semantic data-contract registry metadata.

This module intentionally contains descriptions and schemas only. Runtime
validation stays in ``data_contract_semantics`` so the registry can back MCP
describe/tool-reference output without importing semantic check execution
helpers.
"""

_MONOTONIC_MODES = {"increasing", "decreasing", "nondecreasing", "nonincreasing"}

SEMANTIC_CHECK_DEFINITIONS = {
    "allow_null": {
        "purpose": "Require or allow null values in the target column.",
        "schema": {"type": "boolean", "default": True},
        "example": {"y": {"allow_null": False}},
    },
    "range": {
        "purpose": "Require numeric values to fall within an inclusive [min, max] interval.",
        "schema": {
            "type": "array",
            "prefixItems": [{"type": "number"}, {"type": "number"}],
            "minItems": 2,
            "maxItems": 2,
        },
        "example": {"y": {"range": [0, 1]}},
    },
    "unique": {
        "purpose": "Require every value in the target column to be unique.",
        "schema": {"type": "boolean"},
        "example": {"sample_id": {"unique": True}},
    },
    "monotonic": {
        "purpose": "Require ordered values in the target column.",
        "schema": {"type": "string", "enum": sorted(_MONOTONIC_MODES)},
        "example": {"time": {"monotonic": "increasing"}},
    },
    "monotonic_within_group": {
        "purpose": "Require ordered values in the target column within each configured group.",
        "schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "mode": {"type": "string", "enum": sorted(_MONOTONIC_MODES)},
            },
            "required": ["group_by", "mode"],
        },
        "example": {"time": {"monotonic_within_group": {"group_by": ["sample"], "mode": "increasing"}}},
    },
    "min_replicates": {
        "purpose": "Require a minimum replicate count within groups.",
        "schema": {"type": "object"},
        "example": {"mean": {"min_replicates": {"group_by": ["condition"], "n": 3}}},
    },
    "expected_sample_count": {
        "purpose": "Require each configured group to have an exact or ranged expected count of non-null target values.",
        "schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "count": {"type": "integer", "minimum": 1},
                "range": {
                    "type": "array",
                    "prefixItems": [{"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 1}],
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "required": ["group_by"],
            "oneOf": [{"required": ["count"]}, {"required": ["range"]}],
        },
        "example": {"value": {"expected_sample_count": {"group_by": ["condition"], "range": [3, 5]}}},
    },
    "grouped_cv": {
        "purpose": "Check coefficient of variation within configured groups.",
        "schema": {"type": "object"},
        "example": {"mean": {"grouped_cv": {"group_by": ["condition"], "threshold": 0.15}}},
    },
    "log_scale_positive": {
        "purpose": "Require positive values when the column will be plotted on a log scale.",
        "schema": {"type": "boolean"},
        "example": {"mean": {"log_scale_positive": True}},
    },
    "error_bar_source": {
        "purpose": "Declare and validate the source column used for error bars.",
        "schema": {"type": "object"},
        "example": {"mean": {"error_bar_source": {"column": "sem", "source": "sem"}}},
    },
    "mean_sem": {
        "purpose": "Validate mean and SEM relationships from grouped replicate data.",
        "schema": {"type": "object"},
        "example": {"mean": {"mean_sem": {"group_by": ["condition"], "sem_column": "sem"}}},
    },
    "linear_fit": {
        "purpose": "Validate a target column against an expected linear fit.",
        "schema": {"type": "object"},
        "example": {"y": {"linear_fit": {"x_column": "x", "slope": 2.0, "intercept": 1.0}}},
    },
    "outlier_flag": {
        "purpose": "Validate a boolean outlier flag column and maximum flagged fraction.",
        "schema": {"type": "object"},
        "example": {"y": {"outlier_flag": {"column": "outlier", "max_fraction": 0.25}}},
    },
    "axis_unit": {
        "purpose": "Validate that a configured axis unit conversion is compatible.",
        "schema": {"type": "object"},
        "example": {"current": {"axis_unit": {"data_unit": "mA", "display_unit": "A"}}},
    },
    "unit": {
        "purpose": "Validate actual_unit compatibility with an expected unit when Pint is installed.",
        "schema": {"type": "string"},
        "example": {"current": {"unit": "A", "actual_unit": "mA"}},
    },
    "unit_coherence": {
        "purpose": "Validate that declared related-column units combine to the target column's expected unit.",
        "schema": {
            "type": "object",
            "properties": {
                "expected_unit": {"type": "string"},
                "terms": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "unit": {"type": "string"},
                            "exponent": {"type": "integer", "default": 1},
                        },
                        "required": ["column", "unit"],
                    },
                    "minItems": 1,
                },
            },
            "required": ["expected_unit", "terms"],
        },
        "example": {
            "resistivity": {
                "unit_coherence": {
                    "expected_unit": "ohm*cm",
                    "terms": [
                        {"column": "resistance", "unit": "ohm"},
                        {"column": "area", "unit": "cm^2"},
                        {"column": "thickness", "unit": "cm", "exponent": -1},
                    ],
                }
            }
        },
    },
}
