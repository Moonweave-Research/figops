# [Graph_making_hub]/analysis_helpers/R/material_physics.R
# ---------------------------------------------------------
# 🏛️ Research Hub - Material Physics & Resistivity Library
# ---------------------------------------------------------

#' 측정 저항을 비저항(Resistivity)으로 변환
#' @param resistance 측정된 저항값 (Ohm)
#' @param area 전극 면적 (cm^2)
#' @param thickness_um 시편 두께 (um)
#' @param thickness_correction 두께 보정값 (um)
#' @return 비저항 (Ohm * cm)
calc_resistivity <- function(resistance, area, thickness_um, thickness_correction = 20) {
  t_cm <- (thickness_um - thickness_correction) * 1e-4
  return(resistance * (area / t_cm))
}

#' Curie-von Schweidler (CvS) 지수 추출 (n-value)
#' @param time 시간 벡터
#' @param current_proxy 전류에 비례하는 값 (예: 1/Resistivity)
#' @param start_time 시작 시간 (s)
#' @param end_time 종료 시간 (s)
#' @return Trapping Exponent (n)
extract_cvs_exponent <- function(time, current_proxy, start_time = 10, end_time = 100) {
  # 특정 구간(Regime) 필터링
  mask <- time >= start_time & time <= end_time
  t_sub <- time[mask]
  i_sub <- current_proxy[mask]
  
  if (length(t_sub) < 5) return(NA_real_)
  
  # Log-log 선형 회귀 (I ~ t^-n  => log(I) ~ -n * log(t))
  fit <- lm(log10(i_sub) ~ log10(t_sub))
  n_val <- -as.numeric(coef(fit)[2])
  return(n_val)
}

#' 품질 관리(QC): 단조성 및 데이터 무결성 검사
#' @param values 데이터 벡터
#' @param min_points 최소 필요 데이터 개수
#' @return 논리값 (TRUE if passed)
is_valid_trend <- function(values, min_points = 200) {
  if (length(values) < min_points) return(FALSE)
  
  # 기본적으로 시작보다 끝이 높아야 함 (저항 증가 케이스)
  initial_val <- mean(head(values, 10), na.rm = TRUE)
  final_val   <- mean(tail(values, 10), na.rm = TRUE)
  
  return(final_val > initial_val)
}
