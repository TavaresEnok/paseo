#!/usr/bin/env python3
"""Print a dedicated worker bridge/firewall plan; execute only with --apply as root.

This script never runs on import. Run at the later maintenance boundary, before
activating the staged autonomy configuration. No existing services are stopped.
"""
import argparse,json,os,shutil,subprocess
NETWORK='paseo-workers';BRIDGE='br-paseowork';CHAIN='PASEO_WORK_EGRESS';SUBNET='172.30.248.0/24'
PRIVATE=['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','198.18.0.0/15','224.0.0.0/4','240.0.0.0/4']

def firewall():
    rules=['*filter',':'+CHAIN+' - [0:0]','-F '+CHAIN]
    rules += ['-A '+CHAIN+' -d '+cidr+' -j REJECT' for cidr in PRIVATE]
    rules += ['-A '+CHAIN+' -j ACCEPT','COMMIT','']
    return '\n'.join(rules)

def plan():
    return {'network':NETWORK,'bridge':BRIDGE,'driver':'bridge','ipv6':False,'icc':False,'forward_rules':firewall(),'input_rule':['INPUT','-i',BRIDGE,'-j','DROP'],'forward_jump':['FORWARD','-i',BRIDGE,'-j',CHAIN], 'subnet':SUBNET}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:print(json.dumps(plan(),indent=2));return
    if os.geteuid()!=0:raise SystemExit('Use root somente na aplicação posterior.')
    for binary in ('docker','iptables','iptables-restore'):
        if not shutil.which(binary):raise SystemExit('Pré-requisito ausente: '+binary)
    # Do not change the host's selected iptables backend. Prefer Docker's
    # active chain if present; otherwise use the current host backend.
    ipt='iptables'
    for candidate in ('iptables','iptables-nft','iptables-legacy'):
        if shutil.which(candidate) and subprocess.run([candidate,'-w','-S','DOCKER-USER'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
            ipt=candidate;break
    restore=ipt+'-restore'
    if not shutil.which(restore):raise SystemExit('Backend de restore ausente: '+restore)
    existing=subprocess.run(['docker','network','inspect',NETWORK],capture_output=True,text=True)
    if existing.returncode:
        # The host may have a completely allocated default Docker address pool.
        import ipaddress
        routes=json.loads(subprocess.check_output(['ip','-j','-4','route','show'],text=True))
        for route in routes:
            destination=route.get('dst','default')
            if destination!='default' and ipaddress.ip_network(SUBNET).overlaps(ipaddress.ip_network(destination,strict=False)):raise SystemExit('Sub-rede já roteada: '+destination)
        subprocess.run(['docker','network','create','--driver','bridge','--subnet',SUBNET,'--opt','com.docker.network.bridge.name='+BRIDGE,'--opt','com.docker.network.bridge.enable_icc=false',NETWORK],check=True)
    else:
        net=json.loads(existing.stdout)[0]
        if net.get('Driver')!='bridge' or net.get('EnableIPv6') or net.get('Options',{}).get('com.docker.network.bridge.name')!=BRIDGE or net.get('Options',{}).get('com.docker.network.bridge.enable_icc')!='false' or not any(c.get('Subnet')==SUBNET for c in net.get('IPAM',{}).get('Config',[])):raise SystemExit('Rede existente divergente; não a substituir automaticamente.')
    # Install the policy atomically in our chain. Never flush Docker/host rules.
    subprocess.run([restore,'--wait','--noflush'],input=firewall(),text=True,check=True)
    inbound=['FORWARD','-o',BRIDGE,'-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT']
    inbound_drop=['FORWARD','-o',BRIDGE,'-j','DROP']
    # Insert drop first, then established allow above it. Our egress rule
    # precedes both. All hooks apply only to this dedicated bridge.
    for rule in (plan()['input_rule'],inbound_drop,inbound,plan()['forward_jump']):
        if subprocess.run([ipt,'-w','-C',*rule],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run([ipt,'-w','-I',rule[0],'1',*rule[1:]],check=True)
    masquerade=['POSTROUTING','-s',SUBNET,'!','-o',BRIDGE,'-j','MASQUERADE']
    if subprocess.run([ipt,'-w','-t','nat','-C',*masquerade],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run([ipt,'-w','-t','nat','-I',masquerade[0],'1',*masquerade[1:]],check=True)
    print('Rede e isolamento IPv4 aplicados; IPv6 da bridge desativado.')
if __name__=='__main__':main()
