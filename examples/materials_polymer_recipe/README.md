# Materials/Polymer Domain Helper Recipe

This public-safe fixture shows reusable M4.3 domain analysis helpers flowing through the normal
Graph Hub contract path:

1. `materials_polymer.signal_smooth_baseline` smooths and baseline-corrects a raw signal.
2. `materials_polymer.resistivity_transform` converts resistance, area, and thickness into
   resistivity and conductivity.
3. `data_contract.csv_checks` validates both declared outputs before the figure renders.

From the repository root:

```bash
uv run python orchestrator.py --project examples/materials_polymer_recipe --step all --force
```

Expected outputs:

- Data: `examples/materials_polymer_recipe/results/data/polymer_signal_cleaned.csv`
- Data: `examples/materials_polymer_recipe/results/data/polymer_material_properties.csv`
- Figure: `examples/materials_polymer_recipe/results/figures/polymer_domain_helper.png`
