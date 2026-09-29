"""Owned loopback state oracle, independent of resolver/runner telemetry.
Only the MCP adapter's attempted mutations write it. Values stay in memory.
No Driver, GUI, model provider, or browser is used.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
import json, threading


@contextmanager
def oracle(token, scenario):
    state = {'submitted': None, 'type_count': 0, 'submit_count': 0, 'wrong_submissions': 0, 'reads': 0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self, data, status=200):
            raw = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path == '/state':
                state['reads'] += 1
                if scenario == 'verification-unavailable' and state['type_count']:
                    return self.send({'status':'unavailable'},503)
                submitted = None if scenario == 'verification-unknown' else state['submitted']
                return self.send({'submitted':submitted})
            if self.path == '/audit':
                return self.send({'type_count':state['type_count'],'submit_count':state['submit_count'],
                    'wrong_submissions':state['wrong_submissions'],'submitted_correct':state['submitted']==token,
                    'submitted_present':state['submitted'] is not None,'oracle_reads':state['reads']})
            self.send({},404)
        def do_POST(self):
            value = self.rfile.read(int(self.headers.get('Content-Length',0))).decode()
            if self.path == '/reset':
                state.update(submitted=None,type_count=0,submit_count=0,wrong_submissions=0,reads=0)
                self.send({},204)
            elif self.path == '/type':
                state['type_count'] += 1
                self.send({},204)
            elif self.path == '/submit':
                state['submit_count'] += 1
                state['submitted'] = value
                state['wrong_submissions'] += int(value != token)
                self.send({},204)
            else: self.send({},404)
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown(); server.server_close(); thread.join()
