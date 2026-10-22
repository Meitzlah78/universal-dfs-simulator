"""Shared dashboard presentation; no simulation or player-data mutations."""
CSS = '''<style>
:root { --simmah-navy:#061321; --simmah-panel:#0a1c2e; --simmah-line:#193c55; --simmah-teal:#19d3b0; }
[data-testid="stAppViewContainer"] { background: radial-gradient(ellipse at top right,#0c263b 0%,#061321 55%); color:#dbe9f6; }
[data-testid="stHeader"] { background:rgba(6,19,33,.94); }
[data-testid="stMainBlockContainer"],section.main>div.block-container { max-width:1800px; padding:1.1rem 1.5rem 2rem !important; }
[data-testid="stVerticalBlock"] { gap:.55rem; }
[data-testid="stHorizontalBlock"] { gap:1rem; }
h1,h2,h3 { color:#edf7ff; letter-spacing:-.025em; }
h3 { font-size:1.05rem !important; margin:.4rem 0 .15rem !important; }
p,label,button,input { font-size:.82rem; }
[data-testid="stCaptionContainer"] { color:#91aac2; font-size:.74rem; }
.simmah-brand { display:flex; align-items:center; gap:.75rem; padding:.2rem 0 .8rem; border-bottom:1px solid #193c55; margin-bottom:.5rem; }
.simmah-bars { display:flex; align-items:flex-end; gap:4px; height:29px; }
.simmah-bars i { display:block; width:6px; background:#19d3b0; border-radius:2px; box-shadow:0 0 10px #19d3b033; }
.simmah-bars i:nth-child(1){height:12px}.simmah-bars i:nth-child(2){height:21px}.simmah-bars i:nth-child(3){height:29px}
.simmah-brand-name { font-size:1.85rem; font-weight:800; letter-spacing:.07em; line-height:1; color:#f1f7ff; }
.simmah-brand-tagline { color:#90a8be; font-size:.61rem; letter-spacing:.15em; margin-top:.3rem; }
.simmah-brand--compact { padding:0; margin:0; border:0; min-height:34px; gap:.55rem; }
.simmah-brand--compact .simmah-brand-name { font-size:1.35rem; }
.simmah-brand--compact .simmah-brand-tagline { font-size:.48rem; letter-spacing:.12em; margin-top:.2rem; }
.simmah-brand--compact .simmah-bars { height:25px; }
.simmah-brand--compact .simmah-bars i { width:5px; }
.simmah-brand--compact .simmah-bars i:nth-child(1){height:10px}.simmah-brand--compact .simmah-bars i:nth-child(2){height:18px}.simmah-brand--compact .simmah-bars i:nth-child(3){height:25px}
@media(max-width:640px){.simmah-brand--compact .simmah-brand-name{font-size:1rem}.simmah-brand--compact .simmah-brand-tagline{display:none}.simmah-brand--compact{gap:.35rem}}
:is([data-baseweb="tab-list"], [role="tablist"]) { gap:1.4rem; border-bottom:1px solid #193c55; background:transparent; }
:is(button[data-baseweb="tab"], [role="tab"]) { color:#9db2c6; height:42px; font-size:.84rem; padding:0 .25rem; }
:is(button[data-baseweb="tab"], [role="tab"])[aria-selected="true"] { color:#19d3b0; font-weight:700; }
[data-baseweb="tab-highlight"] { background:#19d3b0; height:2px; }
[data-testid="stExpander"] { border:1px solid #193c55; background:#091b2b; border-radius:7px; }
[data-testid="stExpander"] summary { font-size:.8rem; }
[data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="textarea"] { background:#0a1e32; border-color:#23445e; border-radius:5px; }
[data-testid="stFileUploader"] { background:#091b2b; border:1px dashed #23445e; border-radius:7px; padding:.3rem; }
[data-testid="stDataFrame"],[data-testid="stDataEditor"] { border:1px solid #193c55; border-radius:6px; overflow:hidden; }
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stLinkButton"] a { border:1px solid #24516b; border-radius:5px; background:#0b2034; color:#dbe9f6; min-height:2.1rem; font-size:.78rem; }
[data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover { border-color:#19d3b0; color:#19d3b0; }
[data-testid="stButton"] button[kind="primary"],[data-testid="stDownloadButton"] button[kind="primary"] { background:#19d3b0; border-color:#19d3b0; color:#03251f; font-weight:750; }
[data-testid="stMetric"] { background:#0a1c2e; border:1px solid #193c55; border-radius:6px; padding:.65rem; }
[data-testid="stMetricValue"] { font-size:1.25rem; color:#19d3b0; }
.st-key-simmah_build_panel { background:linear-gradient(160deg,#0c2338,#071727); border:1px solid #21435d; border-radius:8px; padding:.75rem; }
@media(min-width:901px) {
 .st-key-simmah_build_panel { position:fixed !important; top:10rem; right:max(1.5rem, calc((100vw - 1800px) / 2 + 1.5rem)); width:calc((100vw - 4rem) * .2252252) !important; max-width:391px; height:calc(100dvh - 11rem); overflow-y:auto !important; overflow-x:hidden; overscroll-behavior:contain; scrollbar-gutter:stable; z-index:980; box-shadow:0 8px 24px #0004; }
}
.st-key-simmah_build_panel [data-testid="stVerticalBlock"] { gap:.4rem; }
.st-key-simmah_build_panel [data-testid="stCaptionContainer"] { font-size:.69rem; }
.st-key-sticky_projection_bar { anchor-name:--simmah-refresh; position:fixed !important; top:3rem; left:50%; transform:translateX(-50%); width:calc(100% - 3rem) !important; max-width:1752px; z-index:990; padding:.45rem .8rem !important; background:rgba(6,19,33,.98) !important; border:1px solid #193c55 !important; border-radius:8px; margin:0 !important; box-shadow:0 5px 16px #0005; }
[data-testid="stMainBlockContainer"],section.main>div.block-container { padding-top:10.5rem !important; }
[data-testid="stTabs"] :is([data-baseweb="tab-list"], [role="tablist"]) { position:fixed !important; top:7rem; left:max(1.5rem, calc((100vw - 1800px) / 2 + 1.5rem)); transform:none; width:calc((100% - 4rem) * .7747748); max-width:1345px; z-index:989; background:#061321 !important; border-bottom:1px solid #193c55; padding:.2rem .6rem; box-shadow:0 5px 12px #0004; }
@media(max-width:640px) { [data-testid="stTabs"] :is([data-baseweb="tab-list"], [role="tablist"]) { left:.5rem; width:calc(100% - 1rem); padding:.15rem; overflow-x:auto; } .st-key-sticky_projection_bar { width:calc(100% - 1rem) !important; padding:.35rem .5rem !important; } .st-key-sticky_projection_bar [data-testid="stHorizontalBlock"] { flex-wrap:nowrap !important; } .st-key-sticky_projection_bar [data-testid="stColumn"] { min-width:0 !important; } .st-key-sticky_projection_bar button p { font-size:.65rem !important; } }
.st-key-sticky_projection_bar [data-testid="stMarkdownContainer"] p { color:#91aac2 !important; font-size:.75rem; }
@media(max-width:900px) {
 [data-testid="stMainBlockContainer"] { padding:10.5rem .7rem 1.2rem !important; }
 .simmah-brand-name { font-size:1.45rem; }
 :is([data-baseweb="tab-list"], [role="tablist"]) { gap:.65rem; }
 :is(button[data-baseweb="tab"], [role="tab"]) { font-size:.74rem; }
}
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none !important; animation:none !important; } }
</style>'''


def render_brand(st, *, compact=False, show_logo=True):
    st.markdown(CSS,unsafe_allow_html=True)
    if not show_logo:return
    brand_class='simmah-brand simmah-brand--compact' if compact else 'simmah-brand'
    st.markdown('''<div class="'''+brand_class+'''" aria-label="Simmah"><div class="simmah-bars" aria-hidden="true"><i></i><i></i><i></i></div><div><div class="simmah-brand-name">SIMMAH</div><div class="simmah-brand-tagline">SIMULATE. BUILD. COMPETE.</div></div></div>''',unsafe_allow_html=True)


def player_columns(frame):
    preferred=['Player' if 'Player' in frame else 'Name','Injury Status','Position','Team','Opponent','Salary','Projection','ProjectionSource',
        'Sim Pts','Sim P10','Sim P95','Projected Ownership','Field Own %','Field CPT Own %',
        'Min Exposure %','Max Exposure %','Captain Min %','Captain Max %','Lock','Fade']
    return [c for c in preferred if c in frame.columns]


def player_column_config(st):
    return {'Salary':st.column_config.NumberColumn('Salary',format='$%d'),
        'Projection':st.column_config.NumberColumn('Proj Pts',format='%.1f'),
        'Sim Pts':st.column_config.NumberColumn('Sim Pts',format='%.1f'),
        'Sim P10':st.column_config.NumberColumn('Floor (P10)',format='%.1f'),
        'Sim P95':st.column_config.NumberColumn('Ceiling (P95)',format='%.1f')}


def render_diversity_controls(st, platform, mode, simulation_count):
    """Portfolio exposure choice is independent of construction-scenario choice."""
    value = st.slider("Lineup exposure diversity",0,100,50,step=5,
        key=f"portfolio_exposure_diversity_{platform}_{mode}_v1",
        help="Higher settings spread player exposure and penalize similar rosters in the final portfolio. Manual exposure limits and player locks remain authoritative. Changing this reselects existing candidates; it does not reduce simulation counts.")
    cap=100-.4*value
    st.caption(f"Preferred player exposure cap: {cap:.0f}%. Automatic limits may relax if needed to fill entries; manual limits stay enforced.")
    with st.expander("Advanced: candidate construction",expanded=False):
        scenario=st.slider("Game-scenario construction",0,100,
            100 if mode in ("Showdown","Single Game") else 50,step=5,
            key=f"lineup_build_aggressiveness_{platform}_{mode}",
            help="Separate from final lineup exposure. Higher settings build candidates from fewer joint construction scenarios. Only affects newly built candidates.")
        st.caption(f"Each candidate averages {max(1,round(simulation_count**(1-scenario/100))):,} construction scenarios. Contest evaluation retains the full simulation set.")
    return value,scenario/100
