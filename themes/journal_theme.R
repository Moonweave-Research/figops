# journal_theme.R — Nature/Science (AAAS) Style Definitions
# FigOps journal theme helper
library(ggplot2)

# ── Nature Standard Sizes (mm) ───────────────────────────────────
SINGLE_COLUMN <- 89 # mm
DOUBLE_COLUMN <- 183 # mm

# ── Style Engine (Vending Machine Pattern) ───────────────────────
theme_journal <- function(target_format = "nature", font_scale = 1.0) {
    target_format <- tolower(target_format)

    # 1. 포맷별 기본값 설정 (fallback: nature)
    if (target_format == "ppt") {
        base_size <- 14.0 * font_scale
        line_weight <- 1.5 * (1.0 + (font_scale - 1.0) * 0.7)
        tick_length <- 0.15 * font_scale # PPT는 바깥쪽 틱
    } else {
        # nature, science 공통
        base_size <- 7.0 * font_scale
        line_weight <- 0.5 * (1.0 + (font_scale - 1.0) * 0.7)
        tick_length <- -0.1 * font_scale # Nature는 안쪽 틱
    }

    # 2. 공통 테마 생성
    t <- theme_bw(base_size = base_size, base_family = "sans") %+replace%
        theme(
            plot.title = element_text(size = base_size + 1.5 * font_scale, face = "bold", hjust = 0.5),
            axis.title = element_text(size = base_size + 0.5 * font_scale, face = "bold"),
            axis.text = element_text(size = base_size - 0.5 * font_scale, color = "black"),

            # Legend
            legend.title = element_text(size = base_size - 0.5 * font_scale, face = "bold"),
            legend.text = element_text(size = base_size - 1.0 * font_scale),
            legend.key.size = unit(0.3 * font_scale, "cm"),
            legend.background = element_blank(),
            legend.key = element_blank(),

            # Plot Area
            panel.grid.major = element_blank(),
            panel.grid.minor = element_blank(),
            panel.border = element_rect(color = "black", fill = NA, linewidth = line_weight),

            # Ticks
            axis.ticks = element_line(color = "black", linewidth = line_weight * 0.5),
            axis.ticks.length = unit(tick_length, "cm"),

            # Separation
            panel.spacing = unit(0.5, "lines"),
            plot.margin = margin(5, 5, 5, 5, "mm")
        )

    # 3. PPT 전용 디테일 수정 (top/right 테두리 제거 등)
    if (target_format == "ppt") {
        t <- t + theme(
            panel.border = element_blank(),
            axis.line = element_line(color = "black", linewidth = line_weight)
        )
    }

    return(t)
}

# 하위 호환성을 위한 별칭 설정
theme_nature <- function(base_size = 7) {
    # 기존 코드에서 base_size=7이 기본이므로, font_scale은 base_size / 7 로 계산
    theme_journal(target_format = "nature", font_scale = base_size / 7.0)
}

# ── Palette (palettes.yaml 자동 동기화) ──────────────────────────
# yaml 패키지가 있으면 palettes.yaml에서 로드, 없으면 하드코딩 fallback
.load_wt_colors <- function() {
    # Hub 경로: 환경 변수 > 현재 스크립트와 같은 디렉토리
    hub_path <- Sys.getenv("RESEARCH_HUB_PATH", unset = "")
    candidates <- c(
        file.path(hub_path, "themes", "palettes.yaml"),
        file.path(dirname(sys.frame(1)$ofile), "palettes.yaml"),
        file.path(getwd(), "themes", "palettes.yaml")
    )
    yaml_path <- Find(file.exists, candidates)
    if (!is.null(yaml_path) && requireNamespace("yaml", quietly = TRUE)) {
        data <- yaml::read_yaml(yaml_path)
        wt <- data[["WT_COLORS"]]
        return(unlist(setNames(as.character(wt), names(wt))))
    }
    # Fallback (yaml 패키지 없거나 파일 못 찾을 때)
    c("60" = "#2c3e50", "70" = "#2980b9", "75" = "#e74c3c",
      "80" = "#f39c12", "85" = "#8e44ad")
}
wt_colors <- tryCatch(.load_wt_colors(), error = function(e) {
    c("60" = "#2c3e50", "70" = "#2980b9", "75" = "#e74c3c",
      "80" = "#f39c12", "85" = "#8e44ad")
})

# ── Output Helper ──────────────────────────────────────────────
save_journal_fig <- function(p, filename, width_mm = 89, height_mm = 80) {
    # Deterministic PDF: suppress embedded timestamps during this function scope only.
    old_epoch <- Sys.getenv("SOURCE_DATE_EPOCH", unset = NA)
    Sys.setenv(SOURCE_DATE_EPOCH = "1")
    on.exit({
        if (is.na(old_epoch)) Sys.unsetenv("SOURCE_DATE_EPOCH")
        else Sys.setenv(SOURCE_DATE_EPOCH = old_epoch)
    }, add = TRUE)

    # Save PDF (Vector)
    ggsave(filename, p, width = width_mm, height = height_mm, units = "mm", dpi = 600, device = grDevices::pdf)

    # Save PNG (Raster)
    png_name <- gsub("\\.pdf$", ".png", filename)
    ggsave(png_name, p, width = width_mm, height = height_mm, units = "mm", dpi = 300, device = "png")
}
