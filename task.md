# 📊 Graph Making Hub — 마스터 체크리스트 (task.md)

> **최종 업데이트**: 2026-03-07 (UX 문서 분리, 사용자용 에러 안내 강화)
> **원칙**: 우선순위는 **런타임 크래시 > 아키텍처 정합성 > 문서 정확성 > 개선** 순서

---

## 🆕 Hardening Milestone (P1: 시스템 강건화)

- [x] **계약 입력 Prefetch + 집계 환경 해시 추가**
  - DoD: `data_contract.py`가 CSV 읽기 전에 `ensure_local_files`를 호출하여 GDrive 지연을 선제 처리
  - DoD: provenance가 lockfile 개별 해시 외에 집계 `environment_hash`를 출력하여 실행 환경 식별성을 강화
- [x] **Prefetch 가시성 및 안정성 확보 (utils.py)**
  - DoD: 구글 드라이브 파일 다운로드 시 실시간 진행률(예: `Downloading [1/10] ...`) 출력
  - DoD: 파일 열기 실패 시 프로세스 중단 대신 스킵 및 에러 요약 보고
- [x] **데이터 로드 강건성 강화 (data_contract.py)**
  - DoD: UTF-8 BOM 등 다양한 인코딩 자동 감지 (`utf-8-sig` 적용)
  - DoD: CSV 읽기 실패 시 원인(권한, 파일 깨짐 등)을 구체적으로 명시
- [x] **프로세스 자원 해제 및 에러 래핑 (process_runner.py)**
  - DoD: 서브프로세스 예외 발생 시에도 `finally` 블록을 통한 임시 자원 정리 보장
  - DoD: 팔레트 이름 오타 등 흔한 실수에 대해 "사용 가능한 옵션 목록"을 포함한 친절한 에러 가이드 출력

---

## 🆕 CTO Review Remediation (2026-03-05)

- [x] **Phase 1 기반 반영**: orchestrator provenance에 DVC 상태/해시(`dvc status --json` 기반) 출력 추가
- [x] **Phase 2 기반 반영**: `environment.python_lock`/`environment.r_lock` 스키마 + lockfile 사전 게이트 + strict 모드(`--strict-lock`) 도입
- [x] **Phase 3 기반 반영**: `.build_state.json` 기반 Smart Build (mtime+size 시그니처), `[RUN]/[SKIP]` 로그, `--force` 전체 재실행 도입
- [x] **템플릿/문서 동기화**: `project_config_template.yaml`, `Research_Central_Architecture.md`, `.gitignore` 업데이트
- [x] **운영 검증(실행)**: DVC local remote(`localtmp`)에서 `add/push/pull/status` 왕복 검증 완료
- [x] **운영 검증(실행)**: 실제 프로젝트(`10mm_20min_통합_260303`)에 `renv.lock` 생성 + `renv::restore()` 동기화 확인
- [x] **운영 검증(실행)**: 실제 프로젝트 `--step plot --strict-lock` 2회차에서 Smart Build `[SKIP]` 확인 + `--force` 재실행 확인
- [x] **운영 후속 작업**: DVC remote를 `gdrive://<folder_id>`로 전환하고 OAuth(Desktop app) 방식으로 `dvc push/pull` 재검증 완료
- [x] **운영 검증(실행)**: 실제 프로젝트 `--step all --strict-lock --force` 완주 + 2회차 incremental에서 analysis/plot 전체 `[SKIP]` 확인

## 🆕 실제 프로젝트 회귀 검증 (2026-03-06)

- [x] **실제 등록 프로젝트 4건 `--check-all --step plot --force --strict-lock` 통과**
  - DoD: sandbox 밖 실제 경로에서 figure 출력 권한 문제 없이 4/4 통과
- [x] **실제 등록 프로젝트 4건 `--check-all --step all --force --strict-lock` 통과**
  - DoD: `hub_logs/check_all_report.json`에 4/4 success 기록
  - DoD: `12. ionoelastomer`, `10mm_20min_통합_260303`, `[10mm_20min]`, `260130` 실제 프로젝트가 analysis+plot 전체 완주
- [x] **외부 프로젝트 설정 보정**
  - DoD: 실제 분석 스크립트가 참조하는 입력 경로를 `analysis.inputs`에 선언해 prefetch 누락 제거
  - DoD: lockfile이 없던 등록 프로젝트들에 공유 `renv.lock` 경로와 `environment.strict: false`를 반영해 strict-lock 게이트를 명시적으로 통과 가능하게 정리
- [x] **Figure baseline snapshot/hash regression 추가**
  - DoD: `--check-all --regression-baseline update/check`로 기준 figure snapshot을 저장/검사
  - DoD: `hub_logs/check_all_report.json`에 figure별 baseline 상태(`matched`, `mismatch`, `missing_baseline`, `updated`)와 image diff 요약 기록
  - DoD: sidecar PDF가 있으면 함께 추적하고, macOS Quick Look이 가능할 때 first-page preview 기준 visual diff를 기록
- [x] **Discovery 정제**
  - DoD: interactive 실행은 스키마 유효한 프로젝트만 보여주되, 운영용 `--check-all` 리포트는 invalid config를 `invalid_projects`로 별도 집계해 숨기지 않음

## 🆕 Reproducibility Lock Hardening (2026-03-06)

- [x] **Python full transitive lock 반영**
  - DoD: `requirements-lock.txt`를 현재 운영 `.venv` 기준 full freeze로 갱신해 top-level pin이 아니라 전체 dependency tree를 고정
- [x] **Repo-level `renv.lock` 도입**
  - DoD: 허브 루트에 `renv.lock`을 추가하고 Docker/R 경로가 동일 lock 기준으로 복원되도록 정렬
- [x] **Docker R restore 경로 교체**
  - DoD: `Dockerfile`이 `install.packages(...)` 최신 설치 대신 `renv.lock` 기반 `renv::restore()`를 사용
- [x] **Invalid config 운영 리포트 가시화**
  - DoD: `--check-all` 요약과 `hub_logs/check_all_report.json`에 `discovered_count`, `invalid_count`, `invalid_projects` 기록

## 🆕 UX Friction Reduction (2026-03-07)

- [x] **README 역할 분리**
  - DoD: README가 `처음 쓰는 사람`, `매일 쓰는 사람`, `운영자` 기준으로 다시 정리되고, 운영 검증 명령은 별도 섹션으로 분리
- [x] **다중 컴퓨터 운영 규칙 문서화**
  - DoD: README에 Google Drive Desktop 앱 문제와 DVC 인증 문제를 구분하고, 여러 컴퓨터 사용 규칙을 짧게 명시
- [x] **사용자용 다음 행동 안내 강화**
  - DoD: `orchestrator.py`, `config_parser.py`, `provenance.py`가 자주 발생하는 실패 지점에서 바로 다음 행동을 출력
- [x] **QA 문서 역할 명확화**
  - DoD: `QA.md`가 일상 사용 문서가 아니라 운영자용 검증 문서임을 명시

---

## 🆕 연결된 프로젝트 (Registered Projects)

- [x] **60~85wt% 액추에이션 (5일 이내 샘플)_260202** 허브 연결 완료
- [x] **10mm_20min 통합_260303** 허브 연결 완료
- [x] **10mm_20min 통합 분석** 허브 연결 완료
- [x] **12. ionoelastomer (Battle Test)** 허브 연결 및 FFT/Matched Plotting 검증 완료

---

## 🔴 P0: 즉시 수정 (런타임 크래시)

- [x] **`test_unification_run.py` 전체 재작성**
- [x] **`test_evolution.py` 수정**
- [x] **`common_plots.py` log-scale 대응**
- [x] **패키지 import 호환성 복구**
- [x] **Fail-Fast 강화**
- [x] **출력물 검증 강제**
- [x] **설정 검증 추가**
- [x] **실패 시 종료코드 반영**

---

## 🟠 P1: 데이터 계약 및 환경 격리 (데이터 무결성)

- [x] **실행 환경 분리 (P1-1)**
- [x] **CSV 계약 강제 (P1-2)**
- [x] **문서-코드 정합성 정리 (P1-3)**
- [x] **재사용 스타일 프로파일 체계 추가 (P1-4)**
- [x] **언어 원칙 강제 (P1-5)**
- [x] **액추에이션 분석 R 전환 (P1-6)**

---

## 🟡 P2: 기술 부채 및 구조 최적화 (유지보수성)

- [x] **절대경로 Fallback 제거**
- [x] **운영/실험 코드 경계 분리**
- [x] **코드 모듈화 (Refactoring)**: orchestrator.py를 `hub_core/` 패키지로 6개 모듈 분리 완료

---

## 🟢 P3: 문서 정리

- [x] **아키텍처 문서 통합**
- [x] **`README.md` 업데이트**
- [x] **`AGENTS.md` 신설**
- [x] **`SUB_AGENTS.md` 전면 개편(v3.0)**
- [x] **`GEMINI.md`/`Claude.md` 경량화**
- [x] **`Research_Central_Architecture.md` 최신 동기화**

---

## 🔵 P4: 품질 개선 (Nice-to-have)

- [x] **`requirements.txt` 생성**
- [x] **`COLUMN_1_5 = 120` 제거**
- [x] **figsize 중복 해소**
- [x] **재현성 확보 (Random Seed)**
- [x] **PDF 결정론성(Determinism) 확보**: Python/R 저장 시 타임스탬프 제거 패치 완료
- [x] **CSV 계약 강건성 보완**: 컬럼명 좌우 공백(`.strip()`) 처리 로직 추가 완료

---

## 🧭 신규 로드맵 (2026-03-03 설계 리뷰 반영)

### 🔴 P0: 신뢰성 게이트 강화 (Next)

- [x] **`target_format` enum 엄격 검증 도입**
- [x] **`--list-projects` 재귀 탐색 모드 추가**

### 🟠 P1: 재현성/아티팩트 무결성

- [x] **실행 provenance 로그 추가**
- [x] **출력 파일 품질 게이트 강화**

### 🟡 P2: 선도 운영 방식 정렬

- [x] **CI용 smoke test 시나리오 정의**
- [x] **figure regression 기준안 수립**

---

## 🧭 Maturity Roadmap (Phase 2: 성숙도 및 운영성 강화)

### 🟢 P1: 사용자 경험 및 진입 장벽 제거 (DX)
- [x] **대화형 프로젝트 선택기 (Interactive CLI)**
  - DoD: 인자 없이 실행 시 등록된 프로젝트 목록을 숫자 선택형 CLI로 표시하고 즉시 실행 가능
- [x] **스캐폴딩 자동화 (`--init`)**
  - DoD: 신규 폴더에 대해 기본 `project_config.yaml` 및 분석/플롯 스크립트 템플릿 자동 생성

### 🟡 P1: 데이터 신뢰성 및 무결성 정교화 (Reliability)
- [x] **시맨틱(논리적) 데이터 계약 도입**
  - DoD: `dtypes` 외에 `range`, `allow_null`, `unique` 등 논리적 제약 조건 검증 로직 추가 완료
- [x] **중앙 집중식 실행 로깅 (Persistence)**
  - DoD: 모든 파이프라인 실행 이력을 `hub_logs/` 폴더에 JSONL 형태로 영구 기록

### 🟠 P2: 대규모 운영 및 재현성 정점 (Operations)
- [x] **전체 프로젝트 회귀 테스트 (`--check-all`)**
  - DoD: 모든 등록 프로젝트를 일괄 실행하고 PDF/PNG 해시 변화를 자동 감지하는 리포트 생성
- [x] **도커 기반 격리 실행 환경 (Dockerization)**
  - DoD: `Dockerfile` 제공 및 `orchestrator`에서 도커 컨테이너 내 실행 옵션 지원

---

## ✅ 완료된 마일스톤 (아카이브)

### 마일스톤 1: Lean Hub v2 리팩토링
### 마일스톤 3: Theme Library 아키텍처

---

## 📝 참고 사항

- **의존성**: Seaborn 없이 **Matplotlib + NumPy** 기반으로 구현
- **폰트**: Arial/Helvetica 기본
- **허브 폴더명**: `[Graph_making_hub]`
- **운영 규약 기준 문서**: `AGENTS.md`, `SUB_AGENTS.md`

---

## 📦 Handoff Packet (2026-03-06, Hardening & Real-Project Validation)

```yaml
handoff_packet:
  summary: "hub_core hardening, logging/scaffolding/check-all/docker 추가 후, full lock + invalid-config reporting까지 운영 기준으로 정렬"
  decisions:
    - "1,300줄의 orchestrator.py를 6개 전문 모듈(config, contract, cache, provenance, runner, utils)로 분리"
    - "hub_core/utils.py에 GDrive 지연 방지를 위한 ensure_local_files (prefetcher) 추가"
    - "analysis_helpers/R에 FFT 주파수 감지 및 물리량 보정 공용 라이브러리 신설"
    - "data_contract CSV 로드 직전에도 prefetch를 강제해 계약 검증 경로를 GDrive-safe 하게 보강"
    - "provenance 출력에 lock/runtime 정보를 집계한 environment_hash를 추가"
    - "hub_core/execution_log.py를 추가해 모든 실행 결과를 중앙 hub_logs/execution_history.jsonl에 영구 기록"
    - "orchestrator --init + hub_core/scaffold.py를 추가해 신규 프로젝트 스캐폴드를 자동 생성"
    - "orchestrator --check-all + hub_core/visual_regression.py를 추가해 전체 프로젝트 회귀 리포트를 자동 생성"
    - "check-all에 --regression-baseline update/check를 추가해 figure baseline snapshot, sidecar PDF 추적, 해시 비교, image diff 요약을 opt-in으로 지원"
    - "interactive 목록은 valid project만 유지하되, 운영용 check-all/report는 invalid config를 discovered_count/invalid_projects로 별도 노출"
    - "Dockerfile + --docker/--docker-build 옵션을 추가해 격리 실행 경로를 제공"
    - "Docker image에 fonts-liberation/fontconfig를 포함하고, Python theme가 설치된 sans font만 선택하도록 바꿔 Docker font fallback 경고를 줄임"
    - "requirements-lock.txt를 full transitive lock으로 교체하고, 허브 루트 renv.lock + Docker renv::restore()로 R 환경도 lock 기반 복원으로 전환"
    - "실제 등록 프로젝트들의 project_config.yaml에 analysis.inputs / environment.r_lock 보정을 반영해 prefetch/lock 게이트를 운영 상태에 맞게 정렬"
    - "sandbox 밖 실제 경로에서 --check-all --step plot/all --force --strict-lock을 재검증해 4개 프로젝트 모두 통과 확인"
  touched_files:
    - "orchestrator.py"
    - "hub_core/*"
    - "analysis_helpers/R/*"
    - "12. ionoelastomer/*"
    - "task.md"
  verification_run:
    - "python orchestrator.py --project '12. ionoelastomer' --step all --force -> PASS"
    - "FFT Auto-detection: 10mol.csv -> 5.0 Hz 정확히 감지"
    - "Baseline Shift: Y축 0점 보정 확인"
    - "python orchestrator.py --check-all --step plot --force --strict-lock -> 4/4 PASS"
    - "python orchestrator.py --check-all --step all --force --strict-lock -> 4/4 PASS"
```
