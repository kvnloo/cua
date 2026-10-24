"""Export scored decision rows while retaining hashes of the unmodified raw ledger."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import corpus


def export(corpus_path,ledger_path,destination):
    frozen=Path(corpus_path).read_bytes()
    data=json.loads(frozen)
    nodes={n['id']:n for n in data['nodes']}
    digest=hashlib.sha256(frozen).hexdigest()
    raw=Path(ledger_path).read_bytes()
    source_hash=hashlib.sha256(raw).hexdigest()
    oracle_hash=hashlib.sha256(Path(corpus.__file__).read_bytes()).hexdigest()
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    counts=Counter()
    with destination.open('w') as stream:
        for line in raw.splitlines():
            row=json.loads(line)
            if row['corpus_sha256']!=digest:
                raise ValueError('mixed corpus identities')
            node=nodes[row['node_id']]
            row['correct']=corpus.correct(node,row['output']) if row['status']=='ok' else None
            row['oracle_scope']='task-specification/pre-state one-step progress or valid termination; not observed native post-state'
            row['split']=node['split']
            row['raw_row_sha256']=hashlib.sha256(line).hexdigest()
            row['raw_ledger_sha256']=source_hash
            row['oracle_source_sha256']=oracle_hash
            stream.write(json.dumps(row,allow_nan=False)+'\n')
            counts[row['model']]+=1
    receipt={'corpus_sha256':digest,'raw_ledger_sha256':source_hash,
             'oracle_source_sha256':oracle_hash,
             'scored_matrix_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
             'rows_per_model':dict(counts),'raw_ledger_source':str(ledger_path)}
    destination.with_suffix('.provenance.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',required=True)
    p.add_argument('--ledger',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    export(a.corpus,a.ledger,a.out)
