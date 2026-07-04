# QA Guide — Smoke Test & Figure Regression (v4.0)

이 문서는 독립 `figops` repository의 최소 품질 보증 절차를 정의합니다.

일상 실행 가이드는 `README.md`를 먼저 보고, 이 문서는 운영 검증이나 릴리스 전 점검 때만 사용한다.

---

## 1) 운영자용 Smoke Test 시나리오

목표:
- 대표 샘플 프로젝트에 대해 파이프라인의 **전체 도메인(Prefetch, Analysis, Contract, Plot, Diagram, Integrity)**이 깨지지 않는지 빠르게 확인.

권장 샘플:
- `12. ionoelastomer` (대화형 실행 및 시맨틱 계약 테스트용)

절차:

1. **문법 및 모듈 임포트 검사**
```bash
python -m py_compile orchestrator.py hub_core/*.py themes/*.py plotting/*.py
```

2. **허브 자동 Smoke Test**
```bash
python -m unittest tests.test_smoke
```

3. **대화형 프로젝트 탐색 확인**
```bash
python orchestrator.py  # 인자 없이 실행하여 목록 출력 확인
```

4. **샘플 프로젝트 전체 실행 (Full Cycle)**
```bash
python orchestrator.py --project "12. ionoelastomer" --step all --force --strict-lock
```

5. **도식 단독 실행 확인**
```bash
python orchestrator.py --project "12. ionoelastomer" --step diagrams --strict-lock
```

6. **전체 등록 프로젝트 점검**
```bash
python orchestrator.py --check-all --step plot --strict-lock --regression-baseline check
python orchestrator.py --check-all --step diagrams --strict-lock
```

7. **Docker Smoke Test**
```bash
python orchestrator.py --docker --docker-build --project "12. ionoelastomer" --step plot --force --strict-lock
```

8. **합격 조건**
- Exit code = 0
- `python -m unittest tests.test_smoke` 통과.
- 로그에 `📡 [Prefetch] Progress` 표시 및 `✅ All files are ready locally` 확인.
- 로그에 `🔎 [Hub Intelligence] Detected freq` 표시 확인.
- 로그에 `🔍 [Data Contract Step] ✅ Passed` 확인.
- 로그에 `✅ Output verified` 확인.
- `--step diagrams` 실행 시 diagram output verification이 통과해야 함.
- `--check-all` 요약에 `discovered_configs`, `invalid_configs`가 표시되고, invalid config가 있으면 리포트에 `invalid_projects`가 남아야 함.
- Docker 경로에서도 lock gate, provenance, plot 출력이 동일하게 통과해야 함.
- uv/R 런타임 상태와 자격증명은 repo 안이 아니라 외부 runtime/cache 경로에 있어야 함.

---

## 2) Regression & Integrity 기준안

채택 기준:
- **시맨틱 무결성 + 아티팩트 해시 기반 회귀 검증**

기준 항목:

1. **시맨틱 데이터 무결성 (Semantic Integrity)**
- `project_config.yaml`에 정의된 `semantic_checks` 통과 여부.
- `Observed min/max`가 물리적 한계 범위를 벗어나지 않아야 함.

2. **출력물 재현성 (Determinism)**
- 동일 데이터/코드 조건에서 생성된 PDF의 SHA256 해시값 일치 여부.
- Python은 `pyproject.toml` + `uv.lock`, R은 repo-level `renv.lock`을 기준으로 환경을 복원했는지 확인.
- `metadata={'CreationDate': None}` 옵션 적용 확인.
- PNG/JPG 계열 대표 산출물은 `--regression-baseline check` 시 baseline snapshot 대비 `pixel_diff_ratio`, `pixel_rms`, 크기 변경 여부를 함께 확인.
- PDF는 macOS 환경에서 `qlmanage`가 가능하면 first-page preview 기준으로 같은 diff 메트릭을 기록하고, 렌더러가 없으면 명시적으로 hash-only fallback 상태를 남긴다.

3. **파일 품질 게이트**
- 0 byte 파일 생성 금지.
- PDF/PNG 포맷 헤더 유효성 검사 통과.
- SVG는 `width`/`height` 물리 단위(`mm`, `cm`, `in`, `pt`, `px`)가 있으면
  journal max width preflight를 적용한다.
- PDF/EPS는 현재 파일 크기와 PDF font safety를 검사하되, 물리 폭 추출은
  렌더러 의존성이 커서 명시적으로 dimension check를 skip한다.

4. **수학적 최적화 및 물리적 한계선(Boundary) 교차 검증 (QA Logic)**
- 물리적 하한선(예: $y \ge 0$)과 데이터의 노이즈 밴드가 충돌하는 경우, 맹목적으로 하한선을 강제(Bounded Fitting)하여 발생하는 '계통적 오차(Systematic Error)'를 허용하지 않음.
- 피팅 및 회귀 분석 수행 시, 잔차 분포(Residual Distribution)를 우선 검증하여 모델의 수학적/물리적 타당성을 판별.

---

## 3) Publication-Ready Figure Quality Rubric

Full rubric: `docs/specs/2026-06-30-figure-quality-rubric.md`

Machine-readable geometry diagnostic map:
`docs/specs/geometry-diagnostic-rubric-map.json`. Check it with
`scripts/check_geometry_rubric_map.py` after adding or renaming any
`geometry_diagnostics/1` metric.

Graph tool qualification review for agents:
`docs/specs/2026-07-03-graph-tool-qa-review.md`

Use this rubric after render/preflight outputs exist. It is a review layer over
the existing FigOps checks, not a replacement for data contracts, geometry
diagnostics, visual regression, or provenance.

Review outcomes:
- `publishable`: cited hard gates pass, `manual_review_needed` is not true, and
  advisory issues do not obscure the result.
- `revise`: hard gates pass, but advisory polish should be improved before
  release/submission.
- `blocked`: any hard gate fails, a hard-gate diagnostic is unmeasured/skipped
  without a format/runtime reason, or `manual_review_needed=true` is unresolved.

Hard gates:
- `FQ-H1` Artifact integrity: figure exists, is non-empty, format/header and
  `validate_figure_preflight` error-enforced checks pass.
- `FQ-H2` Journal-safe geometry: no clipped required artists; `journal_compliance`
  and `font_size_token_drift` are acceptable for the selected target format.
- `FQ-H3` Readability collisions: tick, title, legend, colorbar, annotation, and
  data-artist overlap checks do not block interpretation.
- `FQ-H4` Data visibility: plotted data remain visible in the intended axes, with
  severe overplotting handled and semantic/data-contract checks still valid.
- `FQ-H5` Traceability: output maps to project config, script, inputs, style
  target/profile, provenance hash, and declared baseline when configured.

Advisory polish:
- `FQ-A1` Visual hierarchy: the primary result is visually dominant without
  hiding uncertainty or comparisons.
- `FQ-A2` Label density: labels are sparse enough to scan and dense labels are
  abbreviated, rotated, faceted, or moved out of the plot.
- `FQ-A3` Contrast and accessibility: series, overlays, reference lines, and text
  remain distinguishable in grayscale and CVD-safe review.
- `FQ-A4` Panel balance: multipanel figures have consistent scale, margins,
  labels, and legend strategy unless an asymmetry is intentional.
- `FQ-A5` Narrative clarity: measured quantity, units, groups, uncertainty, and
  takeaway are understandable without reading the plotting script.

Future geometry, preflight, or visual-regression diagnostics should map to one
of these rubric IDs, or be explicitly marked informational, before becoming a
generated warning.

Diagnostic name mapping for current render outputs:

| Surface | Names | Rubric use |
| --- | --- | --- |
| `validate_figure_preflight` | `format`, `dpi`, `dimensions`, `font_settings`, `file_size`, `color_mode` | `FQ-H1` artifact integrity. |
| `geometry_diagnostics/1` | `artists_outside_figure`, `journal_compliance`, `font_size_token_drift` | `FQ-H2` journal-safe geometry; `font_size_token_drift` can also inform `FQ-A1`. |
| `geometry_diagnostics/1` | `tick_label_overlaps`, `axis_label_title_overlap`, `figure_title_panel_title_overlap`, `colorbar_overlap`, `legend_internal_overlaps`, `artist_overlaps`, `point_annotation_overlaps` | `FQ-H3` readability collisions. |
| `geometry_diagnostics/1` | `artists_outside_axes`, `marker_marker_overlaps`, `blank_area_ratio` | `FQ-H4` data visibility; `blank_area_ratio` can also inform `FQ-A4`. |
| Data/provenance outputs | `data_contract semantic checks`, project config figure declaration, `provenance`, `figure_traceability_matrix`, visual-regression baseline state | `FQ-H5` traceability. |
| Render envelope | `manual_review_needed` | Claim boundary: when `true`, the graph is not publication-ready until resolved. |
| Render envelope | `visual_preflight_status`, `layout_report/1` | Summary surfaces; map contained findings back to `FQ-H1` through `FQ-H4` or `FQ-A1` through `FQ-A4`. |
| `geometry_diagnostics/1` | `legend_marker_consistency`, `font_size_token_drift` | `FQ-A1` advisory polish unless it also violates `FQ-H2`. |
| `geometry_diagnostics/1` | `tick_label_crowding`, `point_label_skips`, `text_axis_edge_proximity` | `FQ-A2` advisory polish unless density or edge proximity blocks readability enough to trigger `FQ-H3`. |
| `geometry_diagnostics/1` | `annotation_overlay_contrast` | `FQ-A3` advisory polish unless contrast prevents reading required text or data. |
| `geometry_diagnostics/1` | `blank_area_ratio`, `label_offset_consistency` | `FQ-A4` advisory polish unless data visibility is impaired. |
| Metadata/caption surfaces | project figure metadata, axis titles, legend labels, callouts, captions | `FQ-A5` advisory narrative review; no current hard diagnostic name. |
| `geometry_diagnostics/1` | `legend_data_collision` | Informational only in the current implementation. |

---

## 4) Agent Claim Boundaries

Agents must not describe a graph as publication-ready when
`manual_review_needed=true`. In that case, the correct wording is that FigOps
created an artifact and surfaced QA findings for revision.

Agents may claim journal compliance only for the encoded FigOps token set
(selected `target_format`, style profile, minimum font size, minimum line
width, maximum encoded figure height, and preflight checks). Claims about the
latest external publisher instructions require a dated source matrix outside
this QA guide.

Current renderer wording should stay precise:

- Safe: "publication-oriented rendering with style tokens, preflight, geometry
  diagnostics, visual regression support, and manual-review escalation."
- Unsafe: "all labels are optimally placed" or "every rendered graph is
  automatically publication-ready."

For the full agent playbook, see
`docs/specs/2026-07-03-graph-tool-qa-review.md`.

---

## 5) 운영 권고

- **허브 모듈 수정 시**: `hub_core/` 내부 로직 변경 시 반드시 2개 이상의 서로 다른 프로젝트(`ionoelastomer`, `Sulfur_polymer`)에 대해 테스트를 수행.
- **Runtime 상태 분리**: 데이터 결과값, 회귀 baseline, 실행 로그, 자격증명은 repo 밖 runtime/cache 경로에 둔다. DVC/data registry는 현재 운영 표면에서 retired 상태다.

**Last Update**: 2026-07-03 (graph tool QA qualification and agent claim boundaries)
