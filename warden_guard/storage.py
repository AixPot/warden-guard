import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

class Blocked(Exception):
    pass

def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        tmp.unlink(missing_ok=True)

class Storage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextlib.contextmanager
    def lock(self, name='run'):
        with open(self.root / (name + '.lock'), 'a') as handle:
            os.chmod(handle.name, 0o600)
            try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise Blocked('busy') from None
            yield

    def identity(self, role, server, account):
        scope = hashlib.sha256(json.dumps([role,server,account], separators=(',',':')).encode()).hexdigest()
        path = self.root / 'devices' / (scope + '.json')
        with self.lock('devices'):
            if not path.exists():
                atomic(path, json.dumps({'appId':str(uuid.uuid4())}).encode())
            try:
                data = json.loads(path.read_text())
                if set(data) != {'appId'} or str(uuid.UUID(data['appId'])) != data['appId'] or path.stat().st_mode & 0o777 != 0o600:
                    raise ValueError()
                return data['appId']
            except (ValueError,TypeError,KeyError):
                raise Blocked('device_corrupt') from None

    def check_ready(self):
        path = self.root / 'journal.json'
        if not path.exists(): return
        try:
            data = json.loads(path.read_text())
            if data['phase'] not in ('complete','unchanged'): raise ValueError()
        except (ValueError,KeyError,TypeError): raise Blocked('journal') from None

    def record(self, phase, details):
        atomic(self.root / 'journal.json', json.dumps(dict(details,phase=phase),sort_keys=True).encode())

    def crypt(self, raw, password, decrypt=False):
        readfd, writefd = os.pipe()
        try:
            os.write(writefd, password + b'\n'); os.close(writefd); writefd = -1
            command = ['openssl','enc','-aes-256-cbc','-pbkdf2','-iter','100000','-md','sha256','-pass','fd:'+str(readfd)]
            if decrypt: command.append('-d')
            proc = subprocess.run(command,input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,pass_fds=(readfd,),timeout=120)
            if proc.returncode: raise Blocked('crypto')
            return proc.stdout
        finally:
            os.close(readfd)
            if writefd != -1: os.close(writefd)

    def decrypt(self, path, password):
        return self.crypt(Path(path).read_bytes(),password,True)

    def backup(self, raw, role, password):
        ciphertext = self.crypt(raw,password)
        if self.crypt(ciphertext,password,True) != raw: raise Blocked('roundtrip')
        path = self.root / 'backups' / (role+'-'+str(time.time_ns())+'.enc')
        atomic(path,ciphertext)
        if self.decrypt(path,password) != raw: raise Blocked('roundtrip')
        return path

    def retain_source(self, days=30, minimum=7):
        if days < 1 or minimum < 1: raise Blocked('retention')
        paths = sorted((self.root / 'backups').glob('source-*.enc'),reverse=True)
        for path in paths[minimum:]:
            if path.stat().st_mtime < time.time() - days*86400: path.unlink()
