# 📝 시각화 스크립트 표준 보일러플레이트 (Boilerplate)

개별 프로젝트(`scripts/python`, `scripts/R`)에서 그래프를 그릴 때 최상단에 포함해야 하는 시작 코드입니다.

이 코드는 중앙 스크립트(`orchestrator.py`)가 주입해주는 환경 변수(`THEME_FORMAT`, `THEME_SCALE`, `THEME_PROFILE`)를 받아 테마 엔진 함수에 인자로 넘겨주는 역할을 합니다. 만약 코랩이나 로컬 프롬프트 등, `orchestrator.py`를 거치지 않고 단독 실행될 경우에는 안정적인 기본값(`nature`, `1.0`, `baseline`)으로 동작하도록 설계되었습니다.

---

## 🐍 Python 보일러플레이트 (`script/python/my_plot.py`)

```python
import sys
import os
import matplotlib.pyplot as plt

# 1. 중앙 통제실(Hub) 경로 탐색 및 테마 엔진 로드
# orchestrator가 찔러주는 환경변수가 없다면 상대 경로로 스스로 [Graph_making_hub](Hub)를 찾습니다.
hub_path = os.environ.get('RESEARCH_HUB_PATH', 
                          os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '[Graph_making_hub]')))
sys.path.insert(0, os.path.join(hub_path, 'themes'))

from journal_theme import apply_journal_theme, get_figsize, SINGLE_COLUMN, DOUBLE_COLUMN

# 2. visual_style 주문서 수령 (환경 변수 파싱)
target_format = os.environ.get('THEME_FORMAT', 'nature')
font_scale = float(os.environ.get('THEME_SCALE', '1.0'))
profile_name = os.environ.get('THEME_PROFILE', 'baseline')

# 3. 테마 적용 (순수 함수 호출)
apply_journal_theme(
    target_format=target_format,
    font_scale=font_scale,
    profile_name=profile_name
)

# -------------------------------------------------------------------
# 👇 아래부터는 표준 Matplotlib 코드를 자유롭게 작성합니다.
# -------------------------------------------------------------------

w, h = get_figsize(SINGLE_COLUMN)
fig, ax = plt.subplots(figsize=(w, h))

# ... 플로팅 작업 ...

plt.show() # 또는 plt.savefig()
```

---

## 📊 R 보일러플레이트 (`script/R/my_plot.R`)

```r
library(ggplot2)

# 1. 중앙 통제실(Hub) 경로 탐색 및 테마 엔진 로드
hub_path <- Sys.getenv("RESEARCH_HUB_PATH")
if (hub_path == "") {
  # 단독 실행 시를 위한 Fallback (상대 경로)
  hub_path <- file.path(dirname(dirname(getwd())), "[Graph_making_hub]") 
}
source(file.path(hub_path, "themes", "journal_theme.R"))

# 2. visual_style 주문서 수령 (환경 변수 파싱)
target_format <- Sys.getenv("THEME_FORMAT")
if (target_format == "") target_format <- "nature"

font_scale_str <- Sys.getenv("THEME_SCALE")
if (font_scale_str == "") {
  font_scale <- 1.0
} else {
  font_scale <- as.numeric(font_scale_str)
}

# 3. 내 테마 객체 가져오기 (순수 함수 호출)
my_theme <- theme_journal(target_format = target_format, font_scale = font_scale)

# -------------------------------------------------------------------
# 👇 아래부터는 표준 ggplot2 코드를 작성하고 마지막에 `+ my_theme`를 더해줍니다.
# -------------------------------------------------------------------

# p <- ggplot(data, aes(x=a, y=b)) + geom_point()
# p_styled <- p + my_theme
# save_journal_fig(p_styled, "output.pdf", width_mm = SINGLE_COLUMN, height_mm = 80)
```
