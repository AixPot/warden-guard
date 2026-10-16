"""Opt-in, synthetic accounts only. Run inside an isolated loopback test container.
Registration wire format: Vaultwarden 1.37.4 public identity/accounts API.
Never run against a real server. All generated credentials remain in memory/tmpfs.
"""
import base64
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.request
import urllib.parse
import uuid
sys.path.insert(0, '/app')
from warden_guard.runtime import Profile
from warden_guard.storage import Storage
from warden_guard.cycle import execute
from warden_guard.content import canonical

SERVER='https://127.0.0.1:8443'
def request(path, payload=None, token=None, form=False):
    headers={'Accept':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    raw=None
    if payload is not None:
        raw=(urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
        headers['Content-Type']='application/x-www-form-urlencoded' if form else 'application/json'
    with urllib.request.urlopen(urllib.request.Request(SERVER+path,data=raw,headers=headers),timeout=30) as response:
        return json.load(response)

def account(role):
    email=role+'-'+uuid.uuid4().hex+'@example.invalid'
    password=secrets.token_urlsafe(32)
    # HKDF-Expand with SHA256: one block for each 32-byte stretched subkey.
    helper=r"""
const c=require('crypto'); let s=''; process.stdin.on('data',d=>s+=d); process.stdin.on('end',()=>{
const a=JSON.parse(s); const m=c.pbkdf2Sync(a.password,a.email,600000,32,'sha256');
const hash=c.pbkdf2Sync(m,a.password,1,32,'sha256').toString('base64');
const enc=c.createHmac('sha256',m).update(Buffer.concat([Buffer.from('enc'),Buffer.from([1])])).digest();
const mac=c.createHmac('sha256',m).update(Buffer.concat([Buffer.from('mac'),Buffer.from([1])])).digest();
const iv=c.randomBytes(16), key=c.randomBytes(64), cipher=c.createCipheriv('aes-256-cbc',enc,iv);
const ct=Buffer.concat([cipher.update(key),cipher.final()]);
const tag=c.createHmac('sha256',mac).update(Buffer.concat([iv,ct])).digest();
const pair=c.generateKeyPairSync('rsa',{modulusLength:2048,publicKeyEncoding:{type:'spki',format:'der'},privateKeyEncoding:{type:'pkcs8',format:'der'}});
const iv2=c.randomBytes(16), cipher2=c.createCipheriv('aes-256-cbc',key.subarray(0,32),iv2);
const ct2=Buffer.concat([cipher2.update(pair.privateKey),cipher2.final()]);
const tag2=c.createHmac('sha256',key.subarray(32)).update(Buffer.concat([iv2,ct2])).digest();
const keys={publicKey:pair.publicKey.toString('base64'),encryptedPrivateKey:'2.'+[iv2,ct2,tag2].map(b=>b.toString('base64')).join('|')};
console.log(JSON.stringify({hash,keys,key:'2.'+[iv,ct,tag].map(b=>b.toString('base64')).join('|')}));
});
"""
    p=subprocess.run(['node','-e',helper],input=json.dumps({'email':email,'password':password}).encode(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True)
    keys=json.loads(p.stdout)
    token=request('/identity/accounts/register/send-verification-email',{'email':email,'name':'Synthetic acceptance'})
    request('/identity/accounts/register/finish',{'email':email,'masterPasswordHash':keys['hash'],'key':keys['key'],'kdf':0,'kdfIterations':600000,'emailVerificationToken':token,'keys':keys['keys']})
    return {'server':SERVER,'account':email,'password':password},keys['hash']

def devices(scope, password_hash):
    data=request('/identity/connect/token',{'grant_type':'password','client_id':'cli','scope':'api offline_access','username':scope['account'],'password':password_hash,'deviceIdentifier':Storage('/state').identity('source' if scope['account'].startswith('source-') else 'dest',scope['server'],scope['account']),'deviceName':'Acceptance observer','deviceType':'8'},form=True)
    return request('/api/devices',token=data['access_token'])

def main():
    assert os.environ.get('WG_ISOLATED_ACCEPTANCE')=='yes'
    os.umask(0o077)
    ram='/run/warden-guard'
    # Local TLS terminator: no published ports, no insecure TLS bypass.
    import ssl, http.server, threading, http.client
    cert=ram+'/cert.pem'; key=ram+'/tls.key'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',key,'-out',cert],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    fail_upload=False
    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self): self.forward()
        def do_POST(self): self.forward()
        def do_PUT(self): self.forward()
        def do_DELETE(self): self.forward()
        def forward(self):
            body=self.rfile.read(int(self.headers.get('Content-Length','0')))
            if fail_upload and self.command=='POST' and '/attachment' in self.path:
                self.send_response(503); self.send_header('Content-Length','0'); self.end_headers(); return
            upstream=http.client.HTTPConnection('127.0.0.1',80,timeout=30)
            upstream.request(self.command,self.path,body,dict(self.headers))
            r=upstream.getresponse(); data=r.read(); self.send_response(r.status)
            for k,v in r.getheaders():
                if k.lower() not in ('connection','transfer-encoding','content-length'): self.send_header(k,v)
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); upstream.close()
    proxy=http.server.ThreadingHTTPServer(('127.0.0.1',8443),Proxy)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
    proxy.socket=context.wrap_socket(proxy.socket,server_side=True)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cert))))
    os.environ['NODE_EXTRA_CA_CERTS']=cert
    storage=Storage('/state')
    src, sh=account('source'); dst, dh=account('dest')
    # SSH private key is generated in tmpfs and never printed.
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',ram+'/key'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    private=Path(ram+'/key').read_text(); public=Path(ram+'/key.pub').read_text().strip()
    fingerprint=subprocess.check_output(['ssh-keygen','-lf',ram+'/key.pub']).decode().split()[1]
    data={'encrypted':False,'folders':[], 'items':[
        {'id':str(uuid.uuid4()),'type':1,'name':'Representative login','folderId':None,'organizationId':None,'collectionIds':[], 'notes':None,'favorite':False,'reprompt':0,'fields':None,'passwordHistory':None,'login':{'username':'','password':secrets.token_urlsafe(20),'totp':'','uris':None,'fido2Credentials':[]}},
        {'id':str(uuid.uuid4()),'type':5,'name':'Representative SSH','folderId':None,'organizationId':None,'collectionIds':[],'notes':None,'favorite':False,'reprompt':0,'fields':None,'passwordHistory':None,'sshKey':{'privateKey':private,'publicKey':public,'keyFingerprint':fingerprint}}]}
    # Use actual official CLI import for fixture creation; no production endpoint involved.
    data['items'][0]['login'].pop('password')
    duplicate=copy.deepcopy(data['items'][0]); duplicate['id']=str(uuid.uuid4()); data['items'].append(duplicate)
    data['items'].append({'id':str(uuid.uuid4()),'type':3,'name':'Archived representative card','card':{'brand':'Visa','number':'4111111111111111'},'organizationId':None,'collectionIds':[]})
    # Equal bodies, different attachments; duplicate names/content and a zero-byte file.
    with Profile('source',src,storage,ram) as seed:
        seed.role='dest'  # Synthetic fixture setup only; scoped identity stays source.
        seed.ingest(data)
        rows=json.loads(seed.export_raw())['items']; logins=[i for i in rows if i['type']==1]
        for n,item in enumerate(logins):
            seed.upload_attachment(item['id'],'same.bin',b'first' if n==0 else b'second')
        seed.upload_attachment(logins[0]['id'],'same.bin',b'first')
        seed.upload_attachment(logins[0]['id'],'empty.bin',b'')
        card=next(i for i in rows if i['type']==3)
        seed.upload_attachment(card['id'],'archived.bin',b'archived-payload')
        seed.command('archive','item',card['id'])
        seed.command('sync')
        assert any(i['id']==card['id'] for i in json.loads(seed.command('list','items','--archived')))
        assert not any(i['id']==card['id'] for i in json.loads(seed.command('list','items')))
        print(json.dumps({'synthetic_archive_cli_state_verified':True}),flush=True)
    old=copy.deepcopy(data); old['items']=old['items'][:1]; old['items'][0]['name']='Old destination record'
    with Profile('dest',dst,storage,ram) as seed:
        seed.ingest(old)
        seed.upload_attachment(json.loads(seed.export_raw())['items'][0]['id'],'old.bin',b'old-payload')
    backup_password=secrets.token_urlsafe(32).encode()
    with Profile('source',src,storage,ram) as source, Profile('dest',dst,storage,ram) as target:
        source_export=json.loads(source.export_raw())
        status=execute(source,target,storage,backup_password)
        assert status=='complete',status
        print(json.dumps({'first':status,'attachments_verified':True}),flush=True)
        from warden_guard.cycle import snapshot
        from warden_guard.attachments import unpack
        source_snapshot=snapshot(source)
        assert canonical(snapshot(target)['data'])==canonical(source_snapshot['data'])
        recovered=[unpack(storage.decrypt(p,backup_password)) for p in (Path('/state')/'backups').glob('*-*.enc') if p.name.startswith(('source-','target-'))]
        assert any(b'old-payload' in r['payloads'] for r in recovered)
        assert any(sorted(r['payloads'])==sorted(source_snapshot['payloads']) for r in recovered)
        # JSON archivedDate alone is not proof: independently inspect fresh CLI states.
        def archive_state(profile):
            profile.command('sync')
            normal=json.loads(profile.command('list','items'))
            archived=json.loads(profile.command('list','items','--archived'))
            assert len(archived)==1 and archived[0]['type']==3 and not archived[0].get('deletedDate')
            assert archived[0]['id'] not in {i['id'] for i in normal}
            return archived[0]['archivedDate']
        with target.fresh() as verifier:
            assert archive_state(verifier)==next(i['archivedDate'] for i in source_snapshot['data']['items'] if i['type']==3)
        # Exercise offline extraction and restore to a third, newly-created synthetic vault.
        from warden_guard.restore import extract
        from warden_guard.attachments import pack
        restored_scope,_=account('restore')
        recovered_source=next(r for r in recovered if sorted(r['payloads'])==sorted(source_snapshot['payloads']))
        extraction=Path(ram)/'offline-restore'
        extract(pack(recovered_source),extraction)
        restore_data=json.loads((extraction/'import.json').read_bytes())
        manifest=json.loads((extraction/'manifest.json').read_bytes())
        with Profile('dest',restored_scope,storage,ram) as restored:
            mapping=restored.ingest_mapped(restore_data)
            for n,meta in enumerate(manifest):
                restored.upload_attachment(mapping[meta['itemId']],meta['fileName'],(extraction/'payloads'/f'{n:06d}').read_bytes())
        with Profile('dest',restored_scope,storage,ram) as verifier:
            assert canonical(snapshot(verifier)['data'])==canonical(source_snapshot['data'])
            assert archive_state(verifier)==next(i['archivedDate'] for i in source_snapshot['data']['items'] if i['type']==3)
        import shutil
        shutil.rmtree(extraction)
        print(json.dumps({'fresh_cli_archive_state_verified':True,'native_import_preserves_archivedDate_and_state':True,'new_vault_offline_restore_archive_and_attachment_verified':True}),flush=True)
        print(json.dumps({'offline_snapshot_payload_restore':True,'zero_byte':b'' in source_snapshot['payloads'],'missing_password':all('password' not in i['login'] or i['login']['password'] is None for i in source_export['items'] if i['type']==1)}),flush=True)
    ids_before=sorted(p.read_text() for p in (Path('/state')/'devices').glob('*.json'))
    with Profile('source',src,storage,ram) as source, Profile('dest',dst,storage,ram) as target:
        assert canonical(snapshot(source)['data'])==canonical(source_snapshot['data'])
        status=execute(source,target,storage,backup_password)
        assert status=='unchanged',status
        print(json.dumps({'second':status,'fresh_profile_export_equal':True}))
    credentials=Path(ram)/'credentials.json'
    credentials.write_text(json.dumps({'source':src,'dest':dst,'backup_password':backup_password.decode()})); credentials.chmod(0o600)
    env=dict(os.environ,WG_CREDENTIALS_FILE=str(credentials),WG_STATE_DIR='/state',WG_TMPFS_DIR=ram)
    result=subprocess.run([sys.executable,'-m','warden_guard','once'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==0 and json.loads(result.stdout)=={'status':'unchanged'} and result.stdout.count(b'\n')==1 and not result.stderr
    # Real entrypoint failure injection: HTTP upload rejection, no adapter monkeypatch.
    import time
    time.sleep(65)
    with Profile('source',src,storage,ram) as seed:
        seed.role='dest'
        seed.upload_attachment(source_export['items'][0]['id'],'changed.bin',b'changed')
    with Profile('dest',dst,storage,ram) as observer:
        before_failure=snapshot(observer)
    fail_upload=True
    result=subprocess.run([sys.executable,'-m','warden_guard','once'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==1 and json.loads(result.stdout)['status']=='error' and not result.stderr
    fail_upload=False
    with Profile('dest',dst,storage,ram) as observer:
        after_failure=snapshot(observer)
    old_ids={i['id'] for i in before_failure['data']['items']}
    assert {i['id']:i for i in after_failure['data']['items'] if i['id'] in old_ids}=={i['id']:i for i in before_failure['data']['items']}
    assert json.loads((Path('/state')/'journal.json').read_bytes())['phase']=='uploading'
    result=subprocess.run([sys.executable,'-m','warden_guard','once'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==1 and json.loads(result.stdout)['status']=='error'
    print(json.dumps({'real_upload_failure_old_ids_and_bytes_preserved':True,'retry_blocked':True}),flush=True)
    credentials.unlink()
    print(json.dumps({'real_entrypoint_once':'unchanged','exit':0,'one_safe_status':True}))
    ids_after=sorted(p.read_text() for p in (Path('/state')/'devices').glob('*.json'))
    assert ids_before==ids_after
    # Respect the isolated server's normal login rate limit; do not disable it.
    import time
    time.sleep(65)
    for scope, hashed, role in ((src,sh,'source'),(dst,dh,'dest')):
        listing=devices(scope,hashed)
        rows=listing.get('data',listing.get('devices',[]))
        wanted=storage.identity(role,scope['server'],scope['account'])
        assert len(rows)==1 and any(row.get('identifier')==wanted or row.get('id')==wanted for row in rows), 'server device not matched or duplicate'
    print(json.dumps({'stable_scoped_appIds':True,'server_devices_verified':True,'tmpfs_profiles_clean':not any(Path(ram).glob('source-*')) and not any(Path(ram).glob('dest-*')),'types':[x['type'] for x in source_export['items']],'optional_fields':'real CLI export tested; strict null/empty synthetic tests additionally cover omitted fields'}))
if __name__=='__main__':
    try: main()
    except Exception as exc:
        import traceback
        print(json.dumps({'failure_class':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]}),flush=True)
        raise
