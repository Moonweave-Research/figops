import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

def apply_zero_point_adjustment(df, voltage_col="voltage", tail_points=200):
    """
    Perform physical zero-point adjustment based on the mean of the last N points (tail).
    
    Args:
        df (pd.DataFrame): Input dataframe.
        voltage_col (str): Name of the voltage column.
        tail_points (int): Number of points at the end of the series to use for baseline.
        
    Returns:
        pd.DataFrame: Dataframe with adjusted voltage.
        float: The shift value applied (tail_v).
    """
    if len(df) < tail_points:
        tail_points = len(df)
        
    tail_v = np.mean(df[voltage_col].values[-tail_points:])
    df[voltage_col] = df[voltage_col] - tail_v
    return df, tail_v

def double_exponential_model(t, a_s, tau_s, a_d, tau_d):
    """
    Double exponential decay model for ISPD analysis.
    V(t) = a_s * exp(-t/tau_s) + a_d * exp(-t/tau_d)
    """
    return a_s * np.exp(-t/tau_s) + a_d * np.exp(-t/tau_d)

def double_exponential_with_offset_model(t, a_s, tau_s, a_d, tau_d, offset):
    """
    Double exponential decay model with baseline offset for ISPD analysis.
    V(t) = a_s * exp(-t/tau_s) + a_d * exp(-t/tau_d) + offset
    """
    return a_s * np.exp(-t/tau_s) + a_d * np.exp(-t/tau_d) + offset

def fit_ispd_data(t, v, p0=None, bounds=None):
    """
    Fit ISPD data to a double exponential model and return parameters with errors.
    Automatically sorts components into shallow (short tau) and deep (long tau).
    
    Returns:
        tuple: (popt, perr, r2)
               popt: [a_shallow, tau_shallow, a_deep, tau_deep]
               perr: [a_s_err, tau_s_err, a_d_err, tau_d_err]
               r2: R-squared value
    """
    if p0 is None:
        p0 = [v[0]*0.4, 100, v[0]*0.6, 5000]
    
    if bounds is None:
        # Avoid zero tau and negative amplitudes
        bounds = ([0, 0.1, 0, 10], [np.inf, np.inf, np.inf, np.inf])

    # Subsample for stability if data is too dense
    if len(t) > 10000:
        idx = np.linspace(0, len(t)-1, 5000, dtype=int)
        t_fit, v_fit_data = t[idx], v[idx]
    else:
        t_fit, v_fit_data = t, v

    popt, pcov = curve_fit(double_exponential_model, t_fit, v_fit_data, p0=p0, bounds=bounds)
    
    # Sort components by tau: popt[1] is tau_s, popt[3] is tau_d
    if popt[1] > popt[3]:
        popt = [popt[2], popt[3], popt[0], popt[1]]
        pcov = pcov[[2,3,0,1], :][:, [2,3,0,1]]
    
    perr = np.sqrt(np.diag(pcov))
    
    # Calculate R2 on full data
    v_pred = double_exponential_model(t, *popt)
    ss_res = np.sum((v - v_pred)**2)
    ss_tot = np.sum((v - np.mean(v))**2)
    r2 = 1 - (ss_res / ss_tot)
    
    return popt, perr, r2

def fit_ispd_data_with_offset(t, v, p0=None, bounds=None):
    """
    Advanced fit using 5-parameter model (Double Exp + Offset).
    V(t) = a_s * exp(-t/tau_s) + a_d * exp(-t/tau_d) + offset
    
    Returns:
        tuple: (popt, perr, r2)
               popt: [a_s, tau_s, a_d, tau_d, offset]
               perr: [a_s_err, tau_s_err, a_d_err, tau_d_err, offset_err]
               r2: R-squared value
    """
    if p0 is None:
        # Intelligent p0 estimation
        v_min, v_max = np.min(v), np.max(v)
        v_range = v_max - v_min
        p0 = [v_range*0.4, 100, v_range*0.6, 5000, v_min]
    
    if bounds is None:
        # Offset can be negative/positive depending on drift
        bounds = ([0, 0.1, 0, 10, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf])

    # Subsample for stability
    if len(t) > 10000:
        idx = np.linspace(0, len(t)-1, 5000, dtype=int)
        t_fit, v_fit_data = t[idx], v[idx]
    else:
        t_fit, v_fit_data = t, v

    popt, pcov = curve_fit(double_exponential_with_offset_model, t_fit, v_fit_data, p0=p0, bounds=bounds, maxfev=20000)
    
    # Sort by tau
    if popt[1] > popt[3]:
        # swap a1, tau1 with a2, tau2, keep offset at end
        popt = [popt[2], popt[3], popt[0], popt[1], popt[4]]
        pcov = pcov[[2,3,0,1,4], :][:, [2,3,0,1,4]]
    
    perr = np.sqrt(np.diag(pcov))
    
    # Calculate R2
    v_pred = double_exponential_with_offset_model(t, *popt)
    ss_res = np.sum((v - v_pred)**2)
    ss_tot = np.sum((v - np.mean(v))**2)
    r2 = 1 - (ss_res / ss_tot)
    
    return popt, perr, r2

def calculate_trap_density(a, tau, thickness_um, permittivity_r, temperature_k=300):
    """
    Placeholder for trap density calculation logic.
    Actual implementation depends on the specific ISPD-to-Nt model used in the project.
    """
    # TODO: Implement project-specific Nt extraction formula if needed
    pass
