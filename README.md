# 📊 Graph Making Hub

> **Keyword Index for AI Navigation**: See [KEYWORDS.md](./docs/KEYWORDS.md) for indexed physical models, analytical thresholds, and material-property correlations.

> **"Data is the API. Quality is Absolute."**
>  
> 이 허브는 연구 프로젝트의 분석과 그래프 생성을 한 곳에서 실행하고, 결과를 재현 가능하게 관리하는 운영 도구다.

## 누가 무엇을 보면 되나

- 처음 쓰는 사람: 이 README만 먼저 본다.
- 운영 검증을 돌리는 사람: [QA.md](./docs/QA.md)를 본다.
- 내부 구현/이력 확인: [task.md](./task.md), [AGENTS.md](./AGENTS.md)를 본다.
- 라이선스/배포 정책 확인: [LICENSE](./LICENSE), [NOTICE](./NOTICE), [license_distribution_decision_20260609.md](./docs/02-design/license_distribution_decision_20260609.md)를 본다.

## 라이선스 및 배포 상태

Graph Making Hub public-core source is licensed under the Mozilla Public License
2.0 (MPL-2.0). See [LICENSE](./LICENSE) and [NOTICE](./NOTICE) for details.
Project-specific datasets, unpublished workflow notes, credentials, manuscript
assets, and internal style packs are outside this public-core distribution unless
they are explicitly included with their own notices.

## 3단계 시작 가이드

처음에는 아래 3개만 알면 된다.

1. 등록된 프로젝트 보기 및 상태 점검

```bash
# 대화형 목록 보기
python orchestrator.py

# 전체 프로젝트 상태 및 캐시 정합성 점검 (신규)
python orchestrator.py --status
```

2. 마법사 모드로 새 작업 시작하기 (신규)

```bash
# 대화형 마법사를 통해 프로젝트 생성 및 설정
python orchestrator.py --wizard
```

3. 특정 프로젝트 그래프 다시 그리기

```bash
python orchestrator.py --project "12. ionoelastomer" --step plot
```

데이터 분석은 건너뛰고 플롯만 다시 만든다. 일상 작업에서 가장 자주 쓰는 명령이다.
실행 시 **'자가 진단(Self-Diagnosis)'**과 **'시각적 검증(Visual Verification)'** 단계가 자동으로 수행되어 데이터 무결성을 보장한다.

## 매일 쓰는 명령

```bash
# 대화형으로 프로젝트 선택
python orchestrator.py

# 프로젝트 상태 요약 및 미결 과제 확인
python orchestrator.py --status

# 설정 마법사 실행
python orchestrator.py --wizard

# 프로젝트 전체 실행 (자가 진단 포함)
python orchestrator.py --project "프로젝트명" --step all
```

## 권장 사항 (Optional)

더 나은 CLI 경험(컬러 로그, 진행 바, 표 형식 출력)을 위해 `rich` 패키지 설치를 권장한다.
```bash
pip install rich
```

## 핵심 기능

- **Self-Diagnosis & Visual Verification**: 파이프라인 실행 시 입력 데이터의 정합성을 자동으로 진단하고, 출력된 시각적 결과물이 품질 기준(Quality Gateway)을 통과하는지 검증한다.
- **Smart Build**: 바뀌지 않은 analysis/plot/diagram 단계는 다시 계산하지 않는다.

## Multi-Panel Compose Modes

Bridge renderer의 다중 패널 조립은 현재 두 가지 운영 모드를 가진다.

- `draft`
  - `plt.subplots()` 기반의 빠른 조립 경로다.
  - 개별 패널의 절대 mm plot box는 보존되지 않고, composite grid 안에서 재배치된다.
- `manuscript`
  - `fig.add_axes(...)` 기반의 제출용 조립 경로다.
  - 각 패널은 publication layout의 plot box mm 규격을 유지한 채 slot 안에 배치된다.
  - slot이 너무 작으면 조용히 축소하지 않고 에러를 내서 다시 설계하도록 강제한다.
  - 현재는 `standard`, `top_outside`, `right_outside`처럼 고정 geometry가 있는 패널만 허용한다.
  - `smart`, `best` 기반 패널은 manuscript 조립 대상으로 허용하지 않는다.

현재 이 기능은 Graph Hub 내부 API `MultiPanelSpec(compose_mode=...)` 수준에서 제공된다. Athena bridge contract에는 아직 노출되지 않았다.

# 도식만 다시 실행
python orchestrator.py --project "프로젝트명" --step diagrams

# 캐시 무시하고 강제 재실행
python orchestrator.py --project "프로젝트명" --step all --force

# 등록된 프로젝트 목록만 보기
python orchestrator.py --list-projects
```

## 자주 막히는 경우

- `project_config.yaml not found`
  - 프로젝트 루트에 설정 파일이 없다는 뜻이다.
  - 가장 빠른 해결: `python orchestrator.py --init --project "<project>"`

- `Project directory not found`
  - 프로젝트 경로나 이름이 틀렸다는 뜻이다.
  - 먼저 `python orchestrator.py --list-projects`로 실제 이름을 확인한다.

- `Strict mode enabled: missing lockfile(s)`
  - `--strict-lock`는 재현성 검증 모드다.
  - 운영 검증이 목적이면 lockfile을 추가하고, 로컬 확인만 목적이면 일단 `--strict-lock` 없이 실행할 수 있다.

- Google Drive에서 멈추는 것 같음
  - 허브는 입력 파일을 자동 prefetch한다.
  - 그래도 지연되면 Drive 동기화 완료 후 다시 실행한다.

## 운영 상태 라벨

허브 운영에서는 아래 3개 상태를 구분한다.

- `official`
  - `project_config.yaml`로 rerun surface가 닫혀 있고, 공식 analysis/plot 경로가 정의된 상태
- `suspect`
  - raw 또는 intermediate 자산에 이상 신호가 있어 해석은 보수적으로 해야 하지만, 원본은 보존한 채 rerun은 가능한 상태
- `legacy`
  - 과거 자산 또는 참고용 shell이며, 현재 공식 rerun 표면으로 취급하지 않는 상태

프로젝트 문서, 레지스트리, 운영 메모에서는 이 라벨을 같은 의미로 사용한다.

## Input Export Anomaly

analysis 실행 전 허브는 선언된 CSV 입력 헤더를 스캔한다. 현재 공통 경고 대상은 아래 두 가지다.

- blank header
  - 빈 열 이름이 포함된 경우
- duplicate header
  - 같은 열 이름이 중복 저장된 경우

이 경고는 파이프라인을 멈추지 않는다. 대신 아래 운영 원칙으로 처리한다.

1. raw 원본은 즉시 수정하지 않는다.
2. 프로젝트 문서에 `suspect` 또는 `known raw anomaly`로 남긴다.
3. downstream analysis는 계속 돌리되, 해석은 보수적으로 한다.
4. 가능하면 대응 원본 자산에서 재추출해 이상 여부를 확정한다.

조성 비교처럼 그룹 구조가 있는 데이터는 `quality_group_by`를 사용해 pooled CV 대신 그룹별 CV로 품질 경고를 계산하는 것을 권장한다.

## 프로젝트 연결하기

직접 설정하려면 프로젝트 루트에 `project_config.yaml`을 둔다.

```yaml
project: { name: "Ionoelastomer Analysis", target_journal: "Nature" }

data_contract:
  csv_checks:
    - path: "results/data/summary.csv"
      required_columns: ["time", "value", "molarity"]
      dtypes: { time: float, value: float, molarity: number }
      semantic_checks:
        time: { range: [0, 1000], allow_null: false }
        molarity: { range: [0, 50], unique: false }

pipeline:
  analysis:
    - { script: "hub_scripts/analyze.R", lang: R, cache: true }

figures:
  - { id: Fig1, script: "hub_scripts/plot.py", output: "results/figures/Fig1.png", cache: true }

diagrams:
  - { id: DeviceCrossSection, script: "hub_scripts/diagrams/device_cross_section.py", output: "results/figures/device_cross_section.svg", theme: nature, format: svg, cache: true }
```

## 여러 컴퓨터에서 쓸 때 규칙

- 같은 프로젝트는 한 시점에 한 컴퓨터에서만 실행한다.
- Google Drive Desktop 앱 로그인 문제와 Hub 런타임 문제는 별개로 본다.
- DVC 통합은 현재 운영 표면에서 retired 상태다. 되살리기 전까지 `data_registry/`나 DVC 자격증명을 repo 안에 두지 않는다.
- uv/R 런타임 상태는 기본적으로 `RESEARCH_HUB_RUNTIME_ROOT` 또는 사용자 캐시 아래로 분리된다.
- repo 안 자격증명 파일을 공유하지 않는다.

## 운영자용 명령

아래는 매일 쓰는 명령이 아니라 운영 검증용이다.

```bash
# 허브 자체 자동 smoke test
python -m unittest tests.test_smoke

# 전체 등록 프로젝트 회귀 실행
python orchestrator.py --check-all --step all --force --strict-lock

# 현재 산출물을 baseline snapshot으로 저장
python orchestrator.py --check-all --step plot --regression-baseline update

# 도식만 회귀 실행
python orchestrator.py --check-all --step diagrams --strict-lock

# 이후 실행 결과를 baseline과 비교
python orchestrator.py --check-all --step plot --strict-lock --regression-baseline check

# 동일 명령을 Docker 안에서 실행
python orchestrator.py --docker --docker-build --project "프로젝트명" --step all
```

자세한 합격 기준은 [QA.md](./docs/QA.md)에 있다.

## 핵심 기능

- **Smart Build**: 바뀌지 않은 analysis/plot/diagram 단계는 다시 계산하지 않는다.
- **GDrive Prefetcher**: Drive 가상 파일을 실행 직전에 로컬로 확보한다.
- **Environment Gate**: `--strict-lock`에서 Python/R lockfile을 확인하고 provenance에 해시를 남긴다.
- **Check-All Regression**: 등록 프로젝트 전체를 순회하고 런타임 루트의 `hub_logs/check_all_report.json`에 결과를 남긴다.
- **Figure Baseline Regression**: `figures`와 `diagrams` 출력에 대해 `--regression-baseline update/check`로 해시와 diff를 비교한다.
- **Docker Execution**: 같은 명령을 격리된 컨테이너에서 다시 실행할 수 있다.
- **External Runtime State**: uv/R 런타임 상태와 자격증명은 repo 및 Drive 동기화 폴더 밖에서 관리한다.

## 환경 설정 및 이식성 (Environment & Portability)

이 허브는 `uv`를 사용한 가상 환경 관리를 지원한다.

### uv 사용 설정
`project_config.yaml`의 `environment` 섹션에서 `uv_run: true`를 설정하면 모든 Python 실행 명령에 `uv run`이 접두어로 붙는다.
```yaml
environment:
  uv_run: true
```

### uv 실행 래퍼와 외부 가상 환경
허브 루트에 materialized `.venv/`를 만들지 않는다. Graph Hub에서 `uv`를 사용할 때는 bare `uv run` 대신 아래 래퍼를 사용한다.

```bash
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q
```

`hub_uv.py`는 `UV_PROJECT_ENVIRONMENT`와 `UV_CACHE_DIR`를 Graph Hub 외부 runtime root 아래로 고정한다.

기본 위치:

```text
~/Library/Caches/Graph_making_hub/uv_envs/graph-making-hub
~/Library/Caches/Graph_making_hub/uv_cache
```

명시적으로 runtime root를 바꾸려면 실행 전에 `RESEARCH_HUB_RUNTIME_ROOT`를 설정한다.

```bash
RESEARCH_HUB_RUNTIME_ROOT=/Users/choemun-yeong/ws/research-runtime/graph-hub \
  python hub_uv.py run python orchestrator.py --list-projects
```

현재 래퍼가 사용할 경로는 아래 명령으로 확인한다.

```bash
python hub_uv.py --print-env
```

## 시스템 구조

- [orchestrator.py](./orchestrator.py): CLI 진입점
- [hub_core/](./hub_core/): 설정, 검증, 실행, 캐싱 모듈
- [analysis_helpers/](./analysis_helpers/): 공용 분석 헬퍼
- [themes/](./themes/): 저널 테마 및 스타일 프로필
- [plotting/](./plotting/): 공용 플롯 헬퍼

## 관련 문서

- 운영 규약: [AGENTS.md](./AGENTS.md)
- 검증 기준: [QA.md](./docs/QA.md)
- 작업 이력: [task.md](./task.md)

**Last Update**: 2026-06-07 (independent repo cleanup, uv/Docker alignment, docs link repair)
