import copy
import json
from contextlib import nullcontext
from .content import canonical, validate, Invalid
from .attachments import collect, pack, MAX_JSON


def snapshot(client):
    if hasattr(client, 'export_snapshot'):
        data, raw = client.export_snapshot()
    elif hasattr(client, 'export_raw'):
        raw = client.export_raw()
        data = json.loads(raw)
    else:
        data = client.export()
        raw = json.dumps(data, ensure_ascii=False).encode()
    if len(raw)>MAX_JSON: raise Invalid('json_limit')
    validate(data)
    return collect(client,data,raw)


def subset(snap, ids, folders):
    data=snap['data']
    return dict(data,items=[i for i in data['items'] if i['id'] in ids],
                folders=[f for f in data['folders'] if f['id'] in folders])


def execute(source, target, storage, password, days=30, minimum=7, locked=False):
    with (nullcontext() if locked else storage.lock()):
        storage.check_ready()
        details={}
        storage.record('snapshotting',details)
        src=snapshot(source)
        validate(src['data'], True)
        source_path=storage.backup(pack(src),'source',password)
        storage.retain_source(days, minimum)
        old=snapshot(target)
        target_path=storage.backup(pack(old),'target',password)
        details={'source_snapshot':source_path.name,'target_snapshot':target_path.name,
                 'old_ids':[i['id'] for i in old['data']['items']],
                 'old_folder_ids':[f['id'] for f in old['data']['folders']]}
        if canonical(src['data']) == canonical(old['data']):
            storage.record('unchanged',details)
            return 'unchanged'
        storage.record('importing',details)
        clean=copy.deepcopy(src['data'])
        for i in clean['items']: i.pop('attachments',None)
        mapping={}
        if src['manifest']:
            mapping=target.ingest_mapped(clean)
            if set(mapping)!=set(i['id'] for i in clean['items']) or len(set(mapping.values()))!=len(mapping) or set(mapping.values()) & set(details['old_ids']):
                raise Invalid('id_mapping')
            # IDs and encrypted mapping make interrupted uploads diagnosable offline.
            mapping_path=storage.backup(json.dumps({'version':2,'item_mapping':mapping}).encode(),'mapping',password)
            details['mapping_snapshot']=mapping_path.name
            storage.record('uploading',details)
            for meta,payload in zip(src['manifest'],src['payloads']):
                target.upload_attachment(mapping[meta['itemId']],meta['fileName'],payload)
        else:
            target.ingest(clean)
        # A fresh profile must download all payloads, including the original target.
        with (target.fresh() if hasattr(target,'fresh') else nullcontext(target)) as verifier:
            after=snapshot(verifier)
        old_ids=set(details['old_ids']); old_folders=set(details['old_folder_ids'])
        old_part=subset(after,old_ids,old_folders)
        def attachment_identity(snap):
            return sorted((m['itemId'],m['attachmentId'],m['fileName'],m['length'],m['sha256']) for m in snap['manifest'] if m['itemId'] in old_ids)
        if attachment_identity(after)!=attachment_identity(old): raise Invalid('old_attachment_changed')
        if {i['id']:i for i in old_part['items']} != {i['id']:i for i in old['data']['items']} or {f['id']:f for f in old_part['folders']} != {f['id']:f for f in old['data']['folders']}:
            raise Invalid('old_changed')
        new=subset(after,{i['id'] for i in after['data']['items']}-old_ids,
                   {f['id'] for f in after['data']['folders']}-old_folders)
        if canonical(new)!=canonical(src['data']): raise Invalid('import_verify')
        if src['manifest']:
            by_new={i['id']:i for i in new['items']}
            for item in src['data']['items']:
                actual=by_new.get(mapping[item['id']])
                if actual is None or canonical(dict(new,items=[actual]))[0] != canonical(dict(src['data'],items=[item]))[0]:
                    raise Invalid('attachment_mapping_verify')
        storage.record('deleting',details)
        for ident in details['old_ids']: target.delete('item',ident)
        for ident in details['old_folder_ids']: target.delete('folder',ident)
        final=snapshot(target)
        if canonical(final['data'])!=canonical(src['data']): raise Invalid('final_verify')
        storage.record('complete',details)
        return 'complete'
