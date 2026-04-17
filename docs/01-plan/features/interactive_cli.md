# PDCA Plan: Interactive CLI Project Selector

## 1. Feature Info
- **Feature Name**: interactive_cli
- **Role**: cto-lead / frontend-architect
- **Target Date**: 2026-03-05

## 2. Objective
사용자가 `--project` 인자를 일일이 입력하거나 복사-붙여넣기 하는 수고를 덜어주기 위해, 인자 없이 `python orchestrator.py`를 실행했을 때 현재 연구 루트에 등록된 모든 프로젝트 목록을 터미널에 띄우고 방향키나 번호로 선택할 수 있는 **대화형 인터페이스(Interactive CLI)**를 구현한다.

## 3. Scope
### 🟢 Scope In
- `orchestrator.py` 진입점 수정: 필수 인자(`--project`) 누락 시 즉시 종료하는 대신 대화형 모드(Selection Mode)로 전환.
- `hub_core/utils.py` 또는 `config_parser.py`: 현재 시스템에 등록된(Config가 존재하는) 프로젝트 리스트를 수집하는 기능 강화.
- 터미널 UI 구현: 선택 메뉴 출력, 사용자 입력(키보드) 처리, 선택된 프로젝트 경로 반환.

### 🔴 Scope Out
- GUI(윈도우 창) 구현.
- 프로젝트 자동 생성(`--init`) 기능 (별도 태스크로 분리).
- 복수 프로젝트 동시 선택 (Single selection만 우선 지원).

## 4. Constraints
- **Zero External Dependencies**: `inquirer`나 `pick` 같은 외부 라이브러리 없이, 최대한 Python 표준 라이브러리만 사용하여 **이식성**을 유지한다. (필요시 간단한 ANSI escape code 기반의 메뉴 로직 구현)
- **Backward Compatibility**: 기존의 `--project "path"` 방식은 그대로 유지되어야 하며, 자동화 스크립트 실행에 방해가 되지 않아야 함.

## 5. Acceptance Criteria
1. `python orchestrator.py` 실행 시 등록된 프로젝트 목록이 번호와 함께 출력되어야 한다.
2. 사용자가 번호를 입력하거나 방향키(구현 난이도 고려 후 결정)를 통해 프로젝트를 선택하면 해당 프로젝트 파이프라인이 즉시 시작되어야 한다.
3. 프로젝트가 하나도 없을 경우 친절한 안내 메시지를 출력하고 종료해야 한다.
4. `--project` 인자가 주어지면 대화형 모드를 건너뛰고 바로 실행되어야 한다.
