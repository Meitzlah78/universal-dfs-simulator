"""Attach the latest entries/late-swap checkpoint without nesting previous packages."""
from hashlib import sha256
import io
import json
import zipfile
from simmah_nba_diagnostics import package_bytes,package_reference,retain_package,_json


def matching_reference(st, context):
    cid=str(context.get('contest_id',''));label=str(context.get('format',''))
    target=None
    nfl=st.session_state.get('diagnostic_package_current')
    if nfl and nfl.get('format')==label and nfl.get('contest_id')==cid:target=nfl
    nba=st.session_state.get('nba_build_result') or {}
    if str(nba.get('contest_id',''))==cid and label.endswith(' NBA'):
        from simmah_nba_rules import rules_for
        if nba.get('pool') is not None and label==rules_for(nba['pool'])['platform']+' NBA':
            target=nba.get('result',{}).get('diagnostic_package')
    return target


def attach_latest_export(st, record, context):
    if context.get('kind','entries') not in {'entries','late_swap'}:return
    target=matching_reference(st,context)
    if not target:return
    cid=str(context.get('contest_id',''))
    # Always use the untouched original build, never a previous combined archive.
    base=target.get('original_build_reference') or {'filename':target['filename'],'digest':target['digest']}
    raw=package_bytes(st,base)
    if raw is None:
        st.warning('Latest export is saved, but its original diagnostic package is awaiting archive recovery.')
        return
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:original=json.loads(bundle.read('manifest.json'))
    export_raw=record['archive']
    manifest={'schema':1,'kind':'calibration_solver_with_latest_export',
        'sport':original.get('sport','NBA'),'platform':original['platform'],'contest_id':cid,
        'captured_at_utc':record['exported_utc'],'original_build_captured_at_utc':original['captured_at_utc'],
        'latest_export_kind':context.get('kind','entries'),'latest_export_id':record['export_id'],
        'submission_verified':False,
        'files':{'original_build.zip':{'sha256':sha256(raw).hexdigest()},
                 'latest_export_checkpoint.zip':{'sha256':sha256(export_raw).hexdigest()}}}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_STORED) as bundle:
        bundle.writestr('manifest.json',_json(manifest))
        bundle.writestr('original_build.zip',raw)
        bundle.writestr('latest_export_checkpoint.zip',export_raw)
        bundle.writestr('README.txt',
            'Send this entire ZIP. original_build.zip preserves the original forecast and scored field.\n'
            'latest_export_checkpoint.zip contains the most recent exported entries or late swap,\n'
            'including its exact export.csv, frozen player pool, available swap/lock details and workspace omissions.\n'
            'An exported CSV is not confirmation it was submitted to the platform.\n')
    name=base['filename'].removesuffix('.zip')+'_Latest_Export_'+record['export_id'][:10]+'.zip'
    package=(name,buf.getvalue(),manifest)
    retain_package(st,package)
    target.update(package_reference(package),original_build_reference=base,
        latest_export_utc=record['exported_utc'],latest_export_kind=context.get('kind','entries'))
