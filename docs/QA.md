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

4. **수학적 최적화 및 물리적 한계선(Boundary) 교차 검증 (QA Logic)**
- 물리적 하한선(예: $y \ge 0$)과 데이터의 노이즈 밴드가 충돌하는 경우, 맹목적으로 하한선을 강제(Bounded Fitting)하여 발생하는 '계통적 오차(Systematic Error)'를 허용하지 않음.
- 피팅 및 회귀 분석 수행 시, 잔차 분포(Residual Distribution)를 우선 검증하여 모델의 수학적/물리적 타당성을 판별.

---

## 3) 운영 권고

- **허브 모듈 수정 시**: `hub_core/` 내부 로직 변경 시 반드시 2개 이상의 서로 다른 프로젝트(`ionoelastomer`, `Sulfur_polymer`)에 대해 테스트를 수행.
- **Runtime 상태 분리**: 데이터 결과값, 회귀 baseline, 실행 로그, 자격증명은 repo 밖 runtime/cache 경로에 둔다. DVC/data registry는 현재 운영 표면에서 retired 상태다.

**Last Update**: 2026-06-07 (independent repo cleanup and uv lock alignment)
