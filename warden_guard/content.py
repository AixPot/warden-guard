"""Strict content comparison: unknown fields are retained, not silently discarded."""
import copy
import json
from collections import Counter

class Invalid(Exception):
    pass

ITEM_METADATA = {'id', 'organizationId', 'collectionIds', 'revisionDate', 'creationDate', 'deletedDate', 'object'}
FOLDER_METADATA = {'id', 'object'}

def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def validate(data, nonempty=False):
    if not isinstance(data, dict) or data.get('encrypted') is not False:
        raise Invalid('schema')
    if not isinstance(data.get('folders'), list) or not isinstance(data.get('items'), list):
        raise Invalid('schema')
    if data.get('collections') or data.get('organizations'):
        raise Invalid('unsupported')
    folders = set()
    for folder in data['folders']:
        if not isinstance(folder, dict) or not isinstance(folder.get('id'), str) or not folder['id'] or folder['id'] in folders or not isinstance(folder.get('name'), str):
            raise Invalid('folder')
        folders.add(folder['id'])
    ids = set()
    subtypes = {1:'login', 2:'secureNote', 3:'card', 4:'identity', 5:'sshKey'}
    for item in data['items']:
        if not isinstance(item, dict):
            raise Invalid('item')
        ident, kind = item.get('id'), item.get('type')
        if not isinstance(ident, str) or not ident or ident in ids:
            raise Invalid('id')
        ids.add(ident)
        if type(kind) is not int or kind not in subtypes or not isinstance(item.get(subtypes[kind]), dict) or not isinstance(item.get('name'), str):
            raise Invalid('type')
        payload=item[subtypes[kind]]
        required={1:('password',),2:('type',),3:(),4:(),5:('privateKey','publicKey','keyFingerprint')}[kind]
        if any(key not in payload for key in required):
            raise Invalid('content_missing')
        if kind==2 and payload['type'] != 0:
            raise Invalid('secure_note')
        if item.get('organizationId') or item.get('collectionIds') or item.get('attachments') or item.get('deletedDate'):
            raise Invalid('unsupported')
        if item.get('folderId') is not None and item['folderId'] not in folders:
            raise Invalid('reference')
    if nonempty and not ids:
        raise Invalid('empty')

def canonical(data):
    validate(data)
    folders = {f['id']:{k:v for k,v in f.items() if k not in FOLDER_METADATA} for f in data['folders']}
    items = []
    for original in data['items']:
        item = {k:copy.deepcopy(v) for k,v in original.items() if k not in ITEM_METADATA}
        # Absent folderId and null both mean no folder in the export protocol.
        item['folderId'] = folders.get(item.get('folderId'))
        if item['type'] == 1:
            for key in ('username', 'totp'):
                if item['login'].get(key) in (None, ''):
                    item['login'][key] = None
        items.append(encoded(item))
    return Counter(items), Counter(encoded(f) for f in folders.values())
