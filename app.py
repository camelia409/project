"""
Streamlit App: Explainable AI Floor Plan Generator — Tamil Nadu
An Explainable AI Framework for Climate-Responsive Building Design
and Sustainable Material Selection in Tamil Nadu · Laurie Baker Principles

Generates 3 variants internally, selects + displays the best one.
Run: streamlit run app.py
"""

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import io, json, pandas as pd
import plotly.graph_objects as go

from engine import (
    generate_best_floor_plan, generate_floor_plan,
    TN_CLIMATE_ZONES, BHK_LAYOUTS, BAKER_PRINCIPLES, FloorPlan
)
from algorithms.genetic_optimizer import run_genetic_optimizer
from tn_plot_standards import (
    TN_STANDARD_PLOTS, MIN_PLOT_WIDTH, MIN_PLOT_DEPTH,
    snap_to_nearest_tn_plot, validate_bhk_for_plot,
)
from renderer import render_floorplan

# ── Multi-Agent Design Intelligence (offline knowledge-based expert system) ───
try:
    from agents.orchestrator import ClientBrief, AgentReport, run_pipeline
    _AGENTS_AVAILABLE = True
except ImportError:
    _AGENTS_AVAILABLE = False

# ── Research data modules ──────────────────────────────────────────────────
from data.nbc_standards import (
    NBC_ROOM_MINIMUMS, NBC_VENTILATION, NBC_CEILING_HEIGHTS,
    FSI_BY_CITY, check_nbc_compliance
)
from data.tn_setbacks import (
    TNCDBR_SETBACKS_BY_PLOT_AREA, CMDA_ROAD_WIDTH_SETBACKS,
    GROUND_COVERAGE_LIMITS, HEIGHT_RESTRICTIONS, compute_usable_area
)
from data.vastu_data import (
    VASTU_ROOM_DIRECTION_SCORES, VASTU_FACING_SCORES,
    VASTU_ZONES, VASTU_ADJACENCY
)
from data.materials_db import (
    MATERIALS_DATABASE, get_material_summary_table, get_materials_for_climate
)
from data.tn_climate_data import (
    STATION_CLIMATE, PASSIVE_STRATEGIES, COMFORT_THRESHOLDS
)

# ── New: BuildingCodeChecker + Decision Tree ──────────────────────────────
from validators.building_code_checker import BuildingCodeChecker
from decision_tree import compute_design_decisions, SOIL_FOUNDATION, BUDGET_MATERIALS

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TN FloorPlan AI",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-title  {font-size:1.9rem;font-weight:800;color:#1A237E;border-bottom:3px solid #E65100;padding-bottom:8px;}
.subtitle    {font-size:0.92rem;color:#666;font-style:italic;margin-bottom:12px;}
.score-card  {background:#F9F9F9;border-radius:8px;padding:10px 14px;
              border-left:4px solid #2E7D32;margin:5px 0;display:flex;justify-content:space-between;}
.score-val   {font-weight:700;}
.baker-box   {background:#FFFDE7;border-radius:6px;padding:8px 12px;margin:4px 0;font-size:0.87rem;}
.xai-box     {background:#E8F5E9;border-radius:6px;padding:8px 12px;margin:4px 0;
              font-size:0.87rem;color:#1B5E20;border-left:3px solid #4CAF50;}
.nbc-box     {background:#E3F2FD;border-radius:6px;padding:8px 12px;margin:4px 0;
              font-size:0.85rem;color:#0D47A1;border-left:3px solid #1565C0;}
.vastu-box   {background:#FFF3E0;border-radius:6px;padding:8px 12px;margin:4px 0;
              font-size:0.85rem;color:#E65100;border-left:3px solid #FF6F00;}
.setback-box {background:#F3E5F5;border-radius:6px;padding:8px 12px;margin:4px 0;
              font-size:0.85rem;color:#4A148C;border-left:3px solid #7B1FA2;}
.mat-box     {background:#E8F5E9;border-radius:6px;padding:8px 12px;margin:4px 0;
              font-size:0.84rem;color:#1B5E20;}
.ref-box     {background:#F5F5F5;border-radius:6px;padding:6px 10px;margin:3px 0;
              font-size:0.78rem;color:#555;border-left:2px solid #BDBDBD;font-style:italic;}
.variant-card{background:#F3F4F6;border-radius:10px;padding:12px;text-align:center;
              border:2px solid #E0E0E0;margin:4px;}
.variant-best{border:2px solid #2E7D32;background:#E8F5E9;}
.badge       {background:#2E7D32;color:white;border-radius:12px;padding:2px 10px;
              font-size:0.78rem;font-weight:700;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class='main-title'>🏛️ AI Floor Plan Generator — Tamil Nadu</div>
<div class='subtitle'>
An Explainable AI Framework for Climate-Responsive Building Design
and Sustainable Material Selection in Tamil Nadu · Laurie Baker Principles<br>
<b>Data Sources:</b> NBC 2016 · TNCDBR 2019 · IMD Climatological Normals 1981–2010 ·
ECBC 2017 · Vastu Manasara · COSTFORD Baker Archives
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏠 Design Parameters")

    # ── 1. Plot ──────────────────────────────────────────────────────────────
    st.markdown("### 📐 Plot")
    c1, c2 = st.columns(2)
    with c1:
        plot_w_raw = st.number_input("Width (m)", 5.0, 30.0, 12.0, 0.5)
    with c2:
        plot_h_raw = st.number_input("Depth (m)", 5.0, 30.0, 15.0, 0.5)

    # ── Snap to nearest TN standard plot ─────────────────────────────────────
    plot_w, plot_h, _was_snapped = snap_to_nearest_tn_plot(plot_w_raw, plot_h_raw)
    if _was_snapped:
        st.info(
            f"Plot snapped to nearest Tamil Nadu standard size: "
            f"**{plot_w:.1f}×{plot_h:.1f} m**. "
            f"Your input {plot_w_raw:.1f}×{plot_h_raw:.1f} m is non-standard."
        )

    plot_area = plot_w * plot_h
    _raw_area = plot_w_raw * plot_h_raw

    # ── Area caption + suitability hint ──────────────────────────────────────
    if _was_snapped:
        st.caption(
            f"**{plot_area:.0f} m²** ({plot_area * 10.764:.0f} sq.ft) "
            f"· original {_raw_area:.0f} m²"
        )
    else:
        st.caption(f"**{plot_area:.0f} m²** ({plot_area * 10.764:.0f} sq.ft)")

    # Suitability hint
    if plot_area < 75:
        _suit = "Suitable for: 1BHK"
    elif plot_area < 135:
        _suit = "Suitable for: 1–2BHK"
    elif plot_area < 200:
        _suit = "Suitable for: 2–3BHK"
    elif plot_area < 300:
        _suit = "Suitable for: 3–4BHK"
    else:
        _suit = "Suitable for: 4BHK / Courtyard layout"

    # Standard TN plot indicator
    _is_std = not _was_snapped   # snap returned False → already standard
    _std_label = "Yes ✓" if _is_std else "No"
    st.caption(f"{_suit} · Standard TN plot: **{_std_label}**")

    ca, cb = st.columns(2)
    with ca:
        district = st.text_input("District / City", value="Chennai")
    with cb:
        road_width = st.selectbox("Road width", [
            "Less than 6m", "6-9m", "9-12m", "12-18m", "More than 18m"
        ])

    # Live setback summary
    sb = compute_usable_area(plot_w, plot_h)
    st.markdown(f"""
    <div class='setback-box'>
    📏 <b>TNCDBR Setbacks</b><br>
    Front: {sb['front_setback_m']}m · Rear: {sb['rear_setback_m']}m · Side: {sb['side_setback_m']}m<br>
    Usable: <b>{sb['usable_width_m']}×{sb['usable_depth_m']} m</b> ({sb['max_footprint_pct']}% of plot)
    </div>
    """, unsafe_allow_html=True)

    # ── 2. Building ──────────────────────────────────────────────────────────
    st.markdown("### 🏡 Building")
    bhk = st.selectbox("BHK Configuration", list(BHK_LAYOUTS.keys()), index=1)

    # BHK validation (warn only — does not block generation)
    _bhk_valid, _bhk_warn = validate_bhk_for_plot(plot_w, plot_h, bhk)
    if not _bhk_valid:
        st.warning(_bhk_warn)

    budget_tier = st.selectbox("Budget", [
        "Economy", "Standard", "Premium"
    ])

    # ── 3. Location & Climate ────────────────────────────────────────────────
    st.markdown("### 🌡️ Climate & Orientation")
    climate_zone = st.selectbox("Tamil Nadu Region", list(TN_CLIMATE_ZONES.keys()), index=0)
    facing = st.selectbox(
        "Main Entrance Direction",
        ["North", "South", "East", "West",
         "North-East", "North-West", "South-East", "South-West"],
        index=0,
    )
    # Live Vastu facing score
    vs = VASTU_FACING_SCORES.get(facing, {})
    vastu_pct = vs.get("score", 50)
    st.markdown(f"""
    <div class='vastu-box'>
    🕉️ <b>Vastu Score: {vastu_pct}/100</b> &nbsp;
    <span style='font-size:0.78rem'>{vs.get('reason','')}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 4. Kitchen & Site ────────────────────────────────────────────────────
    st.markdown("### 🍳 Kitchen & Site")
    cooking_style = st.selectbox("Kitchen style", [
        "Traditional (wet kitchen)", "Modular", "Both"
    ])

    soil_type = st.selectbox("Soil Type (IS 1904)", list(SOIL_FOUNDATION.keys()), index=3)

    # Auto-derive occupancy from BHK
    _BHK_OCC = {"1BHK": 2, "2BHK": 4, "3BHK": 5, "4BHK": 6}
    _bhk_key = bhk.split(" +")[0].strip() if " +" in bhk else bhk.split(" ")[0]
    _default_occ = _BHK_OCC.get(_bhk_key, 4)
    occupancy = st.number_input("Occupancy (persons)", min_value=1, max_value=10,
                                 value=_default_occ, step=1)

    special_zone = st.text_input(
        "Special site condition",
        placeholder="e.g. coastal CRZ, flood-prone, hill station",
    )

    # ── 5. Display ───────────────────────────────────────────────────────────
    st.markdown("### 🖥️ Display")
    ci, cj = st.columns(2)
    with ci:
        show_grid    = st.checkbox("Show 1m grid", True)
    with cj:
        show_compass = st.checkbox("Show compass", True)

    # ── 6. Generate button — runs agents THEN floor plan ─────────────────────
    st.markdown("---")
    gen_btn = st.button(
        "🏗️ Generate Floor Plan & Analysis",
        type="primary",
        use_container_width=True,
        help="Runs 6 expert agents then generates the best floor plan",
    )
    st.caption("Agents analyse your brief → best floor plan is generated → all tabs updated.")

    use_ga = st.toggle(
        "🧬 Genetic Optimizer",
        value=False,
        help="Explores 20×15=300 layout variations and selects the highest-scoring one. Takes ~8 seconds.",
    )

    st.markdown("---")
    st.markdown("""
    #### How it works
    Six offline expert agents (Baker · Climate · Material · Regulatory · Vastu · Arch)
    analyse your brief, then **3 layout variants** are generated and scored on 6 criteria.
    The **highest-scoring layout** is shown with full research-backed analysis across all tabs.
    """)

# ─────────────────────────────────────────────────────────────────────────────
# GENERATION (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
# ── Format-conversion helpers (sidebar display values → agent short codes) ────
_CLIMATE_KEY_MAP = {
    "Coastal (Chennai, Pondicherry, Nagapattinam)":          "hot_humid",
    "Inland Semi-Arid (Madurai, Salem, Trichy)":             "hot_dry",
    "Hilly (Ooty, Kodaikanal, Yercaud)":                     "temperate",
    "Western Ghats Wet (Coimbatore foothills, Tirunelveli)": "composite",
}
_FACING_MAP = {
    "North": "N", "South": "S", "East": "E", "West": "W",
    "North-East": "NE", "North-West": "NW",
    "South-East": "SE", "South-West": "SW",
}

if gen_btn or "fp" not in st.session_state:
    # ── Step 1: Derive special_needs from BHK key (no sidebar checkboxes needed) ─
    special_needs = []
    if "Pooja"     in bhk: special_needs.append("pooja_room")
    if "Office"    in bhk: special_needs.append("home_office")
    if "Courtyard" in bhk: special_needs.append("garden_terrace")

    # ── Step 2: Run 6 offline agents ──────────────────────────────────────────
    if _AGENTS_AVAILABLE:
        agent_brief = ClientBrief(
            family_size=4,
            family_type="Nuclear",
            bhk=bhk.split(" +")[0].strip(),   # base BHK (e.g. "3BHK") for agents
            plot_area=plot_area,
            district=district,
            climate_zone=_CLIMATE_KEY_MAP.get(climate_zone, "hot_humid"),
            facing=_FACING_MAP.get(facing, "N"),
            budget_tier=budget_tier,
            special_needs=special_needs,
            vastu_required=("Pooja" in bhk),
            accessibility=False,
            wants_courtyard=("Courtyard" in bhk),
            cooking_style=cooking_style.split(" ")[0],
            road_width=road_width,
            local_body=None,
            num_floors="Ground floor only",
            special_zone=special_zone or None,
        )

        _agent_status = st.empty()
        def _status(name):
            _agent_status.info(f"⚙️ {name}…")

        with st.spinner("Running 6 expert agents…"):
            agent_report = run_pipeline(agent_brief, status_callback=_status)
        _agent_status.empty()
        st.session_state["agent_report"] = agent_report

    # ── Step 3: BHK key is used DIRECTLY — no override needed ────────────────
    _base_bhk   = bhk.split(" +")[0].strip()
    effective_bhk = bhk if bhk in BHK_LAYOUTS else _base_bhk

    # ── Step 4: Generate floor plan (agent-integrated or genetic optimizer) ───
    _ar_for_engine = st.session_state.get("agent_report", None)

    if use_ga:
        _ga_progress_bar = st.progress(0, text="🧬 Initialising genetic population…")
        _ga_best_holder  = st.empty()

        def _on_ga_progress(gen, total_gens, gen_best, gen_avg):
            pct  = int((gen + 1) / total_gens * 100)
            _ga_progress_bar.progress(
                pct,
                text=f"🧬 Generation {gen + 1}/{total_gens} · best {gen_best:.1f} · avg {gen_avg:.1f}",
            )
            _ga_best_holder.caption(f"Current best score: **{gen_best:.1f}**")

        with st.spinner("🧬 Running genetic optimizer (300 variants)…"):
            best, _ga_score, _ga_history = run_genetic_optimizer(
                plot_w, plot_h, effective_bhk, facing, climate_zone,
                generate_fn=generate_floor_plan,
                score_fn=lambda fp: fp.scores.get("Overall", 0.0),
                progress_callback=_on_ga_progress,
            )

        _ga_progress_bar.empty()
        _ga_best_holder.empty()

        # Fallback: if GA returned None (all evaluations failed) use standard path
        if best is None:
            st.warning("Genetic optimizer could not produce a valid layout — falling back to standard generation.")
            best, all3 = generate_best_floor_plan(
                plot_w, plot_h, effective_bhk, climate_zone, facing,
                agent_report=_ar_for_engine,
                special_needs=special_needs,
            )
        else:
            all3 = [best]   # GA returns single winner; chart replaces variants panel

        # ── Optimization convergence chart ────────────────────────────────────
        if _ga_history:
            gens   = [h[0] + 1 for h in _ga_history]
            bests  = [h[1]     for h in _ga_history]
            avgs   = [h[2]     for h in _ga_history]

            fig_ga = go.Figure()
            fig_ga.add_trace(go.Scatter(
                x=gens, y=bests,
                mode="lines+markers",
                name="Best score",
                line=dict(color="#2E7D32", width=2),
                marker=dict(size=6),
            ))
            fig_ga.add_trace(go.Scatter(
                x=gens, y=avgs,
                mode="lines",
                name="Avg score",
                line=dict(color="#1565C0", width=1.5, dash="dot"),
            ))
            fig_ga.update_layout(
                title="🧬 Genetic Optimizer — Convergence",
                xaxis_title="Generation",
                yaxis_title="Score (0–100)",
                yaxis=dict(range=[0, 100]),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=40, r=20, t=50, b=40),
                height=300,
            )
            st.plotly_chart(fig_ga, use_container_width=True)
            st.caption(
                f"🧬 Genetic optimizer explored **{20 * 15} layout variants** · "
                f"best score: **{_ga_score:.1f}/100**"
            )

        st.session_state["ga_history"] = _ga_history
        st.session_state["ga_score"]   = _ga_score

    else:
        with st.spinner("🔄 Generating 3 layout variants and selecting best…"):
            best, all3 = generate_best_floor_plan(
                plot_w, plot_h, effective_bhk, climate_zone, facing,
                agent_report=_ar_for_engine,
                special_needs=special_needs,
            )

    st.session_state["fp"]   = best
    st.session_state["all3"] = all3

fp: FloorPlan = st.session_state["fp"]
all3          = st.session_state["all3"]
_ar = st.session_state.get("agent_report")

# ── Compliance check + Decision tree (post-generation) ──────────────────
_climate_key_map = {
    "Coastal (Chennai, Pondicherry, Nagapattinam)": "hot_humid",
    "Inland (Madurai, Trichy, Salem)": "hot_dry",
    "Hilly (Ooty, Kodaikanal, Yercaud)": "temperate",
    "Western Ghats (Coimbatore, Valparai, Munnar)": "composite",
}
_ck = _climate_key_map.get(climate_zone, "hot_humid")
_checker = BuildingCodeChecker(
    plot_area=plot_w * plot_h, road_width=road_width,
    plot_width=plot_w, plot_height=plot_h,
    zone="CMDA", occupancy=occupancy,
)
_compliance = _checker.generate_compliance_report(fp.rooms)
_decisions = compute_design_decisions(facing, soil_type, occupancy,
                                       budget_tier, _ck, plot_w * plot_h)

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# NEW 2-TAB STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────
tab_plan, tab_report = st.tabs(["📐 Floor Plan", "📋 Report"])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — FLOOR PLAN
# ═════════════════════════════════════════════════════════════════════════════
with tab_plan:
    st.markdown("### 📐 Best Floor Plan")
    fig = render_floorplan(fp, figsize=(13, 10),
                           show_grid=show_grid, show_compass=show_compass)
    st.pyplot(fig, use_container_width=True)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#F5F0E8")
    buf.seek(0)
    st.download_button(
        "⬇️ Download Floor Plan (PNG)",
        data=buf,
        file_name=f"floorplan_{fp.bhk_type.replace(' ','_')}_{fp.facing}.png",
        mime="image/png",
        use_container_width=True,
    )

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — REPORT
# ═════════════════════════════════════════════════════════════════════════════
with tab_report:
    if _ar is None:
        st.info("👈 Generate a floor plan to see the detailed report")
    else:
        # ─────────────────────────────────────────────────────────────────────
        # SECTION 1 — Design Summary (expanded by default)
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("📊 Section 1 — Design Summary", expanded=True):
            # Project title line
            zone_short = fp.climate_zone.split("(")[0].strip()
            st.markdown(f"### {fp.bhk_type} | {plot_w:.0f}×{plot_h:.0f}m | {zone_short} | {fp.facing} Facing")
            
            # Overall score badge
            ov = fp.scores["Overall"]
            def score_color(v):
                return "#2E7D32" if v >= 75 else "#F57F17" if v >= 50 else "#C62828"
            ov_col = score_color(ov)
            st.markdown(f"""
            <div style='background:{ov_col};color:white;border-radius:10px;padding:12px;
            text-align:center;font-size:1.1rem;font-weight:700;margin:10px 0'>
            Overall Design Score: {ov:.0f} / 100
            </div>""", unsafe_allow_html=True)
            
            # Individual scores as metrics
            score_cols = st.columns(7)
            labels = ["Space Eff", "Aspect R", "Nat Vent", "Climate", "Baker", "NBC", "Circ"]
            keys = ["Space Efficiency", "Aspect Ratio Quality", "Natural Ventilation", "Climate Responsiveness",
                    "Baker Compliance", "NBC Compliance", "Circulation Quality"]
            for i, (col, label, key) in enumerate(zip(score_cols, labels, keys)):
                val = fp.scores.get(key, 0)
                col.metric(label, f"{int(val)}")
            
            # Agent-integrated note
            if getattr(fp, "agent_integrated", False):
                st.info("🤖 Agent-Integrated: Design driven by 6 expert agents + geometric analysis")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 1b — Design Logic Summary (Decision Tree)
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🧠 Design Logic Summary (Input → Output Mapping)", expanded=False):
            dl_rows = [
                {"Input": "Plot Facing", "Value": facing, "Design Decision": f"Prefer glazing on {_decisions['preferred_glazing_wall']} wall, avoid {_decisions['avoid_glazing_wall']}"},
                {"Input": "Soil Type", "Value": soil_type, "Design Decision": f"{_decisions['foundation_type']} @ {_decisions['foundation_depth_m']}m depth"},
                {"Input": "Occupancy", "Value": f"{occupancy} persons", "Design Decision": f"Min exit door {_decisions['exit_door_width_m']}m, corridor {_decisions['corridor_width_m']}m (NBC Part 4)"},
                {"Input": "Budget", "Value": budget_tier, "Design Decision": f"{_decisions['wall_material']} | {_decisions['baker_level']}"},
                {"Input": "Climate", "Value": _ck.replace('_', ' ').title(), "Design Decision": f"Wall U ≤ {_decisions['wall_u_target']}, WWR ≤ {_decisions['wwr_max']}"},
                {"Input": "Roofing", "Value": _decisions['roofing'], "Design Decision": f"Overhang sides: {', '.join(_decisions['overhang_sides'])}"},
            ]
            st.dataframe(pd.DataFrame(dl_rows), use_container_width=True, hide_index=True)
            st.caption(f"Material cost estimate: {_decisions['cost_per_sqft']} | {_decisions['material_note']}")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 2 — Site & Regulatory (with BuildingCodeChecker)
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("📐 Section 2 — Site & Regulatory Compliance", expanded=False):
            # Overall compliance badge
            if _compliance["overall_pass"]:
                st.success("✅ All TNCDBR 2019 + NBC 2016 checks PASSED")
            else:
                st.error(f"❌ {_compliance['violation_count']} violation(s) found")
                for v in _compliance["violations"]:
                    st.markdown(f"- 🔴 {v}")

            # Setbacks
            st.markdown("#### Setbacks (TNCDBR 2019 + CMDA)")
            sb = _compliance["setbacks"]
            setback_data = pd.DataFrame([
                {"Rule": "Front Setback", "Required": f"{sb['front_m']} m", "Source": "Max of TNCDBR Table 1 & CMDA road rule"},
                {"Rule": "Rear Setback", "Required": f"{sb['rear_m']} m", "Source": sb["clause"]},
                {"Rule": "Side Setback (each)", "Required": f"{sb['side_each_m']} m", "Source": sb["clause"]},
            ])
            st.dataframe(setback_data, use_container_width=True, hide_index=True)

            # Ground coverage + FSI
            gc = _compliance["ground_coverage"]
            fsi = _compliance["fsi"]
            osr = _compliance["osr"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Ground Coverage", f"≤ {gc['max_pct']}%", f"{'✅' if gc['compliant'] else '❌'}")
            c2.metric("FSI / FAR", f"{fsi['fsi']}", f"Max {fsi['max_built_up_sqm']} m²")
            c3.metric("OSR Required", "Yes" if osr["required"] else "No",
                       f"{osr['area_sqm']} m²" if osr["required"] else "N/A")

            # Room compliance table
            st.markdown("#### Room-Level NBC Compliance")
            rc_rows = []
            for rc in _compliance["room_compliance"]:
                status = "✅" if rc["compliant"] else "❌"
                rc_rows.append({
                    "Room": rc["room_name"],
                    "Area": f"{rc['area_sqm']} m²",
                    "NBC Min": f"{rc['min_area']} m²" if rc["min_area"] != "N/A" else "—",
                    "Width": f"{rc['width_m']} m",
                    "Min Width": f"{rc['min_width']} m" if rc["min_width"] != "N/A" else "—",
                    "Status": status,
                })
            st.dataframe(pd.DataFrame(rc_rows), use_container_width=True, hide_index=True)

            # Exit requirements
            exits = _compliance["exit_requirements"]
            st.caption(f"Exit requirements (NBC Part 4): Door ≥ {exits['min_exit_door_width_m']}m, Corridor ≥ {exits['min_corridor_width_m']}m for {exits['occupancy']} persons")

            # Clauses cited
            st.caption(f"Clauses cited: {' | '.join(_compliance['clauses_cited'][:5])}")

            if special_zone:
                st.warning(f"⚠️ Special zone condition: {special_zone}")

            if _ar and _ar.regulatory_out:
                if _ar.regulatory_out.warnings:
                    for w in _ar.regulatory_out.warnings[:2]:
                        st.error(w)

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 3 — Room Schedule
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🏠 Section 3 — Room Schedule", expanded=False):
            room_rows = []
            all_pass = True
            for r in fp.rooms:
                real_w = [w for w in r.windows if not w.startswith("vent")
                          and w not in ("open_sky", "via corridor")]
                nbc_result = check_nbc_compliance(r.room_type, r.area, r.width)
                nbc_min = NBC_ROOM_MINIMUMS.get(r.room_type, {}).get("min_area_sqm", "—")
                
                if not nbc_result["compliant"]:
                    all_pass = False
                    status = "❌ FAIL"
                    status_color = "red"
                else:
                    status = "✅ PASS"
                    status_color = "green"
                
                room_rows.append({
                    "Room": r.name,
                    "Area (m²)": f"{r.area:.1f}",
                    "W×D (m)": f"{r.width:.1f}×{r.height:.1f}",
                    "Windows": ", ".join(real_w) or "—",
                    "NBC Min": f"{nbc_min}" if nbc_min != "—" else "—",
                    "Status": status
                })
            
            df_rooms = pd.DataFrame(room_rows)
            st.dataframe(df_rooms, use_container_width=True, hide_index=True)
            
            # Adjacency violations
            if fp.adjacency_violations:
                for violation in fp.adjacency_violations:
                    st.markdown(f"<span style='color:red'>⚠️ {violation}</span>", unsafe_allow_html=True)
            else:
                st.success("✅ All required room adjacencies satisfied")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 4 — Climate & Passive Design
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🌡️ Section 4 — Climate & Passive Design", expanded=False):
            ci = TN_CLIMATE_ZONES[fp.climate_zone]
            
            # Climate zone info
            st.markdown(f"**Climate zone:** {zone_short}")
            st.markdown(f"**Design temperature:** {ci['avg_temp_c']}°C")
            st.markdown(f"**Humidity:** {ci['humidity_pct']}%")
            st.markdown(f"**Wind direction:** {ci['prevailing_wind']}")
            
            # ECBC compliance
            zone_to_station = {
                "Coastal": "Chennai", "Inland": "Madurai",
                "Western": "Coimbatore", "Hilly": "Ooty"
            }
            station_key = next(
                (v for k, v in zone_to_station.items() if k in zone_short), None
            )
            if station_key and station_key in STATION_CLIMATE:
                sd = STATION_CLIMATE[station_key]
                st.markdown(f"**ECBC compliance status:** Zone {sd['ecbc_zone']}")
            
            # Passive strategies from climate agent
            if _ar and _ar.climate_out and _ar.climate_out.recommendations:
                st.markdown("**Passive strategies:**")
                for key, val in list(_ar.climate_out.recommendations.items())[:5]:
                    st.markdown(f"- {key}: {val}")
            else:
                st.markdown("**Passive strategies:**")
                for r in ci["baker_response"][:3]:
                    st.markdown(f"- {r}")
            
            # Window placement rules
            st.markdown(f"**Window placement:** Aligned to prevailing wind ({ci['prevailing_wind']})")
            
            # Overhang recommendation
            climate_type = ci.get("type", "hot_humid").replace("_wet", "")
            ps = PASSIVE_STRATEGIES.get(climate_type, {})
            if ps and "overhang_projection_m" in ps:
                st.markdown(f"**Overhang recommendation:** {ps['overhang_projection_m']} m minimum projection")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 5 — Baker Principles & Materials
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🏛️ Section 5 — Baker Principles & Materials", expanded=False):
            # Baker principles applied
            st.markdown("**Baker principles applied:**")
            for f in fp.baker_features:
                st.markdown(f"- {f}")
            
            # Recommended materials table
            ci = TN_CLIMATE_ZONES[fp.climate_zone]
            climate_type = ci.get("type", "hot_humid").replace("_wet", "")
            mat_rows = get_materials_for_climate(climate_type)
            
            if mat_rows:
                st.markdown("**Recommended materials:**")
                material_data = []
                for m in mat_rows[:5]:  # Top 5 materials
                    material_data.append({
                        "Element": m.get("category", "—"),
                        "Material": m.get("full_name", "—"),
                        "U-Value": f"{m.get('u_value_w_m2k', '—')} W/m²K" if m.get('u_value_w_m2k') != "—" else "—",
                        "Cost/m²": f"₹{m.get('cost_per_sqm_inr_2024', '—')}" if m.get('cost_per_sqm_inr_2024') != "—" else "—",
                        "CO₂ rating": f"{m.get('co2_kg_per_m2_wall', '—')} kg/m²" if m.get('co2_kg_per_m2_wall') != "—" else "—"
                    })
                df_mat = pd.DataFrame(material_data)
                st.dataframe(df_mat, use_container_width=True, hide_index=True)
            
            # Cost savings from baker agent
            if _ar and _ar.baker_out and _ar.baker_out.recommendations:
                if "cost_savings" in _ar.baker_out.recommendations:
                    st.markdown(f"**Cost savings vs conventional RCC:** {_ar.baker_out.recommendations['cost_savings']}")
                elif "estimated_savings" in _ar.baker_out.recommendations:
                    st.markdown(f"**Cost savings vs conventional RCC:** {_ar.baker_out.recommendations['estimated_savings']}")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 6 — Vastu Analysis
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🕉️ Section 6 — Vastu Analysis", expanded=False):
            # Facing direction score
            vs_score = VASTU_FACING_SCORES.get(fp.facing, {})
            vs_pct = vs_score.get("score", 50)
            st.markdown(f"**Facing direction score:** {vs_pct}/100 ({fp.facing} facing)")
            st.markdown(f"**Interpretation:** {vs_score.get('reason', 'Not rated')}")
            
            # Room placement compliance table
            SIDE_TO_DIR = {
                "N": "N", "S": "S", "E": "E", "W": "W",
                "NE": "NE", "NW": "NW", "SE": "SE", "SW": "SW"
            }
            vastu_room_rows = []
            for r in fp.rooms:
                real_wins = [w for w in r.windows if w in SIDE_TO_DIR]
                direction = real_wins[0] if real_wins else "N"
                scores_map = VASTU_ROOM_DIRECTION_SCORES.get(r.room_type, {})
                
                if direction in scores_map:
                    score_5, reason = scores_map[direction]
                    score_100 = score_5 * 20
                    status = "✅ Good" if score_100 >= 60 else "⚠️ Fair"
                else:
                    score_100, reason = 50, "Not rated"
                    status = "— Neutral"
                
                # Find recommended direction
                best_dir = "—"
                best_score = 0
                for d, (s, _) in scores_map.items():
                    if s > best_score:
                        best_score = s
                        best_dir = d
                
                vastu_room_rows.append({
                    "Room": r.name,
                    "Recommended Direction": best_dir,
                    "Actual": direction,
                    "Status": status
                })
            
            df_vastu = pd.DataFrame(vastu_room_rows)
            st.dataframe(df_vastu, use_container_width=True, hide_index=True)
            
            # Critical rules pass/fail
            if vastu_room_rows:
                avg_vastu = sum(
                    80 if "Good" in row["Status"] else 60 if "Fair" in row["Status"] else 50
                    for row in vastu_room_rows
                ) / len(vastu_room_rows)
                if avg_vastu >= 70:
                    st.success(f"✅ Overall Vastu compliance: {avg_vastu:.0f}/100 (Good)")
                elif avg_vastu >= 50:
                    st.warning(f"⚠️ Overall Vastu compliance: {avg_vastu:.0f}/100 (Fair)")
                else:
                    st.error(f"❌ Overall Vastu compliance: {avg_vastu:.0f}/100 (Needs improvement)")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 6b — Room Placement Logic (XAI numbered icons)
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("ℹ️ Room Placement Logic (matches ①②③ icons on plan)", expanded=False):
            _CIRCLED = [chr(0x2460 + i) for i in range(20)]
            idx = 0
            for r in fp.rooms:
                if r.area < 3.0 or r.room_type in ("lightwell", "courtyard"):
                    continue
                icon = _CIRCLED[idx] if idx < len(_CIRCLED) else str(idx + 1)

                # Build explanation from multiple sources
                parts = []

                # NBC compliance
                rc_match = [rc for rc in _compliance["room_compliance"]
                            if rc["room_name"] == r.name]
                if rc_match:
                    rc = rc_match[0]
                    nbc_status = "NBC satisfied" if rc["compliant"] else "NBC FAIL"
                    if rc["min_area"] and rc["min_area"] != "N/A":
                        parts.append(f"{nbc_status} (min {rc['min_area']}m², actual {rc['area_sqm']}m²)")

                # Windows
                real_wins = [w for w in r.windows if not w.startswith("vent")
                             and w not in ("open_sky", "via corridor")]
                if real_wins:
                    parts.append(f"windows: {', '.join(real_wins)}")

                # Jali
                if getattr(r, "jali_recommended", False):
                    parts.append("jali screen recommended for cross-ventilation")

                # Vastu
                vastu_scores = VASTU_ROOM_DIRECTION_SCORES.get(r.room_type, {})
                if vastu_scores:
                    best_dir = max(vastu_scores, key=vastu_scores.get)
                    parts.append(f"Vastu ideal: {best_dir}")

                explanation = " | ".join(parts) if parts else "Standard placement"
                st.markdown(f"**{icon} {r.name.title()}** ({r.area:.1f} m²) — {explanation}")
                idx += 1

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 7 — AI Reasoning (XAI)
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🤖 Section 7 — AI Reasoning (XAI)", expanded=False):
            st.markdown("**Key decisions explained:**")
            
            # Use reasoning_trace from agents if available
            reasoning_items = []
            
            if _ar:
                # Collect reasoning from all agents
                if _ar.climate_out and _ar.climate_out.reasoning_trace:
                    reasoning_items.extend(_ar.climate_out.reasoning_trace[:2])
                if _ar.baker_out and _ar.baker_out.reasoning_trace:
                    reasoning_items.extend(_ar.baker_out.reasoning_trace[:2])
                if _ar.vastu_out and _ar.vastu_out.reasoning_trace:
                    reasoning_items.extend(_ar.vastu_out.reasoning_trace[:2])
                if _ar.arch_out and _ar.arch_out.reasoning_trace:
                    reasoning_items.extend(_ar.arch_out.reasoning_trace[:2])
            
            # Add floor plan explanations
            reasoning_items.extend(fp.explanations[:4])
            
            # Display top 8 most important
            for idx, item in enumerate(reasoning_items[:8], 1):
                st.markdown(f"{idx}. {item}")
            
            if not reasoning_items:
                st.info("Generate a floor plan with agents to see detailed reasoning")

        st.divider()

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 8 — Agent Recommendations
        # ─────────────────────────────────────────────────────────────────────
        with st.expander("🧠 Section 8 — Agent Recommendations", expanded=False):
            if _ar:
                # Baker Agent
                if _ar.baker_out:
                    st.markdown("**🏛️ Baker Agent (Sustainability):**")
                    if _ar.baker_out.summary:
                        st.markdown(_ar.baker_out.summary)
                    if _ar.baker_out.warnings:
                        for w in _ar.baker_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.baker_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.baker_out.references[:3])}</span>", unsafe_allow_html=True)
                    st.markdown("")
                
                # Climate Agent
                if _ar.climate_out:
                    st.markdown("**🌡️ Climate Agent (Passive Design):**")
                    if _ar.climate_out.summary:
                        st.markdown(_ar.climate_out.summary)
                    if _ar.climate_out.warnings:
                        for w in _ar.climate_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.climate_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.climate_out.references[:3])}</span>", unsafe_allow_html=True)
                    st.markdown("")
                
                # Material Agent
                if _ar.material_out:
                    st.markdown("**🧱 Material Agent (Local Sourcing):**")
                    if _ar.material_out.summary:
                        st.markdown(_ar.material_out.summary)
                    if _ar.material_out.warnings:
                        for w in _ar.material_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.material_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.material_out.references[:3])}</span>", unsafe_allow_html=True)
                    st.markdown("")
                
                # Regulatory Agent
                if _ar.regulatory_out:
                    st.markdown("**📋 Regulatory Agent (NBC & TNCDBR):**")
                    if _ar.regulatory_out.summary:
                        st.markdown(_ar.regulatory_out.summary)
                    if _ar.regulatory_out.warnings:
                        for w in _ar.regulatory_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.regulatory_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.regulatory_out.references[:3])}</span>", unsafe_allow_html=True)
                    st.markdown("")
                
                # Vastu Agent
                if _ar.vastu_out:
                    st.markdown("**🕉️ Vastu Agent (Spatial Analysis):**")
                    if _ar.vastu_out.summary:
                        st.markdown(_ar.vastu_out.summary)
                    if _ar.vastu_out.warnings:
                        for w in _ar.vastu_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.vastu_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.vastu_out.references[:3])}</span>", unsafe_allow_html=True)
                    st.markdown("")
                
                # Arch Agent
                if _ar.arch_out:
                    st.markdown("**🎯 Arch Agent (MCDM Synthesis):**")
                    if _ar.arch_out.summary:
                        st.markdown(_ar.arch_out.summary)
                    if _ar.arch_out.warnings:
                        for w in _ar.arch_out.warnings[:2]:
                            st.markdown(f"<span style='color:red'>⚠️ {w}</span>", unsafe_allow_html=True)
                    if _ar.arch_out.references:
                        st.markdown(f"<span style='color:#888;font-size:0.8rem'>Sources: {', '.join(_ar.arch_out.references[:3])}</span>", unsafe_allow_html=True)
            else:
                st.info("Generate a floor plan with agents to see recommendations")


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#999;font-size:0.78rem;padding:8px'>
An Explainable AI Framework for Climate-Responsive Building Design and Sustainable
Material Selection in Tamil Nadu · Laurie Baker Principles ·
NBC 2016 · TNCDBR 2019 · IMD Climatological Data 1981–2010 · Vastu Manasara ·
Squarified Treemap + Orientation-Aware Layout + Climate Rules
</div>
""", unsafe_allow_html=True)
