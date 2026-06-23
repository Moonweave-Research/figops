# Architecture: [Graph_making_hub]

This document outlines the core structural components and their responsibilities within the Research Hub.

## Directory Structure & Modules

### 1. `hub_core` (Core Logic)
The engine of the Hub, responsible for lifecycle management and project orchestration.
- **Config Parsing**: Robust handling of project-level YAML/JSON configurations.
- **Health & Diagnosis**: `health_check.py` provides self-diagnosis tools for input data integrity and environment health.
- **Scaffolding**: `scaffold.py` manages project initialization and configuration via the interactive wizard.
- **Intelligent Caching**: Content-aware caching of intermediate results to skip redundant computations.
- **Execution Engine**: Parallel execution of analysis and plotting pipelines with full environment isolation.
- **Regression Suite**:
    - `visual_regression.py`: Figure and PDF visual similarity checking.
    - `data_regression.py`: Numeric drift detection for CSV/Parquet/TSV datasets.

## Technical Principles

### Visual Quality Gateway (시각적 품질 게이트웨이)
플롯이나 도식이 생성된 직후, 사전 정의된 '시큐리티 & 스타일 가이드'에 따라 렌더링 결과물을 검증한다. 해상도, 폰트 임베딩 여부, 저널 테마 준수 여부를 확인하여 최종 승인 전까지 산출물을 잠금 상태로 유지한다.

### Atomic Cache Update (원자적 캐시 업데이트)
파이프라인의 각 단계가 100% 성공적으로 완료되었을 때만 전역 캐시를 갱신한다. 네트워크 장애나 실행 중단으로 인한 캐시 오염을 방지하기 위해 임시 스테이징 영역에서 검증 후 원자적으로 메인 메타데이터에 반영한다.

### 2. `plotting` (Standardized Visualization)
Matplotlib-based visualization helpers designed for publication-quality output.
- **Standardization**: Consistent fonts, line weights, and color schemes for public journal formats.
- **Layout Helpers**: Tools for multi-panel figures and complex subplots.

### 3. `analysis_helpers` (Domain-Specific Scripts)
Domain-specific analysis logic, categorized by scientific field.
- `physics/`: Scripts for material properties, thermal analysis, and structural mechanics.
- `general/`: Generic signal processing, data cleaning, and statistical analysis tools.

### 4. `themes` (Journal Style Presets)
Styling configurations that drive the visual consistency of the `plotting` module.
- **Presets**: CSS/Matplotlib rcParams for public journal formats.
- **Color Palettes**: Color-blind friendly and high-contrast palettes.
