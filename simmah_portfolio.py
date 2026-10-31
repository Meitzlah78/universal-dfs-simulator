"""Portfolio-level display totals; incomplete estimates stay unavailable."""
import numpy as np
import pandas as pd


def portfolio_roi_totals(portfolio, contest=None):
    contest = contest or {}
    count = len(portfolio) if isinstance(portfolio,pd.DataFrame) else 0
    result = dict(entries=count,fees=None,winnings=None,net=None,roi=None)
    if not count:
        return result
    fees = None
    if "Entry Fee ($)" in portfolio:
        values=pd.to_numeric(portfolio["Entry Fee ($)"],errors="coerce")
        if np.isfinite(values).all() and values.ge(0).all():
            fees=float(values.sum())
    if fees is None:
        fee=pd.to_numeric(contest.get("entry_fee",contest.get("entry")),errors="coerce")
        if pd.notna(fee) and np.isfinite(fee) and fee>=0:
            fees=float(fee)*count
    result["fees"]=fees
    if "Expected Prize ($)" not in portfolio:
        return result
    prizes=pd.to_numeric(portfolio["Expected Prize ($)"],errors="coerce")
    if not np.isfinite(prizes).all() or prizes.lt(0).any():
        return result
    result["winnings"]=float(prizes.sum())
    if fees is not None:
        result["net"]=result["winnings"]-fees
        if fees>0:
            result["roi"]=100*result["net"]/fees
    return result
