# PDCA Plan: Orchestrator Refactoring

## 1. Feature Info
- **Feature Name**: orchestrator_refactoring
- **Role**: cto-lead
- **Target Date**: 2026-03-05

## 2. Objective
현재 1,300줄 이상으로 비대해진 단일 파일 `orchestrator.py`를 `hub_core/` 패키지 구조로 모듈화(Refactoring)하여 **가독성, 유지보수성, 그리고 확장성**을 확보한다. 단, 새롭게 추가된 프로급 기능(DVC 연동, Lockfile 환경 통제, Smart Build)을 포함한 모든 기존 기능은 **100% 하위 호환(Backward Compatible)**되어야 한다.

## 3. Scope
### 🟢 Scope In
- `orchestrator.py` 파일 내에 혼재된 도메인 로직(설정 검증, 실행기, 데이터 계약, 캐싱 등)을 분리.
- `hub_core/` 디렉토리 신설 및 내부 Python 모듈(`config.py`, `contract.py`, `runner.py`, `cache.py`, `provenance.py` 등) 구현.
- 분리된 모듈들을 조합하여 기존과 완전히 동일한 CLI 인터페이스를 제공하는 경량화된 `orchestrator.py` (100줄 이내) 작성.

### 🔴 Scope Out
- `project_config.yaml` 스키마 자체의 변경.
- 새로운 파이프라인 단계(Step) 추가.
- `themes/` 엔진이나 `plotting/` 헬퍼 모듈의 코드 수정.
- CLI 명령어 플래그(`--project`, `--step`, `--strict-lock`, `--force` 등)의 변경 (기존 플래그 100% 유지).

## 4. Constraints
- **Zero External Dependencies**: `hub_core/` 패키지 내의 모듈들은 기존처럼 `PyYAML` 외에 무거운 외부 패키지(예: Airflow, Celery)를 도입하지 않는다.
- **Fail-Fast 유지**: 기존에 에러 발생 시 즉시 `sys.exit(1)`을 하던 구조를, 각 모듈이 예외(Exception)를 던지고 `orchestrator.py` 최상단에서 깔끔하게 잡아 종료하는 구조로 개선한다.
- **상태 관리**: 모듈 간 전역 변수(Global state) 사용을 엄격히 금지하고, 파라미터로 명시적 전달(Dependency Injection)을 수행한다.

## 5. Acceptance Criteria
1. **CLI 호환성**: `python orchestrator.py --project <name> --step all --strict-lock` 명령어가 이전과 토씨 하나 틀리지 않고 동일하게 동작해야 단다.
2. **기능 무결성**: 
   - DVC 해시 및 Lockfile 검증 기능이 정상 작동할 것.
   - `.build_state.json`을 통한 Smart Build (캐시 SKIP/RUN)가 정상 동작할 것.
   - R/Python 서브프로세스 실행 및 출력물(PDF/PNG) 0-byte 검증이 정상 동작할 것.
3. **코드 품질**: `orchestrator.py` 본체는 150줄 이내로 유지되며, 핵심 로직은 `hub_core/` 하위 모듈에 응집되어 있어야 한다.