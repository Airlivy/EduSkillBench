"""Unauthenticated connectivity checks; no prompts, credentials or model calls."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from repro.judge import request_deadline, atomic_json

URL='https://ark.cn-beijing.volces.com/api/plan/v1/messages'

def main():
    out=Path('jobs/repair-audit/transport-probe-20261001')
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for attempt in range(2):
        for route in ('environment_proxy','direct'):
            handler=urllib.request.ProxyHandler() if route=='environment_proxy' else urllib.request.ProxyHandler({})
            opener=urllib.request.build_opener(handler)
            started=time.monotonic()
            row={'attempt':attempt+1,'route':route}
            try:
                with request_deadline(20):
                    with opener.open(urllib.request.Request(URL,method='GET'),timeout=15) as response:
                        row.update(http_status=response.status,tls_and_http_reached=True)
            except urllib.error.HTTPError as exc:
                # Authentication/method errors are expected: reaching HTTP proves TLS worked.
                row.update(http_status=exc.code,tls_and_http_reached=True)
                exc.close()
            except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
                reason=getattr(exc,'reason',exc)
                row.update(tls_and_http_reached=False,exception_type=type(exc).__name__,reason_type=type(reason).__name__,errno=getattr(reason,'errno',None))
            row['elapsed_seconds']=round(time.monotonic()-started,3)
            rows.append(row);atomic_json(out/'results.json',rows)
            print(json.dumps(row),flush=True)

if __name__=='__main__':main()
