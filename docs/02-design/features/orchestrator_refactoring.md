# PDCA Design: Orchestrator Refactoring

## 1. Architecture Overview
기존의 1,300줄짜리 `orchestrator.py`를 기능별로 응집도 높게 분리하여 `hub_core/` 패키지를 신설한다.
새로운 `orchestrator.py`는 단지 Argument Parsing과 `hub_core`의 모듈들을 순차적으로 호출하는 얇은 래퍼(Wrapper) 역할만 수행한다.

### Directory Structure
```text
[Graph_making_hub]/
├── orchestrator.py                 # (Refactored) CLI 진입점 및 고수준 파이프라인 흐름 제어
└── hub_core/                       # (New) 핵심 비즈니스 로직 패키지
    ├── __init__.py
    ├── config_parser.py            # yaml 로드, 스키마 검증, 언어 정책 검증
    ├── data_contract.py            # CSV 컬럼, dtype 검사 로직
    ├── cache_manager.py            # Smart Build (.build_state.json) 상태 관리
    ├── provenance.py               # DVC 해시, Lockfile 환경 해시 추출 및 출력
    ├── process_runner.py           # R, Python 서브프로세스 실행 제어 (run_command)
    └── utils.py                    # 공통 유틸리티 (경로 헬퍼, 파일 무결성 검증 등)
```

## 2. Module Specifications

### 2.1 `hub_core.config_parser`
- `load_config(project_dir) -> tuple[dict, str, str]`
- `_validate_config(config) -> list[str]`
- 책임: `project_config.yaml`을 읽고 예외를 던지며, 스키마가 정확한지 검사한다. 기존의 언어 정책 검증(`_get_language_policy`) 로직을 포함한다.

### 2.2 `hub_core.data_contract`
- `validate_data_contract(project_dir, config) -> bool`
- `_dtype_matches(series, expected, pd) -> bool`
- 책임: `pd.read_csv`를 이용해 컬럼명(.strip() 적용)과 데이터 타입을 검사한다. 

### 2.3 `hub_core.provenance`
- `print_provenance(project_dir, config_path, config_hash, config) -> None`
- `_get_dvc_status(...)`, `_get_lockfile_hash(...)`, `_readable_git_commit(...)`
- 책임: DVC 상태, R/Python 버전을 수집하고 로그를 출력한다. Lockfile의 누락을 검증하는 `--strict-lock` 게이트 로직을 여기에 포함한다.

### 2.4 `hub_core.cache_manager`
- `class SmartBuilder`
  - `__init__(project_dir, force=False)`
  - `load_state()`
  - `is_step_stale(step_type, script_path) -> bool`
  - `update_state(step_type, script_path)`
- 책임: `.build_state.json` 파일을 관리하고, 파일의 `mtime`과 `size`를 바탕으로 실행 여부를 결정한다.

### 2.5 `hub_core.process_runner`
- `run_command(cmd_list, cwd, additional_env=None) -> bool`
- `_resolve_runner(lang, step_cfg, config) -> str`
- 책임: 서브프로세스를 띄우고 실시간으로 stdout을 출력하며, 실패 시 False를 반환한다. (환경변수 주입 포함)

### 2.6 `hub_core.utils`
- `_verify_output_file(output_path) -> tuple[bool, str]`
- `list_projects(...)`
- 책임: PDF/PNG 출력물의 0-byte 검증 및 마법의 문자열(Magic number) 헤더 검사, 프로젝트 탐색.

## 3. Data Flow (Main Pipeline)
`orchestrator.py`의 메인 흐름:
1. `args` 파싱 (`argparse`)
2. `config_parser.load_config()` 호출
3. `provenance.verify_lockfiles()` 및 `print_provenance()` 호출
4. `cache_manager.SmartBuilder` 초기화
5. `Analysis Step`: `cache_manager`에 질의 후 `process_runner` 호출
6. `Contract Step`: `data_contract.validate_data_contract()` 호출
7. `Plot Step`: `cache_manager` 질의 후 `process_runner` 호출 및 `utils._verify_output_file()`로 무결성 검증

## 4. Rollback & Migration Strategy
- `git checkout -b refactor/orchestrator-modularization` 브랜치에서 작업한다.
- 작업 완료 후, 기존 테스트 프로젝트(`10mm_20min_통합_260303`)를 대상으로 `--step all --strict-lock --force`를 실행하여 100% 동일한 출력이 나오는지 확인한다.
