# [Graph_making_hub]/analysis_helpers/R/signal_processing.R
# ---------------------------------------------------------
# 🏛️ Research Hub - Standard Signal Processing Library
# ---------------------------------------------------------

#' 데이터로부터 지배적인 주파수를 자동으로 감지 (FFT 기반)
#' @param values 신호 값 벡터
#' @param sampling_cycle_s 샘플링 주기 (초)
#' @return 감지된 주파수 (Hz)
detect_frequency_fft <- function(values, sampling_cycle_s) {
  val_centered <- values - mean(values, na.rm = TRUE)
  n <- length(val_centered)
  
  f_res <- fft(val_centered)
  mag <- Mod(f_res)[1:(n/2)]
  freqs <- (0:(n/2-1)) / (n * sampling_cycle_s)
  
  # 0Hz(DC offset)를 제외한 최대 에너지 주파수 탐색
  max_idx <- which.max(mag[2:length(mag)]) + 1
  return(round(freqs[max_idx], 2))
}

#' 상승 Zero-crossing 지점을 찾아 시간/값 영점 조절
#' @param df 'time', 'value' 컬럼을 가진 데이터프레임
#' @param smooth_window 스무딩 윈도우 크기 (노이즈 제거용)
#' @return 정렬된 데이터프레임
align_to_rising_edge <- function(df, smooth_window = 5) {
  # 노이즈에 강한 엣지 탐색을 위해 임시 스무딩
  v_smooth <- as.numeric(filter(df$value, rep(1/smooth_window, smooth_window), sides = 2))
  centered <- v_smooth - mean(v_smooth, na.rm = TRUE)
  
  is_rising <- (centered[-length(centered)] <= 0) & (centered[-1] > 0)
  rising_idxs <- which(is_rising)
  
  if (length(rising_idxs) > 0) {
    # 유효한(NA가 아닌) 첫 번째 상승 지점 선택
    valid_start <- rising_idxs[!is.na(centered[rising_idxs])][1]
    if (!is.na(valid_start)) {
      df <- df[valid_start:nrow(df), ]
      df$time <- df$time - df$time[1]
      df$value <- df$value - df$value[1]
    }
  }
  return(df)
}
