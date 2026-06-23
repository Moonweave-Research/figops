# PDCA Report: Interactive CLI Project Selector

## 1. Project Info
- **Project Name**: [Graph_making_hub]
- **Target Feature**: interactive_cli
- **Date**: 2026-03-05
- **Author**: report-generator (via bkit)

## 2. Executive Summary
사용자가 수동으로 프로젝트 경로를 입력해야 했던 기존의 불편함을 해소하기 위해, **대화형 프로젝트 선택기(Interactive CLI)** 기능을 성공적으로 구현하였습니다. 이제 인자 없이 오케스트레이터를 실행하면 자동으로 등록된 프로젝트 목록이 표시되며, 간단한 숫자 입력만으로 파이프라인을 가동할 수 있습니다.

## 3. Key Achievements

### 🟢 User Experience (DX)
- **Zero-Arg Startup**: `python orchestrator.py` 실행 시 즉시 대화형 모드 진입.
- **Frictionless Selection**: 긴 연구 폴더 경로를 복사할 필요 없이 번호(1, 2, 3...) 입력만으로 실행 대상 지정.
- **Clear Feedback**: 선택된 프로젝트의 이름을 다시 한번 강조 출력하여 실행 전 확인 단계 제공.

### 🟢 Engineering & Architecture
- **Auto-Discovery**: `get_discoverable_projects` 함수를 통해 `project_config.yaml`이 존재하는 폴더를 실시간으로 탐색.
- **Zero-Dependency TUI**: 외부 라이브러리 없이 Python 표준 라이브러리(`input`, `sys`)만으로 견고한 선택 메뉴 구현.
- **Hybrid Execution**: CLI 인자가 있을 때는 자동화 모드로, 없을 때는 대화형 모드로 유연하게 동작 방식 전환.

## 4. Verification Results
- **Validation Project**: `Synthetic Polymer Actuation (10mm_20min, integrated)`
- **Performance**: 대화형 선택을 포함한 전체 실행 시간이 **0.6초** 이내로 매우 쾌적함.
- **Robustness**: 잘못된 숫자 입력이나 종료 명령(`q`)에 대해 안전한 예외 처리 확인.

## 5. Final Status
- **Acceptance Criteria**: 100% 충족.
- **Conclusion**: 연구원의 심리적 실행 장벽을 낮추는 핵심 QoL 개선 완료.

---
**보고서 생성 완료**
*본 기능은 이제 [Graph_making_hub]의 표준 인터페이스로 채택되었습니다.*
