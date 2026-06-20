import numpy as np


def add_professional_inset_box(ax, popt, perr, r2, loc=(0.95, 0.65), fontsize=8.5, alpha=0.95):
    """
    Add a high-quality, research-standard fit parameters box using LaTeX.
    Supports both 4-param (no offset) and 5-param (with offset) models.
    """
    has_offset = len(popt) == 5

    if has_offset:
        a_s, tau_s, a_d, tau_d, offset = popt
        a_s_e, tau_s_e, a_d_e, tau_d_e, offset_e = perr

        txt = (r"$\bf{Fit\ Parameters}$:" + "\n"
               f"$R^2 = {r2:.5f}$\n"
               fr"$A_{{shallow}} = {a_s:.1f} \pm {a_s_e:.1f}$ V" + "\n"
               fr"$\tau_{{shallow}} = {tau_s:.1f} \pm {tau_s_e:.1f}$ s" + "\n"
               fr"$A_{{deep}} = {a_d:.1f} \pm {a_d_e:.1f}$ V" + "\n"
               fr"$\tau_{{deep}} = {tau_d:.0f} \pm {tau_d_e:.0f}$ s" + "\n"
               fr"$V_{{offset}} = {offset:.1f} \pm {offset_e:.1f}$ V")
    else:
        a_s, tau_s, a_d, tau_d = popt
        a_s_e, tau_s_e, a_d_e, tau_d_e = perr

        txt = (r"$\bf{Fit\ Parameters}$:" + "\n"
               f"$R^2 = {r2:.5f}$\n"
               fr"$A_{{shallow}} = {a_s:.1f} \pm {a_s_e:.1f}$ V" + "\n"
               fr"$\tau_{{shallow}} = {tau_s:.1f} \pm {tau_s_e:.1f}$ s" + "\n"
               fr"$A_{{deep}} = {a_d:.1f} \pm {a_d_e:.1f}$ V" + "\n"
               fr"$\tau_{{deep}} = {tau_d:.0f} \pm {tau_d_e:.0f}$ s")

    props = dict(boxstyle="round,pad=0.5", facecolor="white", alpha=alpha, edgecolor="#cccccc", lw=0.8)

    ax.text(loc[0], loc[1], txt, transform=ax.transAxes, fontsize=fontsize,
            verticalalignment="top", horizontalalignment="right", bbox=props, linespacing=1.6)

def plot_ispd_time_domain(ax, t, v, popt, perr, r2, sample_name=None,
                         show_components=True, scatter_density=20, **kwargs):
    """
    Standardized ISPD time-domain plot with fit components and parameter box.
    Automatically detects model type (with or without offset).
    """
    from hub_core.ispd_physics import double_exponential_model, double_exponential_with_offset_model

    has_offset = len(popt) == 5
    t_h = t / 3600

    if has_offset:
        a_s, tau_s, a_d, tau_d, offset = popt
    else:
        a_s, tau_s, a_d, tau_d = popt
        offset = 0

    # 1. Raw Data
    ax.scatter(t_h[::scatter_density], v[::scatter_density],
               color="lightgray", s=8, alpha=0.4, label="Raw Data", zorder=1)

    # 2. Total Fit
    if has_offset:
        v_fit = double_exponential_with_offset_model(t, *popt)
    else:
        v_fit = double_exponential_model(t, *popt)

    ax.plot(t_h, v_fit, color="black", lw=2.0, label=r"Total Fit ($V_s + V_d$)", zorder=10)

    # 3. Components
    if show_components:
        ax.plot(t_h, a_s * np.exp(-t/tau_s) + offset, color="#1f77b4", lw=1.8, ls="--",
                label=r"Shallow ($V_s$)", alpha=0.8, zorder=5)
        ax.plot(t_h, a_d * np.exp(-t/tau_d) + offset, color="#d62728", lw=1.8, ls="-.",
                label=r"Deep ($V_d$)", alpha=0.8, zorder=5)

        if has_offset:
            ax.axhline(offset, color="#2ca02c", lw=1.0, ls=":", label=f"Offset ($y_0={offset:.1f}V$)", zorder=2)

    # 4. Professional Inset Box
    add_professional_inset_box(ax, popt, perr, r2)

    # 5. Styling
    ax.set_xlabel("Time (hours)", fontweight="bold")
    ax.set_ylabel("Surface potential (V)", fontweight="bold")
    if sample_name:
        ax.set_title(f"{sample_name} Decay Kinetics", fontsize=12, fontweight="bold")

    ax.legend(loc="upper right", frameon=True, fontsize=8, framealpha=0.8)
    ax.grid(True, alpha=0.2, ls="--")
