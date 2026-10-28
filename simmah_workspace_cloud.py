"""Private, integrity-checked S3 workspaces with reusable ZIP-entry segments."""
import io
import json
import zipfile
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from simmah_input_archive import S3Backup
from simmah_workspace_backup import MAX_BYTES, digest, unpack_file, path_for


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


def restore(config, owner, reference, progress=None):
    started = time.perf_counter()
    report = progress or (lambda fraction, text: None)
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
    # Download bounded ranges concurrently, including within a single large
    # matrix attachment. Write directly to disk instead of retaining the ZIP,
    # segment buffers, and decoded arrays together in memory.
    target = path_for(owner, reference['token'])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.'+uuid.uuid4().hex+'.restore')
    chunk = 4 * 1024 * 1024
    jobs = []
    offset = 0
    for part in index['parts']:
        for position in range(0, part['bytes'], chunk):
            jobs.append((offset+position, part, position, min(chunk, part['bytes']-position)))
        offset += part['bytes']
    def fetch(job):
        offset, part, position, length = job
        key = 'workspaces/parts/'+part['hash']
        if position == 0 and length == part['bytes']:
            raw = backup.get(owner, key)
        else:
            response = backup.client.get_object(Bucket=backup.bucket,
                Key=f'{backup.prefix}/{owner}/{key}',
                Range=f'bytes={position}-{position+length-1}')
            body = response['Body']
            try:
                raw = body.read(length+1)
            finally:
                body.close()
        if len(raw) != length:
            raise ValueError('Cloud workspace range failed verification')
        return offset, raw
    try:
        downloaded = 0
        with temporary.open('w+b') as stream, ThreadPoolExecutor(max_workers=4) as pool:
            todo = iter(jobs)
            pending = set()
            for _ in range(min(4, len(jobs))):
                pending.add(pool.submit(fetch, next(todo)))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    offset, raw = future.result()
                    stream.seek(offset);stream.write(raw)
                    downloaded += len(raw)
                    report(.8*downloaded/index['bytes'],
                           f"Downloading saved workspace from S3… {downloaded/(1024*1024):.0f} / {index['bytes']/(1024*1024):.0f} MB")
                    del raw
                    job = next(todo, None)
                    if job is not None:
                        pending.add(pool.submit(fetch, job))
            stream.flush()
        downloaded_at = time.perf_counter()
        report(.85, 'Verifying saved workspace…')
        # Every byte of the reconstructed archive is checked before decoding.
        payload = unpack_file(temporary, expected_digest=reference['digest'], expected_bytes=reference['bytes'])
        decoded_at = time.perf_counter()
        if payload['record']['id'] != reference['id']:
            raise ValueError('Cloud workspace belongs to a different slate')
        os.replace(temporary, target)
        payload['_restore_metrics'] = dict(bytes=index['bytes'], ranges=len(jobs),
            download_seconds=downloaded_at-started,
            verify_decode_seconds=decoded_at-downloaded_at,
            total_seconds=time.perf_counter()-started)
        report(1., 'Saved workspace restored.')
        return payload
    finally:
        temporary.unlink(missing_ok=True)


def probe(config, owner):
    backup = S3Backup(config)
    raw = b'Simmah private workspace storage read/write check v1'
    key = 'workspaces/connection-check'
    backup.put(owner, key, raw)
    if backup.get(owner, key) != raw:
        raise ValueError('Storage read-back failed')
    return True
