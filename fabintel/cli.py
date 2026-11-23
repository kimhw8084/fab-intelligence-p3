"""Offline candidate CLI; never presents synthetic results as company-ready."""
import argparse, json, sys
from pathlib import Path
from fabintel.contracts import validate_envelope
from fabintel.catalog import synthetic_catalog
from fabintel.project import analyze

BASE=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser(prog='python -m fabintel')
    cmd=p.add_subparsers(dest='command',required=True)
    cmd.add_parser('doctor'); cmd.add_parser('demo'); cmd.add_parser('preflight')
    q=cmd.add_parser('qualify-internal',help='validate a site-generated authorized MCP capability capture')
    q.add_argument('--capture',default='',help='path to a P3 site qualification capture JSON')
    m=cmd.add_parser('mcp-discover',help='connect to a configured read-only MCP server and report unqualified capabilities')
    m.add_argument('--config',required=True,help='site-approved MCP adapter config JSON')
    w=cmd.add_parser('mcp-analyze',help='run P3 C01-C05 through approved MCP semantics and bounded read plans')
    w.add_argument('--config',required=True,help='site-approved MCP adapter config JSON')
    w.add_argument('--plan-id',action='append',required=True,help='site-approved P3 analysis plan ID; repeat for current and any auxiliary datasets')
    w.add_argument('--time-start',required=True,help='timezone-aware start for approved relationship discovery')
    w.add_argument('--time-end',required=True,help='timezone-aware end for approved relationship discovery')
    w.add_argument('--top-k',type=int,default=5,help='maximum historical maps to return (1..50)')
    w.add_argument('--output',default='',help='write the validated evidence envelope to this path')
    g=cmd.add_parser('catalog'); g.add_argument('--tables',type=int,default=13000); g.add_argument('--output',default='')
    a=cmd.add_parser('analyze',help='analyze one local JSON wafer map')
    a.add_argument('input',help='path to a JSON investigation file')
    a.add_argument('--output',default='',help='write the evidence envelope to this path')
    a=p.parse_args()
    if a.command=='doctor':
        obj={'state':'CANDIDATE','external_transfer_ready':False,'internal_qualified':False,
         'product':(BASE/'product.json').read_text(encoding='utf8')[:200],
         'note':'Scientific workflow code is available; external qualification gates remain open.'}
    elif a.command=='preflight':
        obj={'status':'PENDING_INTERNAL_QUALIFICATION','network_requests':0,'adapter':'synthetic_only',
             'reasons':['Real approved MCP capabilities and permissions are not available externally.',
                        'Approved local model and company OS require authorized verification.']}
    elif a.command=='qualify-internal':
        from fabintel.preflight import evaluate, read_report
        try:
            capture=read_report(a.capture) if a.capture else None
        except (OSError,ValueError,json.JSONDecodeError) as exc:
            p.error(f'cannot read qualification capture: {exc}')
        obj=evaluate(capture)
    elif a.command=='mcp-discover':
        from fabintel.mcp_adapter import ReadOnlyMCPAdapter
        try:
            adapter=ReadOnlyMCPAdapter.from_config(a.config)
            try:
                obj=adapter.discover()
            finally:
                adapter.client.close()
        except (OSError,ValueError,PermissionError,RuntimeError) as exc:
            p.error(f'MCP discovery failed closed: {exc}')
    elif a.command=='mcp-analyze':
        from fabintel.mcp_adapter import ReadOnlyMCPAdapter
        from fabintel.mcp_workflow import run_mcp_analysis
        try:
            adapter=ReadOnlyMCPAdapter.from_config(a.config)
            try:
                obj=run_mcp_analysis(adapter,a.plan_id,
                    time_window={'start':a.time_start,'end':a.time_end},top_k=a.top_k)
            finally:
                adapter.client.close()
        except (OSError,ValueError,PermissionError,RuntimeError) as exc:
            p.error(f'MCP analysis failed closed: {exc}')
        validate_envelope(obj)
        if a.output:
            Path(a.output).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf8')
            print('WROTE evidence envelope:',a.output,file=sys.stderr)
            return
    elif a.command=='catalog':
        obj={'catalog_version':'SYNTHETIC-1','tables':synthetic_catalog(a.tables)}
        if a.output:
            Path(a.output).write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8')
            print('WROTE SYNTHETIC catalog:',a.output, file=sys.stderr)
            return
    elif a.command=='analyze':
        path=Path(a.input)
        if path.stat().st_size > 10*1024*1024:
            p.error('input exceeds the 10 MiB request limit')
        try:
            data=json.loads(path.read_text(encoding='utf8'))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:
            p.error(f'input must be valid UTF-8 JSON: {exc}')
        if not isinstance(data,dict):
            p.error('input must be a JSON object')
        obj=analyze(data)
        validate_envelope(obj)
        if a.output:
            Path(a.output).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n',encoding='utf8')
            print('WROTE evidence envelope:',a.output,file=sys.stderr)
            return
    else:
        data=json.loads((BASE/'fixtures'/'p3_integrated_synthetic.json').read_text(encoding='utf8'))
        obj=analyze(data)
        validate_envelope(obj)
    print(json.dumps(obj,indent=2,sort_keys=True))

if __name__=='__main__': main()
