"""Shared dashboard presentation; no simulation or player-data mutations."""
CSS = '''<style>
:root{--simmah-bg:#0b1119;--simmah-panel:#101b28;--simmah-line:#233346;--simmah-teal:#2dd4bf;--simmah-muted:#97aabd;--simmah-text:#e6edf5}
[data-testid="stAppViewContainer"]{background:#0b1119;color:var(--simmah-text)}
[data-testid="stHeader"]{background:rgba(11,17,25,.96)}
[data-testid="stMainBlockContainer"],section.main>div.block-container{max-width:1640px;padding:3.2rem 1.65rem 3rem!important}
[data-testid="stVerticalBlock"]{gap:.65rem}[data-testid="stHorizontalBlock"]{gap:1.15rem}
h1,h2,h3{color:#f2f6fc;letter-spacing:-.025em}h3{font-size:1.08rem!important;font-weight:650!important;margin:.4rem 0 .3rem!important}
p,label,button,input{font-size:.88rem} [data-testid="stCaptionContainer"]{color:var(--simmah-muted);font-size:.78rem;line-height:1.5}
.simmah-brand{display:flex;align-items:center;gap:.75rem;padding:.25rem 0}.simmah-bars{display:flex;align-items:flex-end;gap:4px;height:28px}.simmah-bars i{display:block;width:5px;background:var(--simmah-teal);border-radius:2px}.simmah-bars i:nth-child(1){height:11px}.simmah-bars i:nth-child(2){height:19px}.simmah-bars i:nth-child(3){height:28px}.simmah-brand-name{font-size:1.5rem;font-weight:800;letter-spacing:.075em;line-height:1;color:#f1f7ff}.simmah-brand-tagline{color:#8b9fb2;font-size:.55rem;letter-spacing:.14em;margin-top:.3rem}.simmah-brand--compact{min-height:42px}
.st-key-simmah_app_header{position:sticky;top:2.8rem;z-index:99;background:rgba(11,17,25,.98);border-bottom:1px solid var(--simmah-line);padding:.45rem 0 .7rem;margin-bottom:.35rem}
.st-key-sticky_projection_bar [data-testid="stHorizontalBlock"]{align-items:center}.st-key-sticky_projection_bar [data-testid="stButton"] button{font-size:.78rem;background:#132331;border-color:#2c4254}.st-key-sticky_projection_bar [data-testid="stButton"] button:hover{border-color:var(--simmah-teal);color:var(--simmah-teal)}
[data-testid="stTabs"] [data-baseweb="tab-list"]{position:relative;gap:4px;padding:5px;border:1px solid var(--simmah-line);border-radius:10px;background:#101b28;margin-bottom:1.2rem;overflow-x:auto}
[data-testid="stTabs"] button[data-baseweb="tab"]{height:42px;padding:0 18px;color:#9eb0c3;border-radius:7px;font-size:.85rem;font-weight:550;white-space:nowrap}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"]{color:#69e3cf;background:#1a353b;font-weight:650}[data-baseweb="tab-highlight"],[data-baseweb="tab-border"]{display:none}
[data-testid="stExpander"]{border:1px solid var(--simmah-line);background:#0f1925;border-radius:9px}[data-testid="stExpander"] summary{font-size:.84rem;min-height:42px}
[data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="textarea"]{background:#111f2e;border-color:#2a4055;border-radius:7px}
[data-testid="stFileUploader"]{background:#101c2a;border:1px dashed #38516a;border-radius:10px;padding:.65rem}.st-key-simmah_slate_setup{border:1px solid var(--simmah-line);background:linear-gradient(125deg,#122233,#0f1925);border-radius:12px;padding:1.15rem;margin-bottom:1rem}
[data-testid="stFileUploaderDropzone"]{background:transparent;padding:.6rem!important;min-height:85px}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border:1px solid #293b4e;border-radius:9px;overflow:hidden}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,[data-testid="stLinkButton"] a{border:1px solid #2b4054;border-radius:7px;background:#152334;color:#e0eaf5;min-height:2.4rem;font-size:.83rem;font-weight:550;transition:border-color .12s,background .12s}
[data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover,[data-testid="stLinkButton"] a:hover{border-color:var(--simmah-teal);background:#173338;color:#82efdd}
[data-testid="stButton"] button[kind="primary"],[data-testid="stDownloadButton"] button[kind="primary"]{background:var(--simmah-teal);border-color:var(--simmah-teal);color:#063c35;font-weight:750}
button:focus-visible,a:focus-visible{outline:2px solid #76e8d8!important;outline-offset:3px}
[data-testid="stMetric"]{background:#101c29;border:1px solid var(--simmah-line);border-radius:10px;padding:.85rem 1rem}[data-testid="stMetricValue"]{font-size:1.5rem;color:#e6edf5}[data-testid="stMetricLabel"]{color:var(--simmah-muted)}
.st-key-simmah_build_panel{position:sticky;top:7.2rem;background:#101c29;border:1px solid #2b4155!important;border-radius:12px;padding:1rem!important;max-height:calc(100dvh - 8.5rem);overflow-y:auto;scrollbar-width:thin}
.st-key-simmah_build_panel [data-testid="stVerticalBlock"]{gap:.45rem}.st-key-simmah_build_panel [data-testid="stCaptionContainer"]{font-size:.74rem}.st-key-simmah_build_panel h3{font-size:1rem!important}.simmah-build-spec{display:flex;gap:6px;flex-wrap:wrap;margin:.25rem 0 .5rem}.simmah-build-spec span{padding:5px 8px;border:1px solid #2b4155;border-radius:5px;color:#a8bacb;font-size:11px}.simmah-step{display:flex;align-items:center;gap:9px;font-size:12px;color:#a6b8ca;margin:.1rem 0 .75rem}.simmah-step b{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;flex:0 0 24px;border:1px solid #315357;border-radius:7px;background:#153033;color:#6ae4d0;font-size:12px}
[data-testid="stAlert"]{border-radius:8px;padding:.7rem .9rem}[data-testid="stAlert"] p{font-size:.84rem}
@media(min-width:1100px){.st-key-simmah_workspace_grid>[data-testid="stVerticalBlock"]>[data-testid="stHorizontalBlock"]{gap:1.5rem}}
@media(max-width:900px){[data-testid="stMainBlockContainer"],section.main>div.block-container{padding:3.1rem .85rem 2rem!important}.st-key-simmah_build_panel{position:static;max-height:none}.st-key-simmah_app_header{top:2.8rem}.st-key-simmah_slate_setup{padding:.85rem}[data-testid="stTabs"] button[data-baseweb="tab"]{padding:0 11px;font-size:.8rem}}
@media(max-width:640px){.simmah-brand-name{font-size:1.15rem}.simmah-brand-tagline{font-size:.44rem}.simmah-bars{height:23px;gap:3px}.simmah-bars i{width:4px}.st-key-sticky_projection_bar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.5rem}.st-key-sticky_projection_bar [data-testid="stColumn"]{min-width:0!important}.st-key-sticky_projection_bar button p{font-size:.68rem!important}.st-key-sticky_projection_bar button{padding:.3rem .55rem!important}[data-testid="stTabs"] [data-baseweb="tab-list"]{gap:0;padding:4px}[data-testid="stTabs"] button[data-baseweb="tab"]{flex:1;min-width:72px;padding:0 8px;font-size:.73rem;white-space:normal;line-height:1.2}.simmah-step{font-size:11px}.st-key-simmah_slate_setup{padding:.75rem}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important}}
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
