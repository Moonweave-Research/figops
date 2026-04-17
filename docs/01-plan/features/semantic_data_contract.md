# PDCA Plan: Semantic Data Contract

## 1. Feature Info
- **Feature Name**: semantic_data_contract
- **Role**: data-contract-guardian / cto-lead
- **Target Date**: 2026-03-05

## 2. Objective
현재의 데이터 계약(`data_contract.csv_checks`)은 단순히 컬럼의 존재 여부와 데이터 타입(dtype)만 검사한다. 본 작업의 목표는 데이터의 논리적 무결성을 보장하기 위해 **값의 범위(range), 결측치 허용 여부(allow_null), 고유성(unique)** 등 시맨틱(Semantic) 수준의 검증 로직을 추가하는 것이다. 이를 통해 연구 데이터의 이상치나 오염을 파이프라인 초기 단계에서 완벽히 차단한다.

## 3. Scope
### 🟢 Scope In
- `project_config.yaml` 스키마 확장: 각 컬럼별 시맨틱 제약 조건 정의 추가.
- `hub_core/data_contract.py`: 제약 조건(range, allow_null, unique) 검증 엔진 구현.
- 에러 리포팅 강화: 어떤 행(row)에서 어떤 논리적 위반이 발생했는지 구체적으로 출력.

### 🔴 Scope Out
- 복잡한 통계적 이상치(Outlier) 탐지 (예: Z-score, IQR 방식).
- 데이터 자동 보정 (Imputation) 로직.
- 다중 컬럼 간 복합 관계 검증 (예: A > B 조건).

## 4. Constraints
- **Pandas 활용**: 기존 데이터 로드 엔진인 Pandas의 벡터화 연산을 최대한 활용하여 대용량 데이터에서도 검증 속도를 유지한다.
- **Fail-Fast**: 하나라도 시맨틱 위반이 발견되면 즉시 파이프라인을 중단(Exit 1)한다.
- **설정의 유연성**: 모든 제약 조건은 선택 사항(Optional)으로 설계하여 기존 프로젝트와의 하위 호환성을 유지한다.

## 5. Acceptance Criteria
1. `range: [0, 100]`으로 지정된 컬럼에 101이 포함된 경우 검증 실패 및 에러 로그 출력.
2. `allow_null: false`인 컬럼에 NaN이 포함된 경우 검증 실패.
3. `unique: true`인 컬럼에 중복 값이 있는 경우 검증 실패.
4. 새로운 제약 조건이 없는 기존 `project_config.yaml`은 수정 없이도 정상 동작해야 함.
