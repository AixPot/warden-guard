"""Version 2 encrypted snapshot plaintext; payloads are never persisted separately."""
import base64
import copy
import hashlib
import json
import os
from .content import encoded, Invalid

def limit(name, default, maximum):
    value=int(os.environ.get(name,str(default)))
    if not 1<=value<=maximum: raise Invalid('attachment_configuration')
    return value

# Explicit hard ceilings bound decoded payloads, base64 envelopes and tmpfs use.
MAX_FILE = limit('WG_ATTACHMENT_FILE_MIB',16,32) * 1024 * 1024
MAX_TOTAL = limit('WG_ATTACHMENT_TOTAL_MIB',16,32) * 1024 * 1024
if MAX_FILE>MAX_TOTAL: raise Invalid('attachment_configuration')
MAX_COUNT = 256
MAX_JSON = 8 * 1024 * 1024
MAX_BUNDLE = 64 * 1024 * 1024

def filename(name):
    # CLI upload derives the remote name from a basename. Never normalize names.
    if not isinstance(name,str) or not name or name in ('.','..') or any(c in name for c in ('/','\\','\0')) or len(name.encode()) > 240:
        raise Invalid('attachment_name')
    return name

def collect(client, data, raw):
    data=copy.deepcopy(data); manifest=[]; payloads=[]; total=0
    attachments=[a for i in data['items'] for a in (i.get('attachments') or [])]
    if len(attachments)>MAX_COUNT: raise Invalid('attachment_limit')
    for item in data['items']:
        descriptors=[]
        for attachment in item.get('attachments') or []:
            filename(attachment['fileName'])
            if len(payloads)>=MAX_COUNT: raise Invalid('attachment_limit')
            payload=client.download_attachment(item['id'],attachment)
            if not isinstance(payload,bytes) or len(payload)>MAX_FILE: raise Invalid('attachment_limit')
            total+=len(payload)
            if total>MAX_TOTAL: raise Invalid('attachment_limit')
            descriptor={'fileName':attachment['fileName'],'length':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
            manifest.append(dict(descriptor,itemId=item['id'],attachmentId=attachment['id'],metadata=attachment))
            payloads.append(payload); descriptors.append(descriptor)
        item['attachments']=sorted(descriptors,key=encoded)
    return {'data':data,'raw':raw,'manifest':manifest,'payloads':payloads}

def pack(snapshot):
    raw=encoded({'format':'warden-guard.snapshot','version':2,'raw_export':base64.b64encode(snapshot['raw']).decode(),
                 'data':snapshot['data'],'manifest':snapshot['manifest'],
                 'payloads':[base64.b64encode(p).decode() for p in snapshot['payloads']]}).encode()
    if len(raw)>MAX_BUNDLE: raise Invalid('snapshot_limit')
    return raw

def unpack(raw):
    if len(raw)>MAX_BUNDLE: raise Invalid('snapshot_limit')
    doc=json.loads(raw)
    if doc.get('format')!='warden-guard.snapshot' or doc.get('version')!=2: raise Invalid('snapshot_version')
    payloads=[base64.b64decode(p,validate=True) for p in doc['payloads']]
    if len(payloads)!=len(doc['manifest']) or len(payloads)>MAX_COUNT or sum(map(len,payloads))>MAX_TOTAL: raise Invalid('snapshot_manifest')
    for meta,payload in zip(doc['manifest'],payloads):
        filename(meta['fileName'])
        if len(payload)>MAX_FILE or len(payload)!=meta['length'] or hashlib.sha256(payload).hexdigest()!=meta['sha256']: raise Invalid('snapshot_hash')
    from .content import validate
    from collections import Counter
    validate(doc['data'])
    expected=Counter((i['id'],a['fileName'],a['length'],a['sha256']) for i in doc['data']['items'] for a in i.get('attachments') or [])
    actual=Counter((m['itemId'],m['fileName'],m['length'],m['sha256']) for m in doc['manifest'])
    if expected!=actual: raise Invalid('snapshot_manifest')
    original=base64.b64decode(doc['raw_export'],validate=True)
    if len(original)>MAX_JSON: raise Invalid('json_limit')
    return {'raw':original,'data':doc['data'],'manifest':doc['manifest'],'payloads':payloads}
