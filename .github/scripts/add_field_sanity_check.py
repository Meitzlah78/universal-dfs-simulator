from pathlib import Path
p=Path('dfs_app.py'); s=p.read_text()
a='    results_df["AvgPercentile"] = avg_percentiles / selection_n_sims\n\n    if payout_schedule is not None:\n'
b='''    results_df["AvgPercentile"] = avg_percentiles / selection_n_sims

    # Field sanity baseline: 20 random opponent lineups should land near 1/5/10%.
    _sanity_n=min(20,total_field)
    if _sanity_n:
        _rng=np.random.default_rng(20261014); _idx=contest_idx[_rng.choice(total_field,_sanity_n,replace=False)]; _counts=np.zeros(4); _obs=0
        for _start in range(0,selection_n_sims,batch_size):
            _end=min(_start+batch_size,selection_n_sims); _v=simulation_values[_start:_end]; _s=_v[:,_idx].sum(axis=2); _f=_v[:,contest_idx].sum(axis=2)
            if scoring_multiplier != 1.0:
                _s += _v[:,_idx[:,0]]*(scoring_multiplier-1.0); _f += _v[:,contest_idx[:,0]]*(scoring_multiplier-1.0)
            _sorted=np.sort(_f,axis=1); _greater=total_field-np.sum(_sorted[:,:,None] <= _s[:,None,:],axis=1); _pct=1.0-_greater/max(1,total_field)
            _counts += [np.sum(_pct>=.99),np.sum(_pct>=.95),np.sum(_pct>=.90),np.sum(_pct>=.50)]; _obs += _pct.size
        st.session_state["field_sanity_check"]={"Lineups":_sanity_n,"Top 1%":100*_counts[0]/_obs,"Top 5%":100*_counts[1]/_obs,"Top 10%":100*_counts[2]/_obs,"Cash %":100*_counts[3]/_obs}

    if payout_schedule is not None:
'''
if b not in s:
    if a not in s: raise SystemExit('Contest results anchor not found')
    s=s.replace(a,b,1)
c='    scoring_status.success(f"Ranking complete — {len(results_df):,} lineups ranked. Loading your portfolio below.")\n'
d='''    scoring_status.success(f"Ranking complete — {len(results_df):,} lineups ranked. Loading your portfolio below.")
    _sanity=st.session_state.get("field_sanity_check")
    if isinstance(_sanity,dict):
        st.write("### Field Sanity Check")
        st.caption("20 random simulated opponent lineups. Normal baseline: about 1% / 5% / 10% for Top 1 / Top 5 / Top 10.")
        st.dataframe(pd.DataFrame([_sanity]),use_container_width=True,hide_index=True)
'''
if d not in s:
    if c not in s: raise SystemExit('Completion anchor not found')
    s=s.replace(c,d,1)
p.write_text(s)
