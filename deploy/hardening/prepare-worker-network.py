#!/usr/bin/env python3
"""Print a dedicated worker bridge/firewall plan; execute only with --apply as root.

This script never runs on import. Run at the later maintenance boundary, before
activating the staged autonomy configuration. No existing services are stopped.
"""
import argparse,json,os,shutil,subprocess
NETWORK='paseo-workers';BRIDGE='br-paseowork';CHAIN='PASEO_WORK_EGRESS'
PRIVATE=['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','198.18.0.0/15','224.0.0.0/4','240.0.0.0/4']

def firewall():
    rules=['*filter',':'+CHAIN+' - [0:0]','-F '+CHAIN]
    rules += ['-A '+CHAIN+' -d '+cidr+' -j REJECT' for cidr in PRIVATE]
    rules += ['-A '+CHAIN+' -j RETURN','COMMIT','']
    return '\n'.join(rules)

def plan():
    return {'network':NETWORK,'bridge':BRIDGE,'driver':'bridge','ipv6':False,'icc':False,'forward_rules':firewall(),'input_rule':['INPUT','-i',BRIDGE,'-j','DROP'],'forward_jump':['DOCKER-USER','-i',BRIDGE,'-j',CHAIN]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:print(json.dumps(plan(),indent=2));return
    if os.geteuid()!=0:raise SystemExit('Use root somente na aplicação posterior.')
    for binary in ('docker','iptables','iptables-restore'):
        if not shutil.which(binary):raise SystemExit('Pré-requisito ausente: '+binary)
    existing=subprocess.run(['docker','network','inspect',NETWORK],capture_output=True,text=True)
    if existing.returncode:
        subprocess.run(['docker','network','create','--driver','bridge','--opt','com.docker.network.bridge.name='+BRIDGE,'--opt','com.docker.network.bridge.enable_icc=false',NETWORK],check=True)
    else:
        net=json.loads(existing.stdout)[0]
        if net.get('Driver')!='bridge' or net.get('EnableIPv6') or net.get('Options',{}).get('com.docker.network.bridge.name')!=BRIDGE or net.get('Options',{}).get('com.docker.network.bridge.enable_icc')!='false':raise SystemExit('Rede existente divergente; não a substituir automaticamente.')
    # Install the policy atomically in our chain. Never flush Docker/host rules.
    subprocess.run(['iptables','-w','-S','DOCKER-USER'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['iptables-restore','--wait','--noflush'],input=firewall(),text=True,check=True)
    for rule in (plan()['input_rule'],plan()['forward_jump']):
        if subprocess.run(['iptables','-w','-C',*rule],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['iptables','-w','-I',rule[0],'1',*rule[1:]],check=True)
    print('Rede e isolamento IPv4 aplicados; IPv6 da bridge desativado.')
if __name__=='__main__':main()
