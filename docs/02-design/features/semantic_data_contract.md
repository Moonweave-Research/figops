# PDCA Design: Semantic Data Contract

## 1. Architecture Overview
기존의 `hub_core/data_contract.py`에 포함된 기초 검증(Existence, Dtypes) 단계 뒤에 **시맨틱 검증 레이어(Semantic Validation Layer)**를 추가한다. 이 레이어는 각 컬럼별로 정의된 물리적/논리적 제약 조건을 Pandas의 고성능 연산을 통해 검증하고, 위반 사항 발생 시 상세 리포트를 제공한다.

### YAML Schema Extension
`data_contract.csv_checks` 리스트의 각 항목에 `semantic_checks` 사전을 추가한다.
```yaml
semantic_checks:
  <column_name>:
    range: [<min>, <max>]  # (Optional) 값의 허용 범위 [최소, 최대]
    allow_null: <bool>     # (Optional) 결측치 허용 여부 (default: true)
    unique: <bool>         # (Optional) 값의 고유성 보장 (default: false)
```

## 2. Module Specifications

### 2.1 `hub_core.data_contract` 기능 확장
- **`_validate_semantic_constraints(df, constraints) -> list[str]`** (신설)
  - 입력받은 데이터프레임(`df`)과 제약 조건(`constraints`)을 대조하여 에러 메시지 리스트를 반환한다.
  - **Logic**:
    - `range`: `df[col].min()`과 `df[col].max()`를 체크하여 범위 밖의 값이 있는지 확인. 위반 시 위반값의 개수와 범위를 리포트.
    - `allow_null`: `df[col].isnull().any()`가 참이면 에러 리포트.
    - `unique`: `df[col].is_unique`가 거짓이면 중복된 값의 샘플을 리포트.

### 2.2 `hub_core.config_parser` 검증 로직 추가
- `validate_config` 함수 내에 `semantic_checks` 항목이 올바른 형식을 갖추고 있는지(예: range는 2개 요소의 리스트여야 함 등) 확인하는 로직을 추가한다.

## 3. Data Flow
1. **Load**: `pd.read_csv(..., encoding='utf-8-sig')`로 데이터 로드.
2. **Basic Check**: 컬럼 존재 여부 및 데이터 타입 검사 (기존 로직).
3. **Semantic Check** (New):
   - 설정 파일에 `semantic_checks`가 정의되어 있는지 확인.
   - 각 컬럼별로 `range`, `allow_null`, `unique` 조건 순차 검증.
   - 위반 발견 시 모든 위반 사항을 모아 한 번에 출력하고 `False` 반환.
4. **Final Result**: 모든 게이트 통과 시 파이프라인 지속.

## 4. Error Reporting UI
```text
      ❌ Semantic validation failed for 'displacement_summary.csv':
         - Column 'time': 12 values out of range [0, 1000]. (Max found: 1050.2)
         - Column 'molarity': Null values found (allow_null=false).
         - Column 'id': 3 duplicate values found (unique=true).
```

## 5. Backward Compatibility
- `semantic_checks` 필드가 생략된 기존 프로젝트들은 시맨틱 검증 단계를 자동으로 건너뛰며, 기존의 기초 검증만 수행한다.
- 이로 인해 기존 파이프라인의 하위 호환성이 완벽히 유지된다.
