"""Read-only localhost CEF diagnostics, without printing session URLs or titles.

Does not launch the game, enable debugging, execute page scripts, or install.
"""
import argparse
import json
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


def endpoint(port):
    if isinstance(port,bool) or not isinstance(port,int) or not 1024<=port<=65535:
        raise ValueError('Port must be an integer between 1024 and 65535')
    return f'http://127.0.0.1:{port}'


def summarize(version, targets):
    pages=[]
    for target in targets:
        if target.get('type')!='page':continue
        try:
            url=urlsplit(target.get('url',''))
            hostname=url.hostname if url.scheme in {'https','http'} else None
        except ValueError:
            hostname=None
        pages.append({'hostname':hostname,'store_candidate':hostname=='store.lotro.com',
                      'debugger_available':bool(target.get('webSocketDebuggerUrl'))})
    return {'browser':version.get('Browser'),'protocol_version':version.get('Protocol-Version'),
            'pages':pages,'read_only':True,'page_script_executed':False,
            'session_urls_recorded':False,'game_ownership_verified':False}


def probe(port):
    base=endpoint(port)
    class LocalOnly(ProxyHandler):
        def __init__(self):super().__init__({})
    # Do not follow redirects to a remote site, even if a non-CEF service
    # happens to be listening on the selected local port.
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=build_opener(LocalOnly(),NoRedirect())
    def read(path):
        with opener.open(base+path,timeout=3) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Diagnostic response exceeds limit')
            return json.loads(raw)
    return summarize(read('/json/version'),read('/json/list'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    try:
        result=probe(args.port)
    except (OSError,ValueError,TypeError) as error:
        # Connection exceptions can include URLs; expose only the error type.
        print(json.dumps({'available':False,'error_type':type(error).__name__,
                          'note':'Local CEF endpoint unavailable or invalid; no game settings changed.'}))
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
