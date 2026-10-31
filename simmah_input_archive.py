"""Private, content-addressed original inputs and historical calibration jobs.

Raw files never enter Git or the anonymous construction-profile store. Each
browser owns a random capability namespace. The server copy is explicitly
local unless a private S3 bucket is configured; browser backups are separate.
"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
from collections import Counter
from itertools import chain
from pathlib import Path

SCHEMA = 1
MAX_CSV_BYTES = 256 * 1024 * 1024
TOKEN = re.compile(r'\b(CPT|CAPTAIN|MVP|ANYFLEX|FLEX|QB|RB|WR|TE|K|DST|DEF|UTIL|PG|SG|SF|PF|C|G|F|D)\s+')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    return str(name).replace('\\', '/').split('/')[-1][:240] or 'upload.csv'


def csv_tables(raw, name):
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [i for i in archive.infolist() if i.filename.lower().endswith('.csv') and not i.filename.startswith('__MACOSX/')]
            if not members or sum(i.file_size for i in members) > MAX_CSV_BYTES:
                raise ValueError('Standings ZIP has no CSVs or expands beyond 256 MiB')
            for member in members:
                yield safe_name(member.filename), archive.read(member)
    else:
        if len(raw) > MAX_CSV_BYTES:
            raise ValueError('CSV exceeds the 256 MiB analysis limit; original remains archived')
        yield safe_name(name), raw


def inspect_input(raw, name):
    """Classify originals without inventing slate identity or using live pools."""
    result = dict(schema=SCHEMA, kind='other', contest_ids=[], platform=None,
                  mode=None, teams=[], embedded_salary=False)
    # A ZIP may contain multiple contests. Save all bytes but require one CSV
    # per calibrated job, rather than silently fitting the first member.
    tables = list(csv_tables(raw, name))
    if len(tables) != 1:
        result.update(kind='contest_bundle', note='Multiple CSV members; split by contest before calibration')
        return result
    member, data = tables[0]
    reader = csv.reader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    header = next(reader, [])
    lookup = {v.strip().casefold(): i for i, v in enumerate(header)}
    entry_col = lookup.get('entryid', lookup.get('entry id', lookup.get('entry_id')))
    lineup_col = lookup.get('lineup', lookup.get('roster'))
    contest_col = lookup.get('contest id', lookup.get('contest_id'))
    is_standings = entry_col is not None and lineup_col is not None
    result['csv_member'] = member
    if is_standings:
        result['kind'] = 'contest'
        match = re.fullmatch(r'contest-standings-(\d+)\.csv', member)
        if match:
            result.update(platform='DraftKings', contest_ids=[match[1]])
        elif re.fullmatch(r'\d+-\d+\.csv', member):
            result.update(platform='FanDuel', contest_ids=[member[:-4]])
    ids, teams, modes, positions = set(result['contest_ids']), set(), set(), set()
    player_cols = None
    fingerprints, salary_rows = set(), []
    for row in chain([header], reader):
        if contest_col is not None and len(row) > contest_col and re.fullmatch(r'\d+(?:-\d+)?', row[contest_col]):
            ids.add(row[contest_col])
        # Platform salary metadata can start after entries columns and notes.
        if 'Name + ID' in row and 'Salary' in row and 'Roster Position' in row:
            player_cols = {k: row.index(k) for k in ('ID','Name','Position','Roster Position','Salary','TeamAbbrev','Game Info') if k in row}
            result.update(embedded_salary=True, platform='DraftKings')
            if not is_standings:
                result['kind'] = 'salary_entries' if entry_col is not None else 'salary'
            continue
        if 'Id' in row and 'Nickname' in row and 'Salary' in row:
            player_cols = {k: row.index(k) for k in ('Id','Nickname','Position','Salary','Team','Game','Opponent','MVP 1.5x Salary') if k in row}
            result.update(embedded_salary=True, platform='FanDuel')
            if not is_standings:
                result['kind'] = 'salary_entries' if entry_col is not None else 'salary'
            if 'MVP 1.5x Salary' in row:
                modes.add('single')
            continue
        if player_cols:
            id_key = 'ID' if result['platform'] == 'DraftKings' else 'Id'
            if id_key in player_cols and len(row) > max(player_cols.values()) and row[player_cols[id_key]].strip():
                role = row[player_cols['Roster Position']] if 'Roster Position' in player_cols else ''
                pos = row[player_cols['Position']]
                positions.update(pos.split('/'))
                team = row[player_cols.get('TeamAbbrev', player_cols.get('Team'))]
                teams.add(team)
                fingerprints.add(row[player_cols[id_key]].strip())
                salary_rows.append([row[player_cols[k]] for k in sorted(player_cols)])
                if role in ('CPT','FLEX') and result['platform'] == 'DraftKings':
                    modes.add('single')
                elif not modes:
                    modes.add('nba' if pos in ('PG','SG','SF','PF','C','PG/SG','SF/PF') else 'full')
        if is_standings and len(row) > lineup_col and row[lineup_col].strip():
            text = row[lineup_col]
            physical_ids = re.findall(r'\(([^()]+)\)(?=,|$)',text)
            if result['platform'] == 'FanDuel' and physical_ids:
                if len(physical_ids)==6:modes.add('single')
                elif re.search(r'\b(PG|SG|PF|SF)\s',text):modes.add('nba')
                else:modes.add('full')
            elif re.search(r'\b(CPT|CAPTAIN|MVP)\s', text):
                modes.add('single')
            elif re.search(r'\bQB\s', text):
                modes.add('full')
            elif re.search(r'\b(PG|SG|PF|SF)\s', text):
                modes.add('nba')
            # FD standings include physical player IDs in parentheses, not a
            # name-only DK list. Never guess FanDuel from the uploaded label.
            if result['platform'] is None and re.search(r'\(\d+-\d+\)', text):
                result['platform'] = 'FanDuel'
                if len(re.findall(r'\([^()]+\)', text)) == 6:
                    modes.add('single')
    result.update(contest_ids=sorted(ids), teams=sorted(teams),
                  sport=('NBA' if positions and positions<={'PG','SG','SF','PF','C'} else
                         'NFL' if positions and positions<={'QB','RB','WR','TE','K','D','DST','DEF'} else None),
                  player_role_ids=sorted(fingerprints),
                  salary_signature=sha256(json.dumps(sorted(salary_rows)).encode()) if salary_rows else None,
                  mode=next(iter(modes)) if len(modes) == 1 else None)
    return result


def standings_audit(raw, name):
    tables = list(csv_tables(raw, name))
    if len(tables) != 1:
        raise ValueError('One standings CSV per calibration is required')
    _, data = tables[0]
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    columns = {str(k).strip().casefold(): k for k in reader.fieldnames or []}
    eid = columns.get('entryid', columns.get('entry id'))
    lineup = columns.get('lineup', columns.get('roster'))
    remaining = columns.get('timeremaining')
    if not eid or not lineup:
        raise ValueError('Entry ID and lineup columns are required')
    seen, counts = set(), Counter()
    missing = 0
    for row in reader:
        entry = row.get(eid, '').strip()
        if not entry:
            continue
        if entry in seen:
            raise ValueError('Duplicate entry IDs in standings')
        seen.add(entry)
        if remaining and row[remaining].strip() != '0':
            raise ValueError('Contest is not complete; waiting for final standings')
        text = row.get(lineup, '').strip()
        if not text:
            missing += 1
            continue
        # Original FD single-game standings put MVP first and list actual
        # positions, with physical IDs. Preserve that first role explicitly.
        fd_ids = re.findall(r'\(([^()]+)\)(?=,|$)', text)
        parts = TOKEN.split(text)
        roles = parts[1::2]
        labels = [' '.join(x.strip(' ,;|').split()) for x in parts[2::2]]
        if fd_ids:
            labels = fd_ids
            single = len(labels) == 6
        else:
            single = any(r in ('CPT','MVP','CAPTAIN') for r in roles)
        if not labels or len(set(labels)) != len(labels):
            raise ValueError('Unparseable roster or repeated player')
        if single:
            if len(labels) != 6:
                raise ValueError('Single-game roster must contain six distinct players')
            if not fd_ids and roles != [roles[0], *['FLEX']*5]:
                raise ValueError('Expected special role followed by five FLEX slots')
            key = (labels[0], *sorted(labels[1:]))
        else:
            if len(labels) not in (8, 9):
                raise ValueError('Full-roster standings require eight or nine players')
            key = tuple(sorted(labels))
        counts[key] += 1
    n = sum(counts.values())
    if not n:
        raise ValueError('No complete rosters')
    pairs = sum(v*(v-1)//2 for v in counts.values())
    spectrum = Counter(counts.values())
    return dict(recorded_entries=len(seen), complete_entries=n, missing_rosters=missing,
                unique_rosters=len(counts), largest_cluster=max(counts.values()),
                observed_equal_roster_pairs=pairs,
                observed_pair_collision_rate=pairs/(n*(n-1)/2) if n > 1 else 0,
                multiplicity_spectrum=[dict(copies=k,rosters=v) for k,v in sorted(spectrum.items())])


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class S3Backup:
    """Optional private durable mirror. Credentials never enter file metadata."""
    def __init__(self, config):
        import boto3
        from botocore.config import Config
        self.bucket = config['bucket']
        self.prefix = str(config.get('prefix','simmah-inputs')).strip('/')
        options = {k: config[k] for k in ('endpoint_url','region_name','aws_access_key_id','aws_secret_access_key','aws_session_token') if config.get(k)}
        self.client = boto3.client('s3', config=Config(connect_timeout=5,read_timeout=30,retries={'max_attempts':2}), **options)

    def put(self, owner, key, raw):
        self.client.put_object(Bucket=self.bucket, Key=f'{self.prefix}/{owner}/{key}', Body=raw,
                               Metadata={'sha256':sha256(raw)}, ServerSideEncryption='AES256')

    def get(self, owner, key):
        response = self.client.get_object(Bucket=self.bucket, Key=f'{self.prefix}/{owner}/{key}')
        raw = response['Body'].read()
        if response.get('Metadata',{}).get('sha256') != sha256(raw):
            raise ValueError('Durable archive hash mismatch')
        return raw

    def records(self, owner):
        prefix = f'{self.prefix}/{owner}/metadata/'
        paginator = self.client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket,Prefix=prefix):
            for item in page.get('Contents',[]):
                key = item['Key']
                relative = key[len(f'{self.prefix}/{owner}/'):]
                if re.fullmatch(r'metadata/[a-f0-9]{64}\.json',relative):
                    yield json.loads(self.get(owner,relative))


class Archive:
    def __init__(self, root, owner, backup=None):
        if not re.fullmatch(r'[a-f0-9]{32}', owner):
            raise ValueError('Invalid browser archive identity')
        self.owner, self.backup = owner, backup
        self.root = Path(root).resolve() / owner
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS files (
                digest TEXT PRIMARY KEY, filename TEXT NOT NULL, metadata TEXT NOT NULL,
                saved_at REAL NOT NULL, remote_ok INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, salary_digest TEXT NOT NULL, contest_digest TEXT NOT NULL,
                state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.root/'index.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def put(self, raw, filename, metadata=None):
        raw = bytes(raw)
        digest = sha256(raw)
        payload = self.root/'objects'/digest
        if not payload.exists():
            atomic_write(payload, raw)
        elif sha256(payload.read_bytes()) != digest:
            raise ValueError('Existing archive content failed hash check')
        if metadata is None:
            try:
                metadata = inspect_input(raw, filename)
            except (ValueError, UnicodeError, csv.Error, zipfile.BadZipFile) as error:
                metadata = dict(kind='unparsed', note=str(error))
        filename = safe_name(filename)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO files(digest,filename,metadata,saved_at) VALUES(?,?,?,?)',
                       (digest,filename,json.dumps(metadata),time.time()))
        record = next(r for r in self.files() if r['digest']==digest)
        if self.backup and not record['remote_ok']:
            # Two objects are only acknowledged after both writes succeed.
            self.backup.put(self.owner, f'inputs/{digest}', raw)
            self.backup.put(self.owner, f'metadata/{digest}.json', json.dumps(record).encode())
            with self.connect() as db:
                db.execute('UPDATE files SET remote_ok=1 WHERE digest=?',(digest,))
        return next(r for r in self.files() if r['digest']==digest)

    def files(self):
        with self.connect() as db:
            return [{**dict(r),'metadata':json.loads(r['metadata'])} for r in db.execute('SELECT * FROM files ORDER BY saved_at')]

    def recover_remote_index(self):
        if not self.backup:
            return 0
        count = 0
        for record in self.backup.records(self.owner):
            digest = record.get('digest','')
            if not re.fullmatch('[a-f0-9]{64}',digest):
                raise ValueError('Invalid hash in durable index')
            with self.connect() as db:
                count += db.execute('INSERT OR IGNORE INTO files VALUES(?,?,?,?,1)',
                    (digest,safe_name(record['filename']),json.dumps(record['metadata']),
                     float(record['saved_at']))).rowcount
        return count

    def get(self, digest):
        if not re.fullmatch(r'[a-f0-9]{64}',digest):
            raise ValueError('Invalid content hash')
        path = self.root/'objects'/digest
        if not path.exists() and self.backup:
            raw = self.backup.get(self.owner,f'inputs/{digest}')
            if sha256(raw) != digest:
                raise ValueError('Restored file hash mismatch')
            atomic_write(path,raw)
        raw = path.read_bytes()
        if sha256(raw) != digest:
            raise ValueError('Archived file hash mismatch')
        return raw

    def plan(self):
        """Only verified contest-ID joins auto-launch expensive historical fits."""
        files = self.files()
        salary = [r for r in files if r['metadata'].get('embedded_salary')]
        for contest in [r for r in files if r['metadata'].get('kind') == 'contest']:
            cm = contest['metadata']
            eligible = [r for r in salary if cm.get('platform') == r['metadata'].get('platform')
                        and cm.get('mode') == r['metadata'].get('mode')
                        and set(cm.get('contest_ids',[])) & set(r['metadata'].get('contest_ids',[]))]
            if cm.get('bound_salary_digest'):
                eligible = [r for r in salary if r['digest']==cm['bound_salary_digest']]
            if not eligible:
                continue
            # If several revisions have distinct salary tables, do not silently
            # choose the latest. Byte-identical original imports deduplicate.
            fingerprints = {r['metadata'].get('salary_signature') for r in eligible}
            if len(fingerprints) != 1:
                continue
            chosen = eligible[-1]
            jid = sha256(('historical-kl-v1:'+chosen['digest']+':'+contest['digest']).encode())
            supported = ((cm.get('mode') == 'nba' and chosen['metadata'].get('sport')=='NBA') or
                         (cm.get('mode') == 'single' and chosen['metadata'].get('sport')=='NFL' and len(chosen['metadata'].get('teams',[])) == 2))
            state = 'queued' if supported else 'unsupported_format'
            detail = '' if supported else 'Originals saved. Exact automatic KL fitting supports NFL DK Showdown, FD six-player Single Game, and NBA Classic.'
            with self.connect() as db:
                db.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?)',
                    (jid,chosen['digest'],contest['digest'],state,detail,time.time()))
        return self.jobs()

    def bind_salary(self, contest_digest, salary_digest):
        records = {r['digest']:r for r in self.files()}
        contest, salary = records[contest_digest], records[salary_digest]
        cm, sm = contest['metadata'], salary['metadata']
        if cm.get('kind') != 'contest' or not sm.get('embedded_salary'):
            raise ValueError('Choose an original contest and salary table')
        if cm.get('platform') != sm.get('platform') or cm.get('mode') != sm.get('mode'):
            raise ValueError('Platform or roster format mismatch')
        if sm.get('contest_ids') and not set(sm['contest_ids']) & set(cm.get('contest_ids',[])):
            raise ValueError('Embedded contest IDs conflict; linking is forbidden')
        cm = {**cm,'bound_salary_digest':salary_digest,'pairing_evidence':'User explicitly verified same historical slate','pairing_reviewed_at':time.time()}
        with self.connect() as db:
            db.execute('UPDATE files SET metadata=? WHERE digest=?',(json.dumps(cm),contest_digest))
        if self.backup:
            updated=next(r for r in self.files() if r['digest']==contest_digest)
            self.backup.put(self.owner,f'metadata/{contest_digest}.json',json.dumps(updated).encode())

    def jobs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY updated DESC')]

    def set_job(self, jid, state, detail=''):
        with self.connect() as db:
            db.execute('UPDATE jobs SET state=?,detail=?,updated=? WHERE id=?',
                       (state,str(detail)[:3000],time.time(),jid))

    def audit(self, record):
        target = self.root/'audits'/(record['digest']+'.json')
        if target.exists():
            return json.loads(target.read_text())
        try:
            result = dict(status='audited', **standings_audit(self.get(record['digest']),record['filename']))
        except (ValueError,UnicodeError,csv.Error,zipfile.BadZipFile) as error:
            result = dict(status='waiting_or_invalid',detail=str(error))
        atomic_write(target,json.dumps(result).encode())
        return result

    def restore_zip(self, raw):
        """Restore verified originals into the current private browser archive."""
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            if sum(i.file_size for i in bundle.infolist()) > 512*1024*1024:
                raise ValueError('Backup expands beyond 512 MiB')
            manifest = json.loads(bundle.read('manifest.json'))
            if manifest.get('schema') != SCHEMA:
                raise ValueError('Unsupported archive backup schema')
            rows = manifest.get('files',[])
            # Validate every requested member/hash before saving any originals.
            checked = []
            for record in rows:
                digest = record['digest']
                filename = safe_name(record['filename'])
                if not re.fullmatch('[a-f0-9]{64}',digest):
                    raise ValueError('Invalid digest in backup')
                data = bundle.read('originals/'+digest+'/'+filename)
                if sha256(data) != digest:
                    raise ValueError('Backup original failed its hash check')
                checked.append((data,filename))
            for data,filename in checked:
                self.put(data,filename)
        return len(checked)

    def backup_zip(self):
        buf = io.BytesIO()
        manifest = self.files()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',json.dumps(dict(schema=SCHEMA,files=manifest),indent=2))
            for record in manifest:
                archive.writestr('originals/'+record['digest']+'/'+record['filename'],self.get(record['digest']))
            for path in (self.root/'jobs').glob('*/result.zip'):
                archive.write(path,'calibrations/'+path.parent.name+'.zip')
        return buf.getvalue()
