"""Explicitly selected reusable NBA payout templates, independent of slate IDs."""
import json
from pathlib import Path
from simmah_nba_contests import payout_vector


def catalog(platform):
    profiles=json.loads((Path(__file__).parent/'data'/'nba_payscales.json').read_text())['profiles']
    return {key:value for key,value in profiles.items() if value.get('platform') in (None,platform)}


def apply_payscale(profile, selected, day, platform, capacity=None):
    if profile.get('platform') not in (None,platform):
        raise ValueError('Payscale belongs to a different site')
    # Uploaded contest identity and actual fee always win over template metadata.
    result=dict(profile,id=str(selected['id']),name=selected['name'],date=day,
                platform=platform,entry_fee=selected['entry_fee'],
                capacity=profile['capacity'] if capacity is None else capacity)
    payout_vector(result)
    return result


def render_panel(st, contest, selected, day, platform):
    profiles=catalog(platform)
    st.write('### Saved payscales')
    choice=st.selectbox('NBA payscale',['']+list(profiles),
        format_func=lambda key:profiles[key]['name'] if key else 'Use current contest payouts',
        key='nba_payscale_'+platform+'_'+str(selected['id']))
    if not choice:
        if contest is None:
            st.info('Choose the matching NBA payscale above and confirm Full contest capacity. If no saved schedule matches, supply the current contest payout table.')
        return contest
    profile=profiles[choice]
    capacity=st.number_input('Full contest capacity',min_value=profile['payout_tiers'][-1]['last'],
        max_value=1000000,value=profile['capacity'],step=1,
        key='nba_payscale_capacity_'+str(selected['id'])+'_'+choice)
    if capacity is None:
        st.info('Enter the exact full capacity; rounded field sizes cannot be used.')
        return None
    result=apply_payscale(profile,selected,day,platform,int(capacity))
    result['payout_profile_id']=choice
    entry_limit=profile.get('max_entries')
    limit_note=f" · {entry_limit} entries max in the supplied contest" if entry_limit is not None else ''
    st.caption(f"Reusable payout template{limit_note}. Confirm capacity and payouts for this contest. Uploaded contest ID and entry fee are preserved.")
    return result
