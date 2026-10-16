"""Offline extraction only: never logs into or writes to a vault."""
import argparse
import json
import os
from pathlib import Path
import shutil
from .attachments import unpack, MAX_BUNDLE
from .runtime import require_tmpfs
from .storage import atomic


def extract(raw, destination):
    snap=unpack(raw)
    destination=Path(destination)
    require_tmpfs(destination.parent)
    destination.mkdir(mode=0o700,exist_ok=False)
    try:
        atomic(destination/'raw-export.json',snap['raw'])
        # Import this JSON only after reviewing it; attachments are separate payloads.
        data=snap['data']
        for item in data['items']: item.pop('attachments',None)
        atomic(destination/'import.json',json.dumps(data).encode())
        atomic(destination/'manifest.json',json.dumps(snap['manifest']).encode())
        for n,payload in enumerate(snap['payloads']):
            atomic(destination/'payloads'/f'{n:06d}',payload)
    except BaseException:
        shutil.rmtree(destination)
        raise


def main():
    parser=argparse.ArgumentParser(description='Extract a decrypted v2 snapshot to a NEW tmpfs directory; no vault access')
    parser.add_argument('plaintext_snapshot'); parser.add_argument('destination')
    args=parser.parse_args(); os.umask(0o077)
    require_tmpfs(Path(args.plaintext_snapshot).parent)
    with open(args.plaintext_snapshot,'rb') as handle:
        extract(handle.read(MAX_BUNDLE+1),args.destination)

if __name__=='__main__': main()
