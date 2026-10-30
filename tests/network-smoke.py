#!/usr/bin/env python3
"""Run only on an ephemeral CI runner, never on either Paseo server."""
import http.server,json,os,subprocess,sys,threading,urllib.request
from pathlib import Path

def run(*args,check=True):return subprocess.run(list(args),check=check,capture_output=True,text=True,timeout=90)
def main():
 if os.getenv('GITHUB_ACTIONS')!='true' or os.geteuid()!=0:raise SystemExit('Exclusivo de runner efêmero GitHub Actions com root.')
 if run('docker','network','inspect','paseo-workers',check=False).returncode==0:raise SystemExit('Rede já existe: não alterar um ambiente desconhecido.')
 root=Path(__file__).resolve().parents[1];image='busybox:1.37.0'
 run('docker','pull',image)
 class Handler(http.server.BaseHTTPRequestHandler):
  def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'host reachable')
  def log_message(self,*args):pass
 server=http.server.ThreadingHTTPServer(('0.0.0.0',0),Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}',timeout=3) as r:assert r.status==200
  run(sys.executable,str(root/'deploy/hardening/prepare-worker-network.py'),'--apply')
  net=json.loads(run('docker','network','inspect','paseo-workers').stdout)[0]
  assert not net['EnableIPv6']
  gateway=net['IPAM']['Config'][0]['Gateway']
  def worker(*args):return run('docker','run','--rm','--network','paseo-workers','--cap-drop','ALL','--read-only',image,*args,check=False)
  assert worker('wget','-T','3','-q','-O','-',f'http://{gateway}:{server.server_port}').returncode!=0,'Acesso ao host não foi bloqueado'
  assert worker('wget','-T','3','-q','-O','-','http://169.254.169.254/latest/meta-data/').returncode!=0,'Metadata não foi bloqueado'
  assert worker('nslookup','example.com').returncode==0,'DNS público precisa funcionar'
  print('Docker bridge: acesso ao host/metadata bloqueado; IPv6 desligado; DNS externo funcionando.')
 finally:
  server.shutdown();server.server_close()
  run('iptables','-w','-D','INPUT','-i','br-paseowork','-j','DROP',check=False)
  run('iptables','-w','-D','DOCKER-USER','-i','br-paseowork','-j','PASEO_WORK_EGRESS',check=False)
  run('iptables','-w','-F','PASEO_WORK_EGRESS',check=False);run('iptables','-w','-X','PASEO_WORK_EGRESS',check=False)
  run('docker','network','rm','paseo-workers',check=False)
if __name__=='__main__':main()
