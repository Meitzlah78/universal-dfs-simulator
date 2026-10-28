"""Private, integrity-checked S3 workspaces with reusable ZIP-entry segments."""
import io
import json
import zipfile
from simmah_input_archive import S3Backup
from simmah_workspace_backup import MAX_BYTES, digest, unpack, write_backup


def configuration(st):
    try:
        config = dict(st.secrets.get('input_archive', {}))
    except (FileNotFoundError, KeyError, AttributeError):
        return None
    return config if config.get('bucket') else None


def available(backup, owner, key, expected):
    from botocore.exceptions import ClientError
    try:
        response = backup.client.head_object(Bucket=backup.bucket,
            Key=f'{backup.prefix}/{owner}/{key}')
        return response.get('Metadata', {}).get('sha256') == expected
    except ClientError as exc:
        if str(exc.response.get('Error', {}).get('Code')) in {'403','AccessDenied','404','NoSuchKey','NotFound'}:
            return False
        raise


def save(config, owner, raw, reference):
    backup = S3Backup(config)
    # ZIP local entries contain no absolute offsets. Settings change their own
    # small entry; unchanged matrices/archives keep identical compressed bytes.
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        boundaries = sorted({0, bundle.start_dir, len(raw)} |
                            {info.header_offset for info in bundle.infolist()})
    parts = []
    uploaded = reused = 0
    for start, end in zip(boundaries, boundaries[1:]):
        part = memoryview(raw)[start:end]
        hashed = digest(part)
        key = 'workspaces/parts/'+hashed
        if not available(backup, owner, key, hashed):
            backup.put(owner, key, bytes(part))
            uploaded += len(part)
        else:
            reused += len(part)
        parts.append(dict(hash=hashed, bytes=end-start))
    index = json.dumps(dict(schema=1, digest=reference['digest'], bytes=len(raw), parts=parts),
                       separators=(',', ':')).encode()
    key = 'workspaces/index/'+digest(index)+'.json'
    backup.put(owner, key, index)
    # A read-back proves this identity can both write and read this exact index.
    if backup.get(owner, key) != index:
        raise ValueError('Cloud workspace read-back failed')
    return dict(reference, cloud_ok=True, cloud_key=key, cloud_digest=digest(index),
                cloud_uploaded_bytes=uploaded+len(index), cloud_reused_bytes=reused)


def restore(config, owner, reference):
    backup = S3Backup(config)
    raw_index = backup.get(owner, reference['cloud_key'])
    if digest(raw_index) != reference['cloud_digest']:
        raise ValueError('Cloud workspace index failed verification')
    index = json.loads(raw_index)
    if (index.get('schema') != 1 or index.get('digest') != reference['digest']
            or index.get('bytes') != reference['bytes']
            or type(index['bytes']) is not int or not 0 < index['bytes'] <= MAX_BYTES
            or not isinstance(index.get('parts'), list) or len(index['parts']) > 20002):
        raise ValueError('Invalid cloud workspace index')
    import re
    if any(not re.fullmatch('[a-f0-9]{64}', str(p.get('hash')))
           or type(p.get('bytes')) is not int or p['bytes'] <= 0 for p in index['parts']):
        raise ValueError('Invalid cloud workspace segment')
    if sum(p['bytes'] for p in index['parts']) != index['bytes']:
        raise ValueError('Invalid cloud workspace size')
    stream = io.BytesIO()
    for part in index['parts']:
        raw = backup.get(owner, 'workspaces/parts/'+part['hash'])
        if len(raw) != part['bytes'] or digest(raw) != part['hash']:
            raise ValueError('Cloud workspace segment failed verification')
        stream.write(raw)
    raw = stream.getvalue()
    if digest(raw) != reference['digest']:
        raise ValueError('Cloud workspace failed verification')
    payload = unpack(raw)
    if payload['record']['id'] != reference['id']:
        raise ValueError('Cloud workspace belongs to a different slate')
    write_backup(owner, raw, token=reference['token'])
    return payload


def probe(config, owner):
    backup = S3Backup(config)
    raw = b'Simmah private workspace storage read/write check v1'
    key = 'workspaces/connection-check'
    backup.put(owner, key, raw)
    if backup.get(owner, key) != raw:
        raise ValueError('Storage read-back failed')
    return True
