# 🏛️ 연구 중앙 통제 아키텍처 (Research Central Architecture)

> **목적**: 모든 연구 프로젝트에서 저널급 시각화를 일관되게 생산하는 중앙 데이터 엔지니어링 인프라
> **철학**: *"Data is the API. Quality is Absolute."* — 엄격한 데이터 계약과 환경 통제를 통한 100% 재현성 달성
> **버전**: v4.0 (Modular Phoenix)

---

## 1. 폴더 구조

```
연구/                                       ← Google Drive 연구 루트
│
├── [Graph_making_hub]/                     ← 🏛️ 중앙 통제실
│   ├── orchestrator.py                     ← (Thin Wrapper) CLI 진입점
│   ├── hub_core/                           ← 🧠 핵심 비즈니스 로직 패키지
│   │   ├── config_parser.py                ← YAML 스키마 및 언어 정책 검증
│   │   ├── data_contract.py                ← 시맨틱(논리적) 데이터 무결성 검증
│   │   ├── cache_manager.py                ← Smart Build (.build_state.json) 관리
│   │   ├── provenance.py                   ← DVC, Git, Lockfile 계보 추적
│   │   ├── process_runner.py               ← R/Python 실행 및 환경 주입
│   │   └── utils.py                        ← GDrive Prefetcher 및 공용 유틸
│   │
│   ├── analysis_helpers/                   ← 🧪 공용 분석 라이브러리 (FFT, 물리 보정 등)
│   ├── themes/                             ← 🎨 저널 테마 엔진 (Python/R)
│   ├── plotting/                           ← 📈 공용 플롯 헬퍼
│   ├── data_registry/                      ← DVC 추적용 데이터 스냅샷
│   └── docs/                               ← PDCA 및 기술 문서
│
└── 12. ionoelastomer/                      ← 🔬 개별 연구 프로젝트 (예시)
    ├── project_config.yaml                 ← 이 프로젝트의 지능형 주문서
    ├── .build_state.json                   ← 이 프로젝트의 캐시 상태
    ├── results/                            ← ✅ 파이프라인 결과물 (Data/Figures)
    └── hub_scripts/                        ← Hub 라이브러리를 활용한 정제된 스크립트
```

---

## 2. 5대 핵심 메커니즘

### 2.1 Smart Build (지능형 캐싱)
- `.build_state.json`에 각 단계의 `script + inputs + outputs` 시그니처(mtime+size)를 기록.
- 변경이 없는 단계는 자동으로 **`[SKIP]`** 처리하여 대규모 데이터 처리 시간을 90% 이상 절감.

### 2.2 Semantic Data Contract (논리적 무결성)
- 단순 타입을 넘어 값의 **범위(`range`)**, **결측치 허용 여부(`allow_null`)**, **고유성(`unique`)**을 검증.
- 데이터 오염(실험 오차 등)이 시각화 단계로 유입되는 것을 원천 차단.

### 2.3 GDrive Prefetcher (클라우드 최적화)
- 구글 드라이브 가상 파일 스트리밍 지연으로 인한 멈춤 현상 해결.
- 실행 직전 필요한 입력 파일들을 자동으로 스캔하여 로컬로 소환하고 진행률을 표시.

### 2.4 Provenance & Environment Gate
- 모든 실행 로그에 `Git Commit`, `DVC Status`, `Lockfile Hash`를 기록.
- `--strict-lock` 옵션을 통해 사전에 정의된 패키지 환경과 일치하지 않으면 실행을 거부.

### 2.5 Interactive Selection (사용자 경험)
- 인자 없이 `python orchestrator.py` 실행 시 자동으로 프로젝트 목록을 탐색하여 대화형 메뉴 제공.

---

## 3. 핵심 모듈 상세

### 3.1 `hub_core/data_contract.py`
기초 검증 후 시맨틱 검증 레이어를 순차 실행.
```python
# 검증 레이어 구조
1. File Existence Check (파일 존재 확인)
2. Column Existence & Alias Match (컬럼명 및 .strip() 정규화)
3. Dtype Validation (데이터 타입 검사)
4. Semantic Validation (Range, Null, Unique 논리 검사)
```

### 3.2 `hub_core/utils.py` (Prefetcher)
```python
def ensure_local_files(paths):
    # 가상 파일의 첫 1바이트를 읽어 동기화 유도
    # 디렉토리 수신 시 내부 파일 전체 재귀적 처리
```

---

## 4. `project_config.yaml` 스키마 (v4.0)

```yaml
project: { name: "Project Name", target_journal: "Nature" }
visual_style: { target_format: nature, font_scale: 1.0, profile: baseline }

data_contract:
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["time", "value"]
      dtypes: { time: float, value: float }
      semantic_checks:
        time: { range: [0, 1000], allow_null: false }
        value: { range: [-100, 100], unique: false }

pipeline:
  analysis:
    - script: "hub_scripts/analyze.R"
      lang: R
      inputs: ["data/raw/"]
      cache: true

figures:
  - id: Fig1
    script: "hub_scripts/plot.py"
    output: "results/figures/Fig1.png"
    cache: true
```

---

**Last Update**: 2026-03-05 (Modularized hub_core, Interactive CLI, Semantic Contract, Prefetcher)
