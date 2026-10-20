"""Official Underdog NBA X timeline display; never interpreted as lineup data."""
from pathlib import Path


def render_underdog_news(st):
    import streamlit.components.v1 as components
    feed=components.declare_component('simmah_underdog_nba_news',
        path=str(Path(__file__).parent/'components/underdog_nba_news'))
    feed(key='nba_underdog_x_feed',default=None)
