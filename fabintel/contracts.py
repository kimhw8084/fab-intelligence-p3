"""Frozen P1-P4 shared evidence contract; no remote dependencies."""
from __future__ import annotations

import hashlib
import json
from typing import Any

CONTRACT_VERSION='1.0.0'
PRODUCT_IDS=frozenset({'p1','p2','p3','p4'})
MODES=frozenset({'SYNTHETIC_DEMO','INTERNAL_AUTHORIZED'})
STATUSES=frozenset({'VALID','PARTIAL','INCONCLUSIVE','REFUSED','ERROR'})
CATEGORIES=frozenset({'DESCRIPTIVE','ASSOCIATION','PREDICTION','CAUSAL_ESTIMATE','INTERVENTION_VALIDATED'})

class ContractError(ValueError): pass

def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def envelope(product_id, raw_input, status, claims, limitations=(), *, mode='SYNTHETIC_DEMO', assumptions=(), sources=None):
    if product_id not in PRODUCT_IDS: raise ContractError('unknown product')
    if mode not in MODES: raise ContractError('invalid mode')
    if status not in STATUSES: raise ContractError('invalid status')
    if mode=='INTERNAL_AUTHORIZED': raise ContractError('bootstrap is never an authorized internal connector')
    input_hash=digest(raw_input)
    ev={'schema_version':CONTRACT_VERSION,'investigation_id':f'SYN-{product_id}-{input_hash[:12]}',
        'product_id':product_id,'mode':mode,'status':status,'claims':list(claims),'sources':sources or [],
        'assumptions':list(assumptions),'limitations':list(limitations),
        'provenance':{'engine_version':'0.1.0-bootstrap','input_sha256':input_hash,'semantic_catalog_version':'SYNTHETIC-1'}}
    validate_envelope(ev)
    return ev

def validate_envelope(ev):
    for key in ('schema_version','investigation_id','product_id','mode','status','claims','sources','assumptions','limitations','provenance'):
        if key not in ev: raise ContractError('missing '+key)
    if ev['schema_version'] != CONTRACT_VERSION or ev['product_id'] not in PRODUCT_IDS or ev['mode'] not in MODES or ev['status'] not in STATUSES:
        raise ContractError('bad enumerated field')
    if ev['mode']=='SYNTHETIC_DEMO' and ev['investigation_id'][:4]!='SYN-': raise ContractError('synthetic case not labeled')
    if not isinstance(ev['claims'],list): raise ContractError('claims must be list')
    for claim in ev['claims']:
        for field in ('statement','category','source_ids','method','certainty'):
            if field not in claim: raise ContractError('incomplete claim')
        if claim['category'] not in CATEGORIES: raise ContractError('invalid claim category')
        if claim['certainty'] not in ('SUPPORTED','CONDITIONAL','INCONCLUSIVE'): raise ContractError('invalid certainty')
    if ev['status'] in ('INCONCLUSIVE','REFUSED') and not ev['limitations']:
        raise ContractError('an inconclusive/refused result requires a reason')
    return True

def claim(statement,category='DESCRIPTIVE',method='deterministic_baseline',source_ids=None,certainty='SUPPORTED'):
    return {'statement':statement,'category':category,'source_ids':source_ids or [],'method':method,'certainty':certainty}
