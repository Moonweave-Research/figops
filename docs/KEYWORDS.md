# 🔑 Research Central Knowledge Keywords (Search Index)

> **Purpose**: This file acts as a high-density "Anchor" for AI agents to quickly index and retrieve established physical models, analytical thresholds, and structure-property relationships.

---

## 🔬 [1] ISPD & Trap Dynamics (Microscopic)

- **ISPD_ANALYSIS**: Intelligent Surface Potential Decay. Used to derive trap state density $N_t(E)$ from voltage decay $V_s(t)$.
- **TRAP_MERGE_THRESHOLD**: **5% Similarity Rule**. If $\tau_{shallow}$ and $\tau_{deep}$ are within 5%, the distribution is classified as **Merged/Unimodal** (Typical of S75).
- **BIMODAL_TRAP_SIGNATURE**: Presence of a distinct deep trap component ($\tau \approx 24h$). Indicates **Structural Heterogeneity/Aggregation** (Typical of S80).
- **ENERGY_MAPPING**: Converting time to energy domain via $E_t = k_B T \ln(\nu t)$. Standard frequency factor $\nu = 10^{12}\ Hz$.

---

## ⚡ [2] Charge Transport & Resistance (Macroscopic)

- **CVS_POWER_LAW**: Curie-von Schweidler behavior. $I(t) = A \cdot t^{-n}$.
- **TRAPPING_INDEX_N**:
  - **$n > 1.0$**: Trap-limited conduction. Efficient insulation (S75, $n=1.21$).
  - **$n < 1.0$**: Percolation/Leakage-aided conduction. Structural defects (S80, $n=0.92$).
- **RESISTANCE_STABILIZATION**: Correlated to trap homogeneity. Unimodal traps lead to $10\times$ higher resistance increase rates ($\Delta R/R_0$) compared to bimodal/defect-rich samples.

---

## 🛠️ [3] System & Hub Automation

- **RESEARCH_HUB_PATH**: Global environment variable pointing to `[Graph_making_hub]`.
- **DATA_CONTRACT**: The strict CSV schema agreement between analysis and plotting modules.
- **PROVENANCE_LOG**: Execution metadata (Runtime, Hashes, Environment) recorded in `hub_logs/`.
- **SMART_BUILD**: Mtime-based skip logic for optimized pipeline execution (`--force` to override).

---

## 🏷️ [4] Material Families

- **SULFUR_RICH_POLYMER (SRP)**: High-k dielectric polymers with tunable sulfur content.
- **S75_OPTIMAL**: Reference for homogeneous network and maximum dielectric stability.
- **S80_DEFECT**: Reference for sulfur aggregation and percolation leakage pathways.
