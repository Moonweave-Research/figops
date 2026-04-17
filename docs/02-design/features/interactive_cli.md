# PDCA Design: Interactive CLI Project Selector

## 1. Architecture Overview
기존의 CLI 인자 중심 구조를 유지하면서, 사용자 입력이 없을 때만 활성화되는 **대화형 선택 레이어(Selection Layer)**를 추가한다. 외부 의존성을 배제하기 위해 Python의 `input()`과 표준 출력을 활용한 'Numeric Selection' 방식을 채택한다.

### Components & Changes
- `hub_core/config_parser.py`: 프로젝트 목록을 데이터 형태로 반환하는 함수 추가.
- `hub_core/utils.py`: 표준 입력 기반의 대화형 선택 유틸리티 함수 추가.
- `orchestrator.py`: 프로젝트 인자가 없을 때 유효한 프로젝트 목록을 탐색하고 사용자 선택을 유도하는 흐름 제어 로직 추가.

## 2. Module Specifications

### 2.1 `hub_core.config_parser` 확장
- **`get_discoverable_projects(root_dir, max_depth=4) -> list[dict]`**
  - 기존 `list_projects`의 로직을 재사용하여 발견된 프로젝트의 `name`, `rel_path`, `config_path`를 리스트 형태로 반환한다.
  - 반환값 예시: `[{'name': 'Ionoelastomer...', 'path': '12. ionoelastomer'}, ...]`

### 2.2 `hub_core.utils` 신설/확장
- **`prompt_numeric_selection(options: list, header: str) -> int`**
  - 화면에 리스트를 번호와 함께 출력한다.
  - 사용자로부터 정수를 입력받고, 유효한 범위 내인지 검증한다.
  - 잘못된 입력 시 재입력을 요청하거나 종료할 수 있는 인터페이스를 제공한다.

### 2.3 `orchestrator.py` 로직 변경
- **조건부 실행**:
  ```python
  if not args.project and not args.list_projects:
      projects = get_discoverable_projects(root_dir)
      if not projects:
          print("❌ No configured projects found.")
          sys.exit(1)
      
      selected_idx = prompt_numeric_selection([p['name'] for p in projects], "Select a Project to Run")
      args.project = projects[selected_idx]['path']
  ```

## 3. Data Flow
1. `orchestrator.py` 실행 (인자 없음).
2. `config_parser`가 연구 루트 폴더를 스캔하여 `project_config.yaml`이 있는 폴더들을 수집.
3. `utils.prompt_numeric_selection`이 터미널에 목록을 표시.
4. 사용자가 번호 입력.
5. 선택된 경로가 `args.project`에 주입되어 기존 파이프라인 흐름을 그대로 수행.

## 4. UI Design (Draft)
```text
🏛️ Research Central Orchestrator
------------------------------------------------------------
Available Projects:
 [1] Ionoelastomer Displacement Analysis (12. ionoelastomer)
 [2] Sulfur-rich Polymer Actuation (8. Surfur.../10mm_20min)
 [3] Resistance Analysis (8. Surfur.../저항 측정/260130)

Enter project number (or 'q' to quit): _
```

## 5. Migration & Compatibility
- 기존의 `--project` 인자를 사용하는 모든 자동화 쉘 스크립트나 DVC 파이프라인은 100% 동일하게 동작함 (인자가 있으면 대화형 모드는 발동하지 않음).
- Python 3.8+ 표준 라이브러리만 사용하므로 추가 `pip install`이 필요 없음.
