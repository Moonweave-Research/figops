import tempfile
import unittest
from pathlib import Path

from hub_core.config_parser import validate_config
from hub_core.mcp import GraphHubMCPServer


def _minimal_config() -> dict:
    return {
        "project": {"name": "Figure Traceability Demo"},
        "visual_style": {"target_format": "nature"},
        "language_policy": {"allow_nonstandard": True, "plot_lang": "python"},
    }


def _sample_registry() -> list[dict]:
    return [
        {"sample_id": "S60"},
        {"sample_id": "S85"},
    ]


def _experimental_conditions() -> dict:
    return {
        "conditions": [
            {"id": "lcr_al_foil_fab260406", "parameters": {"samples": ["S85"]}},
            {"id": "lcr_control_fab260406", "parameters": {"samples": ["S60"]}},
        ]
    }


def _traceable_figure() -> dict:
    return {
        "id": "fig3c",
        "script": "plot_fig3c.py",
        "inputs": ["results/data/fig3c.csv"],
        "output": "results/figures/fig3c.png",
        "claim": "n exponent rises with sulfur wt%",
        "samples": ["S60", "S85"],
        "conditions": ["lcr_al_foil_fab260406"],
    }


class FigureTraceabilityValidationTest(unittest.TestCase):
    def test_figure_with_claim_samples_and_conditions_validates(self):
        config = _minimal_config()
        config["sample_registry"] = _sample_registry()
        config["experimental_conditions"] = _experimental_conditions()
        config["figures"] = [_traceable_figure()]

        self.assertEqual(validate_config(config), [])

    def test_figure_sample_reference_must_exist_when_registry_declared(self):
        config = _minimal_config()
        config["sample_registry"] = _sample_registry()
        config["figures"] = [
            {
                **_traceable_figure(),
                "samples": ["S85", "S999"],
            }
        ]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("figures[1].samples", combined)
        self.assertIn("S999", combined)

    def test_figure_condition_reference_must_exist_when_conditions_declared(self):
        config = _minimal_config()
        config["experimental_conditions"] = _experimental_conditions()
        config["figures"] = [
            {
                **_traceable_figure(),
                "conditions": ["missing_condition"],
            }
        ]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("figures[1].conditions", combined)
        self.assertIn("missing_condition", combined)

    def test_require_figure_traceability_requires_claim_and_samples_when_registry_exists(self):
        config = _minimal_config()
        config["sample_registry"] = _sample_registry()
        config["data_contract"] = {"require_figure_traceability": True}
        config["figures"] = [
            {
                "id": "fig3c",
                "script": "plot_fig3c.py",
                "output": "results/figures/fig3c.png",
            }
        ]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("fig3c", combined)
        self.assertIn("missing claim", combined)
        self.assertIn("missing samples", combined)

    def test_figure_without_traceability_fields_is_unchanged_by_default(self):
        config = _minimal_config()
        config["figures"] = [
            {
                "id": "fig3c",
                "script": "plot_fig3c.py",
                "output": "results/figures/fig3c.png",
            }
        ]

        self.assertEqual(validate_config(config), [])


class FigureTraceabilityMCPInspectTest(unittest.TestCase):
    def test_inspect_project_surfaces_traceability_matrix(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_figure_traceability_") as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "module"
            project_dir.mkdir()
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: Figure Traceability Demo",
                        "sample_registry:",
                        "  - sample_id: S60",
                        "  - sample_id: S85",
                        "experimental_conditions:",
                        "  conditions:",
                        "    - id: lcr_al_foil_fab260406",
                        "figures:",
                        "  - id: fig3c",
                        "    script: plot_fig3c.py",
                        "    inputs:",
                        "      - results/data/fig3c.csv",
                        "    output: results/figures/fig3c.png",
                        "    claim: n exponent rises with sulfur wt%",
                        "    samples: [S60, S85]",
                        "    conditions: [lcr_al_foil_fab260406]",
                        "visual_style:",
                        "  target_format: nature",
                        "language_policy:",
                        "  allow_nonstandard: true",
                        "  plot_lang: python",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool(
                "graphhub.inspect_project",
                {"project_path": "module"},
            )["structuredContent"]

        self.assertEqual(
            result["figure_traceability_matrix"],
            [
                {
                    "id": "fig3c",
                    "claim": "n exponent rises with sulfur wt%",
                    "script": "plot_fig3c.py",
                    "inputs": ["results/data/fig3c.csv"],
                    "samples": ["S60", "S85"],
                    "conditions": ["lcr_al_foil_fab260406"],
                    "output": "results/figures/fig3c.png",
                }
            ],
        )
