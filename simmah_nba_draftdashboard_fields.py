"""Typed DD attributes; projected MIN semantics explicitly confirmed by the user."""
import numpy as np
import pandas as pd

# Canonical columns stay distinct from ratings and historical summaries.
FIELDS={
 'Projection':(('Projected Points','PRO','Projection'),0,None,'projected fantasy points'),
 'Projected Minutes':(('Projected Minutes','MIN'),0,48,'projected minutes (user-confirmed DD MIN)'),
 'DraftDashboard Usage %':(('Usage Rate %','USE'),0,100,'usage while on the floor'),
 'DraftDashboard DashRank':(('DashRank','DashRank Score'),0,100,'provider rating, not FP or ownership'),
 'DraftDashboard Opponent Defensive Rank':(('Opponent Defensive Rank','Opponent Rank'),1,30,'opponent team defensive rank'),
 'DraftDashboard Position Defensive Rank':(('Opponent Position Defensive Rank','Position Defensive Rank','Position Rank'),1,30,'opponent defensive rank against position'),
 'DraftDashboard Historical FPPG':(('FPPG',),None,None,'historical fantasy points per game'),
 'DraftDashboard FPPM':(('FPPM','PPM'),None,None,'provider fantasy points per minute'),
 'DraftDashboard Chance Hit 5x %':(('Chance To Hit 5x Value %','HIT'),0,100,'probability of reaching five-times salary value'),
 'DraftDashboard Projected Value':(('Projected Value','VAL'),0,None,'projected FP per $1000 salary'),
 'DraftDashboard VS Opponent FP':(('VS OPP',),None,None,'provider player-versus-opponent statistic'),
 'DraftDashboard Game Total':(('Game Total',),0,None,'game total context; does not overwrite trusted market inputs'),
 'DraftDashboard Team Implied Points':(('Team Implied Points',),0,None,'team total context; does not overwrite trusted market inputs'),
}

def apply_fields(pool,frame,keys,pool_keys):
 result=pool.copy(deep=True);applied={}
 for destination,(aliases,lower,upper,meaning) in FIELDS.items():
  columns=[c for c in aliases if c in frame]
  if not columns:continue
  parsed=[]
  for c in columns:
   text=frame[c].astype(str).str.strip()
   if destination.endswith('%'):text=text.str.rstrip('%')
   elif destination=='DraftDashboard Projected Value':text=text.str.rstrip('xX')
   value=pd.to_numeric(text,errors='coerce')
   if not np.isfinite(value).all() or (lower is not None and (value<lower).any()) or (upper is not None and (value>upper).any()):raise ValueError('Invalid DraftDashboard '+c+'; no fields applied')
   if 'Defensive Rank' in destination and not np.equal(value,np.floor(value)).all():raise ValueError('DraftDashboard ranks must be integers')
   parsed.append(value)
  if any(not np.allclose(parsed[0],v,rtol=0,atol=1e-9) for v in parsed[1:]):raise ValueError('Conflicting DraftDashboard aliases for '+destination)
  values=dict(zip(keys,parsed[0]));mapped=pd.Series([values.get(k,np.nan) for k in pool_keys],index=result.index)
  # Missing salary rows (e.g. inactive reserves) retain their original values.
  matched=mapped.notna()
  if destination not in result:result[destination]=np.nan
  result.loc[matched,destination]=mapped[matched]
  if destination=='Projection':
   result.loc[matched,'Projection Source']='DraftDashboard uploaded projection'
  elif destination=='Projected Minutes':
   result.loc[matched,'Minutes Source']='DraftDashboard projected MIN (user confirmed)'
  applied[destination]={'source_column':columns[0],'meaning':meaning}
 if applied:result.attrs['draftdashboard_fields']={'version':1,'fields':applied,'ratings_applied_as_projection_boost':False,'captured_utc':sorted(set(frame.get('Captured UTC',[]))),'source_update_et':sorted(set(frame.get('Source Update ET',[])))}
 return result,applied
