"""CLI diagnostics are deliberately suppressed."""
import argparse
import base64
import copy
import uuid
import resource
from contextlib import contextmanager
from .attachments import filename, MAX_FILE, MAX_TOTAL, MAX_COUNT, MAX_JSON
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from zoneinfo import ZoneInfo
from .content import encoded
from .cycle import execute
from .storage import Storage, Blocked, atomic

class Profile:
    def __init__(self, role, scope, storage, ram='/run/warden-guard'):
        self.role, self.scope, self.storage, self.ram = role, scope, storage, ram
        self.path = None
        self.env = None

    def command(self, *args, input=None, file_limit=None):
        if self.role == 'source' and args[0] not in ('config','login','unlock','sync','export','logout','list') and not (len(args)>1 and args[:2]==('get','attachment')):
            raise Blocked('source_readonly')
        def limits():
            limit=MAX_JSON if file_limit is None else file_limit
            resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
        # Both CLI JSON/stdout and downloaded files are bounded by RLIMIT_FSIZE.
        # Profiles and this anonymous output file live on the same private tmpfs.
        with tempfile.TemporaryFile(dir=self.ram) as output:
            result = subprocess.run(['bw',*args],input=input,env=self.env,stdout=output,
                                    stderr=subprocess.DEVNULL,timeout=180,preexec_fn=limits)
            if result.returncode: raise Blocked('cli')
            if output.tell()>MAX_JSON: raise Blocked('json_limit')
            output.seek(0)
            return output.read(MAX_JSON+1)

    def __enter__(self):
        self.path = Path(tempfile.mkdtemp(prefix=self.role+'-',dir=self.ram))
        self.env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','NODE_EXTRA_CA_CERTS','LANG')}
        self.env.update(BITWARDENCLI_APPDATA_DIR=str(self.path),BW_PASSWORD=self.scope['password'],
                        HOME=str(self.path),TMPDIR=self.ram)
        try:
            appid=self.storage.identity(self.role,self.scope['server'],self.scope['account'])
            atomic(self.path/'data.json',encoded({'global_applicationId_appId':appid}).encode())
            self.command('config','server',self.scope['server'])
            if self.scope.get('client_id') and self.scope.get('client_secret'):
                self.env.update(BW_CLIENTID=self.scope['client_id'],BW_CLIENTSECRET=self.scope['client_secret'])
                self.command('login','--apikey')
                session=self.command('unlock','--passwordenv','BW_PASSWORD','--raw').decode().strip()
            else:
                session=self.command('login',self.scope['account'],'--passwordenv','BW_PASSWORD','--raw').decode().strip()
            self.env['BW_SESSION']=session
            self.env.pop('BW_PASSWORD',None)
            self.env.pop('BW_CLIENTSECRET',None)
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def __exit__(self, *ignored):
        try:
            if self.env is not None: self.command('logout')
        except Exception:
            pass
        finally:
            if self.path is not None: shutil.rmtree(self.path,ignore_errors=True)
            if self.env is not None: self.env.clear()

    def fresh(self):
        return Profile(self.role,self.scope,self.storage,self.ram)

    def export_snapshot(self):
        if shutil.disk_usage(self.ram).free < 8*(MAX_TOTAL+MAX_JSON): raise Blocked('tmpfs_space')
        self.command('sync')
        normal=json.loads(self.command('list','items'))
        archived=json.loads(self.command('list','items','--archived'))
        trash=json.loads(self.command('list','items','--trash'))
        orgs=json.loads(self.command('list','organizations'))
        items=normal+archived+trash
        reject_unexportable(items,orgs)
        by_id=scope_items(normal,archived,trash)
        path=self.path/'vault.json'
        self.command('export','--format','json','--output',str(path),file_limit=MAX_JSON)
        try:
            raw=path.read_bytes(); exported=json.loads(raw)
            exported_ids=set()
            for item in exported['items']:
                ident=item.get('id')
                if not isinstance(ident,str) or ident in exported_ids or ident not in by_id: raise Blocked('export_incomplete')
                exported_ids.add(ident)
                listed=by_id[ident]
                if any(item.get(k)!=listed.get(k) for k in ('type','organizationId','deletedDate','archivedDate')): raise Blocked('export_scope')
            active={k:v for k,v in by_id.items() if not v.get('deletedDate')}
            exported_active=[i for i in exported['items'] if not i.get('deletedDate')]
            if {i['id'] for i in exported_active}!=set(active): raise Blocked('export_incomplete')
            data=copy.deepcopy(exported); data['items']=exported_active
            for item in data['items']:
                item['attachments']=by_id[item['id']].get('attachments') or []
            return data,raw
        finally: path.unlink(missing_ok=True)

    def export_raw(self):
        return self.export_snapshot()[1]

    def download_attachment(self, item, attachment):
        require_tmpfs(self.ram)
        # CLI size describes ENCRYPTED bytes (type-2 overhead 49 + PKCS7 padding).
        size=attachment.get('size')
        if not isinstance(size,(str,int)) or isinstance(size,bool) or not str(size).isdigit(): raise Blocked('attachment_size')
        size=int(size)
        if size<65 or size>MAX_FILE+65: raise Blocked('attachment_limit')
        if shutil.disk_usage(self.ram).free < 8*(MAX_TOTAL+MAX_JSON): raise Blocked('tmpfs_space')
        path=self.path/('download-'+uuid.uuid4().hex)
        try:
            self.command('get','attachment',attachment['id'],'--itemid',item,'--output',str(path),file_limit=MAX_FILE)
            if not path.is_file() or path.is_symlink(): raise Blocked('attachment_file')
            payload=path.read_bytes()
            if 49+16*(len(payload)//16+1)!=size: raise Blocked('attachment_length')
            return payload
        finally: path.unlink(missing_ok=True)

    def upload_attachment(self, item, name, payload):
        filename(name); require_tmpfs(self.ram)
        if len(payload)>MAX_FILE: raise Blocked('attachment_limit')
        with tempfile.TemporaryDirectory(prefix='upload-',dir=self.path) as directory:
            path=Path(directory)/name; atomic(path,payload)
            self.command('create','attachment','--file',str(path),'--itemid',item)

    def ingest_mapped(self, data):
        # Temporary random custom fields create a bijection even for equal bodies.
        # No name matching and no reliance on server import order.
        marker='warden-guard-'+uuid.uuid4().hex
        marked=copy.deepcopy(data); tokens={}
        for item in marked['items']:
            token=uuid.uuid4().hex; tokens[token]=item['id']
            item['fields']=(item.get('fields') or [])+[{'name':marker,'value':token,'type':0}]
        self.ingest(marked)
        observed,_=self.export_snapshot(); mapping={}
        for item in observed['items']:
            matches=[f for f in (item.get('fields') or []) if f.get('name')==marker]
            if not matches: continue
            if len(matches)!=1 or matches[0].get('value') not in tokens: raise Blocked('id_mapping')
            old=tokens[matches[0]['value']]
            if old in mapping: raise Blocked('id_mapping')
            mapping[old]=item['id']
        if set(mapping.values()) & {i['id'] for i in data['items']} or len(mapping)!=len(data['items']): raise Blocked('id_mapping')
        originals={i['id']:i for i in data['items']}
        for old,new in mapping.items():
            item=json.loads(self.command('get','item',new))
            item['fields']=originals[old].get('fields')
            self.command('edit','item',new,input=base64.b64encode(encoded(item).encode()))
        return mapping

    def ingest(self, data):
        path=self.path/'import.json'
        atomic(path,encoded(data).encode())
        try: self.command('import','bitwardenjson',str(path))
        finally: path.unlink(missing_ok=True)

    def delete(self, kind, ident):
        self.command('delete',kind,ident)

def scope_items(normal, archived, trash):
    result={}
    for rows, state in ((normal,'normal'),(archived,'archived'),(trash,'trash')):
        if not isinstance(rows,list): raise Blocked('export_scope')
        for item in rows:
            ident=item.get('id')
            if not isinstance(ident,str) or not ident or ident in result: raise Blocked('export_scope')
            if state=='trash':
                if not item.get('deletedDate'): raise Blocked('export_scope')
            elif item.get('deletedDate') or bool(item.get('archivedDate')) != (state=='archived'):
                raise Blocked('export_scope')
            result[ident]=item
    return result


def reject_unexportable(items, organizations):
    if not isinstance(items,list) or not isinstance(organizations,list) or organizations:
        raise Blocked('unsupported')
    for item in items:
        if item.get('organizationId') or item.get('collectionIds') or type(item.get('type')) is not int or item['type'] not in (1,2,3,4,5):
            raise Blocked('unsupported')

def private_json(path):
    path=Path(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_mode & 0o077:
        raise Blocked('credential_permissions')
    return json.loads(path.read_bytes())

def load_config():
    config=private_json(os.environ.get('WG_CREDENTIALS_FILE','/run/secrets/credentials.json'))
    for role in ('source','dest'):
        scope=config[role]
        if not all(isinstance(scope.get(k),str) and scope[k] for k in ('server','account','password')):
            raise Blocked('configuration')
        if not scope['server'].startswith(('https://',)): raise Blocked('configuration')
    if not isinstance(config.get('backup_password'),str) or not config['backup_password'] or '\n' in config['backup_password'] or len(config['backup_password'].encode()) > 1024:
        raise Blocked('configuration')
    if (config['source']['server'],config['source']['account']) == (config['dest']['server'],config['dest']['account']):
        raise Blocked('same_account')
    return config

def require_tmpfs(path):
    path=Path(path).resolve()
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    matches=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before,after=line.split(' - ',1)
        mount=before.split()[4]
        if str(path)==mount or str(path).startswith(mount.rstrip('/')+'/'):
            matches.append((len(mount),after.split()[0]))
    if not matches or max(matches)[1] != 'tmpfs': raise Blocked('tmpfs_required')
    os.chmod(path,0o700)
    return str(path)

def once():
    config=load_config()
    storage=Storage(os.environ.get('WG_STATE_DIR','/state'))
    with storage.lock():
        storage.check_ready()
        ram=require_tmpfs(os.environ.get('WG_TMPFS_DIR','/run/warden-guard'))
        days=int(os.environ.get('WG_RETENTION_DAYS','30')); minimum=int(os.environ.get('WG_MIN_BACKUPS','7'))
        if days<1 or minimum<1: raise Blocked('retention')
        with Profile('source',config['source'],storage,ram) as src, Profile('dest',config['dest'],storage,ram) as dst:
            return execute(src,dst,storage,config['backup_password'].encode(),days,minimum,locked=True)

def interrupted(signum, frame):
    raise InterruptedError()

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['once','schedule'],default='schedule',nargs='?')
    args=parser.parse_args(argv)
    os.umask(0o077)
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    def tick():
        try:
            result=once()
            print(json.dumps({'status':result}),flush=True)
            return 0
        except InterruptedError:
            print(json.dumps({'status':'error','code':'operation_failed'}),flush=True)
            raise
        except Exception:
            print(json.dumps({'status':'error','code':'operation_failed'}),flush=True)
            return 1
    if args.mode=='once':
        try: return tick()
        except InterruptedError: return 1
    try:
        tz=ZoneInfo(os.environ.get('TZ','Asia/Shanghai'))
        hour=int(os.environ.get('WG_HOUR','0')); minute=int(os.environ.get('WG_MINUTE','0'))
        if not 0<=hour<=23 or not 0<=minute<=59: raise ValueError()
        while True:
            now=datetime.datetime.now(tz)
            due=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
            if due<=now: due+=datetime.timedelta(days=1)
            time.sleep((due-now).total_seconds())
            tick()
    except BaseException:
        return 1
