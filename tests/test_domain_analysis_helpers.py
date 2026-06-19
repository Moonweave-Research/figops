import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from hub_core.config_parser import load_config, validate_config
from hub_core.data_contract import validate_data_contract
from hub_core.process_runner import run_analysis, run_plots

HUB_ROOT = Path(__file__).resolve().parent.parent


class TestMaterialsPolymerDomainHelpers(unittest.TestCase):
    def _write_raw_polymer_csv(self, project_dir: Path) -> None:
        raw_dir = project_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "polymer_response.csv").write_text(
            "\n".join(
                [
                    "time_s,signal_au,resistance_ohm,area_cm2,thickness_um",
                    "0,0.10,1000,0.5,120",
                    "1,0.30,1100,0.5,120",
                    "2,0.55,1300,0.5,120",
                    "3,0.90,1700,0.5,120",
                    "4,1.30,2200,0.5,120",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _domain_config(self) -> dict:
        return {
            "project": {"name": "materials_polymer_domain_helper"},
            "pipeline": {
                "analysis": [
                    {
                        "domain_helper": "materials_polymer.signal_smooth_baseline",
                        "inputs": ["raw/polymer_response.csv"],
                        "outputs": ["results/data/polymer_signal_cleaned.csv"],
                        "params": {
                            "x_column": "time_s",
                            "y_column": "signal_au",
                            "window": 3,
                            "baseline_method": "first",
                        },
                    },
                    {
                        "domain_helper": "materials_polymer.resistivity_transform",
                        "inputs": ["results/data/polymer_signal_cleaned.csv"],
                        "outputs": ["results/data/polymer_material_properties.csv"],
                        "params": {
                            "resistance_column": "resistance_ohm",
                            "area_column": "area_cm2",
                            "thickness_column": "thickness_um",
                            "thickness_correction_um": 20,
                        },
                    },
                ]
            },
            "data_contract": {
                "csv_checks": [
                    {
                        "path": "results/data/polymer_signal_cleaned.csv",
                        "required_columns": [
                            "time_s",
                            "signal_au",
                            "smoothed_signal_au",
                            "baseline_au",
                            "corrected_signal_au",
                        ],
                        "dtypes": {
                            "time_s": "number",
                            "signal_au": "number",
                            "smoothed_signal_au": "number",
                            "baseline_au": "number",
                            "corrected_signal_au": "number",
                        },
                        "semantic_checks": {
                            "time_s": {"monotonic": "nondecreasing", "allow_null": False},
                            "corrected_signal_au": {"range": [-1, 2], "allow_null": False},
                        },
                    },
                    {
                        "path": "results/data/polymer_material_properties.csv",
                        "required_columns": [
                            "time_s",
                            "resistance_ohm",
                            "resistivity_ohm_cm",
                            "conductivity_s_cm",
                        ],
                        "dtypes": {
                            "time_s": "number",
                            "resistance_ohm": "number",
                            "resistivity_ohm_cm": "number",
                            "conductivity_s_cm": "number",
                        },
                        "semantic_checks": {
                            "resistivity_ohm_cm": {"range": [1, 200000], "allow_null": False},
                            "conductivity_s_cm": {"range": [0, 1], "allow_null": False},
                        },
                    },
                ]
            },
        }

    def test_domain_helper_config_is_valid_without_project_local_script(self):
        errors = validate_config(self._domain_config())

        self.assertEqual(errors, [])

    def test_domain_helper_outputs_pass_declared_contract_on_valid_input(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_domain_valid_") as tmpdir:
            project_dir = Path(tmpdir)
            self._write_raw_polymer_csv(project_dir)
            config = self._domain_config()

            analysis_ok = run_analysis(
                str(project_dir),
                config,
                {},
                str(project_dir / ".build_state.json"),
                "config-hash",
                force=True,
            )

            self.assertTrue(analysis_ok)
            self.assertTrue(validate_data_contract(str(project_dir), config))
            with (project_dir / "results" / "data" / "polymer_material_properties.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 5)
            self.assertAlmostEqual(float(rows[0]["resistivity_ohm_cm"]), 50000.0)
            self.assertAlmostEqual(float(rows[0]["conductivity_s_cm"]), 0.00002)

    def test_declared_contract_fails_loudly_when_domain_output_violates_schema(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_domain_contract_fail_") as tmpdir:
            project_dir = Path(tmpdir)
            self._write_raw_polymer_csv(project_dir)
            config = self._domain_config()
            config["data_contract"]["csv_checks"][1]["semantic_checks"]["resistivity_ohm_cm"]["range"] = [0, 10]

            self.assertTrue(
                run_analysis(
                    str(project_dir),
                    config,
                    {},
                    str(project_dir / ".build_state.json"),
                    "config-hash",
                    force=True,
                )
            )

            self.assertFalse(validate_data_contract(str(project_dir), config))

    def test_invalid_domain_helper_arg_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_domain_invalid_arg_") as tmpdir:
            project_dir = Path(tmpdir)
            self._write_raw_polymer_csv(project_dir)
            config = self._domain_config()
            config["pipeline"]["analysis"][0]["params"]["window"] = 0

            analysis_ok = run_analysis(
                str(project_dir),
                config,
                {},
                str(project_dir / ".build_state.json"),
                "config-hash",
                force=True,
            )

            self.assertFalse(analysis_ok)
            self.assertFalse((project_dir / "results" / "data" / "polymer_signal_cleaned.csv").exists())

    def test_materials_polymer_recipe_runs_analysis_contract_and_figure(self):
        with tempfile.TemporaryDirectory(prefix="graph_hub_domain_recipe_") as tmpdir:
            project_dir = Path(tmpdir) / "materials_polymer_recipe"
            shutil.copytree(HUB_ROOT / "examples" / "materials_polymer_recipe", project_dir)

            config, _config_path, config_hash = load_config(str(project_dir))
            self.assertIsNotNone(config)
            build_state: dict = {}
            build_state_path = str(project_dir / ".build_state.json")

            self.assertTrue(
                run_analysis(
                    str(project_dir),
                    config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=True,
                )
            )
            self.assertTrue(validate_data_contract(str(project_dir), config))
            self.assertTrue(run_plots(str(project_dir), config, build_state, build_state_path, config_hash, force=True))
            self.assertTrue((project_dir / "results" / "figures" / "polymer_domain_helper.png").is_file())
