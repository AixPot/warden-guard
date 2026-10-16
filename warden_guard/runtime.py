"""CLI diagnostics are deliberately suppressed."""
import argparse
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

    def command(self, *args, input=None):
        if self.role == 'source' and args[0] not in ('config','login','unlock','sync','export','logout','list'):
            raise Blocked('source_readonly')
        result = subprocess.run(['bw',*args],input=input,env=self.env,stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,timeout=180)
        if result.returncode: raise Blocked('cli')
        return result.stdout

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

    def export_raw(self):
        self.command('sync')
        items=json.loads(self.command('list','items'))
        orgs=json.loads(self.command('list','organizations'))
        reject_unexportable(items,orgs)
        path=self.path/'vault.json'
        self.command('export','--format','json','--output',str(path))
        try:
            raw=path.read_bytes()
            exported=json.loads(raw)
            if {i['id'] for i in exported['items']} != {i['id'] for i in items}:
                raise Blocked('export_incomplete')
            return raw
        finally: path.unlink(missing_ok=True)

    def ingest(self, data):
        path=self.path/'import.json'
        atomic(path,encoded(data).encode())
        try: self.command('import','bitwardenjson',str(path))
        finally: path.unlink(missing_ok=True)

    def delete(self, kind, ident):
        self.command('delete',kind,ident)

def reject_unexportable(items, organizations):
    if not isinstance(items,list) or not isinstance(organizations,list) or organizations:
        raise Blocked('unsupported')
    for item in items:
        if item.get('organizationId') or item.get('attachments') or type(item.get('type')) is not int or item['type'] not in (1,2,3,4,5):
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
