import json,os,sys,tempfile
from unittest.mock import patch
sys.path.insert(0,'mytree')
from app.server import Handler,MyTreeHTTPServer
with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'),patch.dict(os.environ,{'MYTREE_AUTH_MODE':''}):
 server=MyTreeHTTPServer(('127.0.0.1',0),Handler);print(json.dumps({'base':'http://127.0.0.1:'+str(server.server_address[1])}),flush=True);server.serve_forever()
