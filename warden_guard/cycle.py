import json
from contextlib import nullcontext
from .content import canonical, validate, Invalid

def snapshot(client):
    if hasattr(client, 'export_raw'):
        raw = client.export_raw()
        data = json.loads(raw)
    else:
        data = client.export()
        raw = json.dumps(data, ensure_ascii=False).encode()
    validate(data)
    return data, raw

def execute(source, target, storage, password, days=30, minimum=7, locked=False):
    with (nullcontext() if locked else storage.lock()):
        storage.check_ready()
        src, raw = snapshot(source)
        validate(src, True)
        source_path = storage.backup(raw, 'source', password)
        storage.retain_source(days, minimum)
        old, raw = snapshot(target)
        target_path = storage.backup(raw, 'target', password)
        details = {'source_snapshot':source_path.name,'target_snapshot':target_path.name,
                   'old_ids':[i['id'] for i in old['items']], 'old_folder_ids':[f['id'] for f in old['folders']]}
        if canonical(src) == canonical(old):
            storage.record('unchanged', details)
            return 'unchanged'
        storage.record('importing', details)
        target.ingest(src)
        after, _ = snapshot(target)
        before_items = {i['id']:i for i in old['items']}
        before_folders = {i['id']:i for i in old['folders']}
        old_part = dict(after,items=[i for i in after['items'] if i['id'] in before_items],
                        folders=[f for f in after['folders'] if f['id'] in before_folders])
        # Preserve raw fields too: import must not modify the original records.
        if old_part['items'] != old['items'] or old_part['folders'] != old['folders']:
            # Export ordering is not an invariant.
            if {i['id']:i for i in old_part['items']} != before_items or {f['id']:f for f in old_part['folders']} != before_folders:
                raise Invalid('old_changed')
        new = dict(after,items=[i for i in after['items'] if i['id'] not in before_items],
                   folders=[f for f in after['folders'] if f['id'] not in before_folders])
        if canonical(new) != canonical(src): raise Invalid('import_verify')
        storage.record('deleting', details)
        for ident in details['old_ids']: target.delete('item',ident)
        for ident in details['old_folder_ids']: target.delete('folder',ident)
        final, _ = snapshot(target)
        if canonical(final) != canonical(src): raise Invalid('final_verify')
        storage.record('complete', details)
        return 'complete'
