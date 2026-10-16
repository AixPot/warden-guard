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
    data=request('/identity/connect/token',{'grant_type':'password','client_id':'cli','scope':'api offline_access','username':scope['account'],'password':password_hash,'deviceIdentifier':str(uuid.uuid4()),'deviceName':'Acceptance observer','deviceType':'8'},form=True)
    return request('/api/devices',token=data['access_token'])

def main():
    assert os.environ.get('WG_ISOLATED_ACCEPTANCE')=='yes'
    os.umask(0o077)
    ram='/run/warden-guard'
    # Local TLS terminator: no published ports, no insecure TLS bypass.
    import ssl, http.server, threading, http.client
    cert=ram+'/cert.pem'; key=ram+'/tls.key'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-keyout',key,'-out',cert],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self): self.forward()
        def do_POST(self): self.forward()
        def do_PUT(self): self.forward()
        def do_DELETE(self): self.forward()
        def forward(self):
            body=self.rfile.read(int(self.headers.get('Content-Length','0')))
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
    with Profile('dest',src,storage,ram) as seed:
        seed.ingest(data)
    old=copy.deepcopy(data); old['items']=old['items'][:1]; old['items'][0]['name']='Old destination record'
    with Profile('dest',dst,storage,ram) as seed: seed.ingest(old)
    backup_password=secrets.token_urlsafe(32).encode()
    with Profile('source',src,storage,ram) as source, Profile('dest',dst,storage,ram) as target:
        source_export=json.loads(source.export_raw())
        status=execute(source,target,storage,backup_password)
        assert status=='complete',status
        print(json.dumps({'first':status}))
        assert canonical(json.loads(target.export_raw()))==canonical(source_export)
    ids_before=sorted(p.read_text() for p in (Path('/state')/'devices').glob('*.json'))
    with Profile('source',src,storage,ram) as source, Profile('dest',dst,storage,ram) as target:
        assert canonical(json.loads(source.export_raw()))==canonical(source_export)
        status=execute(source,target,storage,backup_password)
        assert status=='unchanged',status
        print(json.dumps({'second':status,'fresh_profile_export_equal':True}))
    credentials=Path(ram)/'credentials.json'
    credentials.write_text(json.dumps({'source':src,'dest':dst,'backup_password':backup_password.decode()})); credentials.chmod(0o600)
    env=dict(os.environ,WG_CREDENTIALS_FILE=str(credentials),WG_STATE_DIR='/state',WG_TMPFS_DIR=ram)
    result=subprocess.run([sys.executable,'-m','warden_guard','once'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert result.returncode==0 and json.loads(result.stdout)=={'status':'unchanged'} and result.stdout.count(b'\n')==1 and not result.stderr
    credentials.unlink()
    print(json.dumps({'real_entrypoint_once':'unchanged','exit':result.returncode,'one_safe_status':True}))
    ids_after=sorted(p.read_text() for p in (Path('/state')/'devices').glob('*.json'))
    assert ids_before==ids_after
    # Respect the isolated server's normal login rate limit; do not disable it.
    import time
    time.sleep(65)
    for scope, hashed, role in ((src,sh,'source'),(dst,dh,'dest')):
        listing=devices(scope,hashed)
        rows=listing.get('data',listing.get('devices',[]))
        wanted=storage.identity(role,scope['server'],scope['account'])
        assert any(row.get('identifier')==wanted or row.get('id')==wanted for row in rows), 'server device not matched'
    print(json.dumps({'stable_scoped_appIds':True,'server_devices_verified':True,'tmpfs_profiles_clean':not any(Path(ram).glob('source-*')) and not any(Path(ram).glob('dest-*')),'types':[x['type'] for x in source_export['items']],'optional_fields':'real CLI export tested; strict null/empty synthetic tests additionally cover omitted fields'}))
if __name__=='__main__': main()
