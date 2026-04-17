# plan.md — CTO Architecture Review 대응 로드맵

> **Date**: 2026-03-05
> **Trigger**: CTO Architecture Review 심층 진단 리포트
> **Author**: Planner Agent (Senior Planning Agent & Project Manager)

---

## Mode: Safe

CTO 리뷰에서 식별된 3대 아키텍처 취약점(환경 격리, 데이터 버전 관리, 멱등성/캐싱)은 시스템의 재현성과 확장성의 근간에 해당한다. 이전 `analyst_report.md`가 존재하지 않으므로 Self-Healing Rule은 해당 없으나, 변경 범위와 리스크를 고려하여 Safe 모드로 진행한다.

---

## 1. Goal

CTO 리뷰에서 지적된 3대 엔지니어링 허점을 단계적으로 해소하여, Graph_making_hub을 **100% 환경 재현 가능하고, 데이터 이력 추적이 가능하며, 불필요한 재실행을 회피하는** 선도 연구 파이프라인으로 격상시킨다.

---

## 2. Scope In / Out

### Scope In
| Phase | 핵심 작업 | 소유 Sub-agent |
|-------|----------|---------------|
| Phase 1 | DVC(Data Version Control) 도입 — 원시 데이터 및 정제 CSV 해시 추적 | Pipeline-Orchestrator, Data-Contract Guardian |
| Phase 2 | Lockfile 기반 환경 통제 — Python `uv.lock`/`requirements.txt` 강제 + R `renv.lock` 도입 | Pipeline-Orchestrator |
| Phase 3 | Smart Build 엔진 — 파일 변경 감지 기반 선택적 단계 실행 (orchestrator 내부 통합) | Pipeline-Orchestrator |

### Scope Out
- Docker/Nix 컨테이너화 (Phase 2 이후 별도 로드맵)
- Snakemake/Nextflow 등 외부 워크플로 엔진 직접 도입 (orchestrator 내부 로직으로 대체)
- CI/CD 파이프라인 구축 (기존 QA.md smoke test 수준 유지)
- 테마 엔진(`themes/`) 또는 플롯 헬퍼(`plotting/`) 변경
- 기존 프로젝트의 분석/플롯 스크립트 수정

---

## 3. Constraints / Risks

| ID | 항목 | 심각도 | 대응 |
|----|------|--------|------|
| R1 | DVC 도입 시 `.dvc` 메타파일이 Git 히스토리를 오염시킬 수 있음 | Medium | `.gitignore` 정책 사전 설계, DVC remote는 Google Drive 연동 |
| R2 | `renv.lock` 초기화 시 기존 R 패키지와 충돌 가능 | Medium | 프로젝트별 `renv` 격리, 글로벌 캐시 활용 |
| R3 | Smart Build의 해시 비교 로직이 orchestrator 복잡도를 증가시킴 | Medium | 최소 구현(파일 mtime + size 비교)으로 시작, 해시는 Phase 3.5에서 선택적 도입 |
| R4 | 로컬 PC 환경(macOS)에서 cairo/X11 미설치로 R PDF 생성 불가 (기존 이슈) | Low | Phase 2에서 `renv`로 cairo 의존성 명시적 관리 |
| R5 | Google Drive 동기화와 DVC 캐시 충돌 가능성 | Medium | `.dvc/cache`를 `.gitignore`에 추가, remote storage는 별도 GDrive 폴더 사용 |

---

## 4. Step-by-Step Implementation

### Phase 1: DVC 도입 (Data Version Control)

**목표**: 원시 데이터와 정제 CSV의 버전을 Git과 분리하여 추적. 과거 어느 시점의 데이터도 복원 가능하게 만든다.

| Step | 작업 | 상세 |
|------|------|------|
| 1.1 | DVC 설치 및 초기화 | `pip install dvc dvc-gdrive` → `dvc init` (Hub 루트) |
| 1.2 | Remote storage 설정 | `dvc remote add -d gdrive gdrive://<folder_id>` — 연구 Google Drive 내 전용 폴더 |
| 1.3 | 데이터 추적 등록 | 각 프로젝트의 `data/raw/`와 `results/data/`를 `dvc add`로 등록 |
| 1.4 | `.gitignore` 정비 | DVC가 자동 생성하는 `.gitignore` 항목 검증, `.dvc/cache` 제외 확인 |
| 1.5 | orchestrator 연동 | provenance 로그에 `dvc status` 결과(data hash) 추가 |
| 1.6 | 문서 업데이트 | `Research_Central_Architecture.md` §1 폴더 구조에 `.dvc` 관련 항목 추가 |

### Phase 2: Lockfile 기반 환경 통제

**목표**: Python/R 패키지 버전을 코드로 고정하여, 어떤 머신에서든 동일한 분석 결과를 보장한다.

| Step | 작업 | 상세 |
|------|------|------|
| 2.1 | Python 환경 잠금 | Hub 루트에 `uv.lock` 생성 (`uv lock`) 또는 `pip freeze > requirements-lock.txt` |
| 2.2 | R 환경 잠금 | 각 프로젝트에서 `renv::init()` → `renv::snapshot()` → `renv.lock` 생성 |
| 2.3 | orchestrator 사전 검증 게이트 | 파이프라인 시작 전 lockfile 존재 여부 확인, 미존재 시 경고(first run) 또는 실패(strict mode) |
| 2.4 | `project_config.yaml` 스키마 확장 | `environment.python_lock`, `environment.r_lock` 필드 추가 (optional) |
| 2.5 | provenance 로그 강화 | lockfile 해시를 provenance에 포함 |
| 2.6 | 문서 업데이트 | `Research_Central_Architecture.md` §6 스키마에 environment 섹션 추가 |

### Phase 3: Smart Build 엔진 (Incremental Execution)

**목표**: 변경되지 않은 단계는 캐시를 사용하여 건너뛰어, 대규모 분석의 반복 실행 시간을 최소화한다.

| Step | 작업 | 상세 |
|------|------|------|
| 3.1 | 빌드 상태 저장소 설계 | 프로젝트별 `.build_state.json` — 각 step의 입력 파일 mtime/size, 출력 파일 mtime/size 기록 |
| 3.2 | 변경 감지 로직 구현 | orchestrator 내부에 `_is_step_stale(step_config, build_state) -> bool` 함수 추가 |
| 3.3 | 선택적 실행 통합 | `--force` 플래그 없으면 stale한 단계만 실행, `--force`면 전체 재실행 |
| 3.4 | 캐시 무효화 정책 | `project_config.yaml` 변경 시 전체 무효화, 개별 스크립트 변경 시 해당 단계만 무효화 |
| 3.5 | CLI UX | 실행 시 `[SKIP] analysis (unchanged)`, `[RUN] plot (script modified)` 등 명확한 로그 |
| 3.6 | 문서 업데이트 | `Research_Central_Architecture.md` §4.5에 Smart Build 동작 설명 추가 |

---

## 5. Acceptance Criteria (Testable)

### Phase 1 — DVC
- [x] `dvc status`가 Hub 루트에서 정상 실행되고, 추적 중인 데이터 파일 목록 출력
- [x] `dvc push` / `dvc pull`로 Google Drive remote와 데이터 왕복 성공
- [x] 기존 프로젝트 1개(`10mm_20min`)에서 `results/data/*.csv`를 변경 후 `dvc diff`로 변경 이력 확인 가능
- [x] orchestrator provenance 로그에 data hash 항목 포함

### Phase 2 — Lockfile
- [x] Hub 루트에 `uv.lock` 또는 `requirements-lock.txt` 존재, `uv sync` 또는 `pip install -r`로 환경 재현 가능
- [x] 프로젝트 1개에서 `renv.lock` 존재, `renv::restore()`로 R 환경 재현 가능
- [x] orchestrator가 lockfile 미존재 시 경고 메시지 출력 (strict mode에서는 exit 1)
- [x] provenance 로그에 python lockfile hash + R lockfile hash 포함

### Phase 3 — Smart Build
- [x] 분석 완료 후 플롯 스크립트만 수정 → `orchestrator.py --project <path>` 실행 시 analysis 단계 SKIP 확인
- [x] `--force` 플래그 시 모든 단계 재실행 확인
- [x] `project_config.yaml` 수정 시 전체 빌드 상태 무효화 확인
- [x] `.build_state.json`이 프로젝트 디렉토리에 정상 생성/갱신

---

## 6. Rollback Plan

| Phase | 롤백 방법 |
|-------|----------|
| Phase 1 | `dvc destroy`로 DVC 메타데이터 완전 제거, `.dvc` 파일 삭제 후 `git commit` |
| Phase 2 | lockfile 삭제, orchestrator의 lockfile 검증 게이트 코드 revert (`git revert`) |
| Phase 3 | `.build_state.json` 삭제, orchestrator의 변경 감지 로직 revert (`git revert`), `--force`가 기본 동작으로 복귀 |

공통: 각 Phase는 독립적 Git branch에서 작업하므로, branch 삭제로 완전 롤백 가능.

---

## 7. Implementation Priority & Dependencies

```
Phase 1 (DVC) ──────────┐
                         ├──→ Phase 3 (Smart Build)
Phase 2 (Lockfile) ──────┘
```

- Phase 1과 Phase 2는 **병렬 진행 가능** (독립적)
- Phase 3는 Phase 1의 데이터 해시 인프라에 의존하므로 Phase 1 완료 후 착수

---

## Ready for Coder

3-Phase 로드맵이 확정되었다. Phase 1(DVC)과 Phase 2(Lockfile)는 병렬 착수 가능하며, Phase 3(Smart Build)는 Phase 1 완료 후 시작한다. 각 Phase는 독립 branch에서 작업하고, Acceptance Criteria의 모든 체크리스트를 통과해야 merge한다. 소유 Sub-agent는 `Pipeline-Orchestrator`가 주도하고, Phase 1의 데이터 계약 부분은 `Data-Contract Guardian`이 협업한다.

---

## Ready for Analyst

Coder implementation/validation is finalized as of **2026-03-05**.

- Phase 1~3 acceptance criteria are checked complete in this plan.
- Operational evidence is recorded in `task.md`:
  - `Handoff Packet (2026-03-05, CTO Review Roadmap Phase 1~3 Core)`
  - `Handoff Packet (2026-03-05, Execution Validation 1/2/3)`
- Final validation includes:
  - DVC GDrive remote(OAuth Desktop app) `push/pull` success
  - `--step all --strict-lock --force` full run success
  - 2nd incremental run with analysis/plot `[SKIP]` confirmation
