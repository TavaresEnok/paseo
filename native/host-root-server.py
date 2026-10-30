#!/usr/bin/env python3
"""Local root-command bridge, restricted to Paseo manager containers."""
import json, os, re, socket, socketserver, struct, subprocess, tempfile, threading
from pathlib import Path
ROOT='/home/enok/Documentos/projetos'
HOME=Path('/home/enok/srv_projetos/runtime/isolated')
class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  try:
   pid,uid,gid=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
   if uid!=1000: raise PermissionError('Unexpected peer user')
   cgroup=Path('/proc/%s/cgroup'%pid).read_text()
   match=re.search(r'/docker/([a-f0-9]{64})(?:\n|$)',cgroup)
   if not match: raise PermissionError('Manager container required')
   info=json.loads(subprocess.check_output(['/usr/bin/docker','inspect',match[1]],timeout=10))[0]
   labels=info['Config'].get('Labels') or {}
   if labels.get('paseo.orchestrator.managed')!='true' or labels.get('paseo.provider') not in ('claude','codex') or info['Config']['WorkingDir'].rstrip('/')!=ROOT:
    raise PermissionError('Only manager sessions at the approved project root may use host root')
   request=json.loads(self.rfile.readline(131073))
   command=request.get('command')
   if not isinstance(command,str) or not command.strip() or len(command)>65536: raise ValueError('Command required, max 65536 characters')
   timeout=max(1,min(int(request.get('timeout',300)),3600))
   with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
    try:
     result=subprocess.run(['/usr/bin/sudo','-n','-H','/usr/bin/timeout','--kill-after=5',str(timeout)+'s','/bin/bash','--noprofile','--norc','-c',command],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=timeout+15)
     code=result.returncode
    except subprocess.TimeoutExpired:
     code=124
    out.seek(0);err.seek(0)
    response={'returncode':code,'stdout':out.read(2097152).decode(errors='replace'),'stderr':err.read(2097152).decode(errors='replace')}
  except Exception as exc:
   response={'returncode':126,'stdout':'','stderr':str(exc)+'\n'}
  self.wfile.write((json.dumps(response)+'\n').encode())
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
 daemon_threads=True
servers=[]
for provider in ('claude','codex'):
 directory=HOME/provider/'home/.paseo-host-admin'
 directory.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(directory,0o700)
 path=directory/'root.sock'
 if path.exists():path.unlink()
 server=Server(str(path),Handler);os.chmod(path,0o600)
 servers.append(server)
for server in servers[:-1]:threading.Thread(target=server.serve_forever,daemon=True).start()
servers[-1].serve_forever()
