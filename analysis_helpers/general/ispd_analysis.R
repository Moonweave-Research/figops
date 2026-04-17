#' ISPD (Intelligent Surface Potential Decay) Analysis Module
#'
#' @tags ISPD_ANALYSIS, TRAP_MERGE_THRESHOLD, BIMODAL_TRAP_SIGNATURE, ENERGY_MAPPING
#' @model Vs(t) = a*exp(b*t) + c*exp(d*t)
#' Methods for trap density analysis from surface potential decay.
#' Ref: K. Liu et al., Small Methods, 8, 2301755 (2024)

#' Calculate Trap Density from Double Exponential Parameters
#'
#' @param t Time in seconds
#' @param params Named vector with a, b, c_amp, d
#' @param prefactor Physical prefactor (eps0*epsr / (q*L^2*kB*T*f0))
#' @return A data frame with Energy, Total, Shallow, and Deep trap densities
calc_ispd_trap_density <- function(t, params, prefactor, nu = 1e12, T_K = 300) {
    kB <- 1.380649e-23
    q_e <- 1.602e-19

    a <- params["a"]
    b <- params["b"]
    c <- params["c_amp"]
    d <- params["d"]

    # Energy: E = kB*T*ln(nu*t) [converted to eV]
    E <- (kB * T_K / q_e) * log(nu * t)

    # dVs/dt for shallow and deep components
    dVdt_shallow <- a * b * exp(b * t)
    dVdt_deep <- c * d * exp(d * t)

    # Nt(E) = prefactor * |t * dVs/dt|
    Nt_shallow <- prefactor * abs(t * dVdt_shallow)
    Nt_deep <- prefactor * abs(t * dVdt_deep)
    Nt_total <- Nt_shallow + Nt_deep

    return(data.frame(
        Energy  = E,
        Total   = Nt_total,
        Shallow = Nt_shallow,
        Deep    = Nt_deep
    ))
}

#' Standard Double Exponential Fitting for ISPD
#'
#' @param data Data frame with t_rel and V_volt
#' @param start_list Initial guesses
#' @return NLS fit coefficients
fit_ispd_double_exp <- function(data, start_list = NULL) {
    V0 <- max(data$V_volt)
    if (is.null(start_list)) {
        start_list <- list(
            a     = V0 * 0.9,
            b     = -1 / 15000,
            c_amp = V0 * 0.1,
            d     = -1 / 80000
        )
    }

    fit <- nls(V_volt ~ a * exp(b * t_rel) + c_amp * exp(d * t_rel),
        data = data,
        start = start_list,
        algorithm = "port",
        lower = c(a = 0.01, b = -1 / 1800, c_amp = 0.001, d = -1 / 36000),
        upper = c(a = 3.0, b = -1 / 28800, c_amp = 1.0, d = -1 / 360000),
        control = nls.control(maxiter = 10000, warnOnly = TRUE)
    )

    return(coef(fit))
}

#' Double Gaussian Fitting for Energy-domain Trap Density
#'
#' @param data Data frame with Energy and Total
#' @param init_vals Initial guesses for A1, mu1, sigma1, A2, mu2, sigma2
#' @return NLS fit coefficients
fit_ispd_energy_gauss2 <- function(data, init_vals = NULL) {
    if (is.null(init_vals)) {
        init_vals <- list(
            A1 = 2.0, mu1 = 1.03, sigma1 = 0.02,
            A2 = 0.2, mu2 = 1.07, sigma2 = 0.02
        )
    }

    # Defined Gauss2 locally for nls
    gauss2_formula <- Total ~ A1 * exp(-0.5 * ((Energy - mu1) / sigma1)^2) +
        A2 * exp(-0.5 * ((Energy - mu2) / sigma2)^2)

    lower_b <- c(A1 = 0.0, mu1 = 0.95, sigma1 = 0.005, A2 = 0.0, mu2 = 1.05, sigma2 = 0.005)
    upper_b <- c(A1 = 5.0, mu1 = 1.045, sigma1 = 0.1, A2 = 5.0, mu2 = 1.15, sigma2 = 0.1)

    fit <- nls(gauss2_formula,
        data = data,
        start = init_vals,
        algorithm = "port",
        lower = lower_b,
        upper = upper_b,
        control = nls.control(maxiter = 1000, warnOnly = TRUE)
    )

    return(coef(fit))
}
