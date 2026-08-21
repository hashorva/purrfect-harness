#!/usr/bin/env python3
"""Mounted regressions for the public frozen-fleet policy entry points."""
import hashlib, json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def run(*args, env=None, ok=True):
    p=subprocess.run(args,text=True,capture_output=True,env=env)
    if ok != (p.returncode == 0): raise AssertionError(f"{args}: {p.returncode}: {p.stderr}")
    return p
def write(p, value): p.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n')
def stub(path,name,body):
    p=path/name; p.write_text('#!/usr/bin/env bash\n'+body+'\n'); p.chmod(0o755)
def main():
  with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp); bin=d/'bin'; bin.mkdir(); home=d/'home'; (home/'.codex').mkdir(parents=True)
    # First inventory: Codex observed; all other providers deliberately absent.
    stub(bin,'codex','exit 0'); write(home/'.codex/models_cache.json',{'models':['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna']})
    env={**os.environ,'PATH':str(bin)+os.pathsep+os.environ['PATH'],'HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1'}; inv=d/'inventory.json'
    public=ROOT/'scripts/fleet-inventory.sh'; run('/bin/bash',str(public),'--json','--out',str(inv),env=env)
    first=json.loads(inv.read_text()); old=first['last_good']['codex']; assert first['seats']['codex.premium']['health']=='healthy'
    # A bad cache is a current failure and retains the old record byte-for-byte semantically.
    (home/'.codex/models_cache.json').write_text('{bad')
    run('/bin/bash',str(public),'--json','--out',str(inv),env=env); second=json.loads(inv.read_text())
    assert second['providers']['codex']['status']=='failure' and second['last_good']['codex']==old
    assert second['seats']['codex.premium']['source']=='last_good' and second['seats']['codex.premium']['health']=='degraded'
    # First-run failure only permits degraded fallback; no empty model can validate.
    fresh=d/'fresh.json'; run('/bin/bash',str(public),'--json','--out',str(fresh),env=env); f=json.loads(fresh.read_text()); assert f['seats']['codex.premium']['source']=='fallback'
    bad=json.loads(fresh.read_text()); bad['seats']['codex.premium']['model']=''; write(d/'bad.json',bad); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-inventory',str(d/'bad.json'),ok=False)
    corrupt=b'{not json'; inv.chmod(0o644); inv.write_bytes(corrupt); run('/bin/bash',str(public),'--out',str(inv),env=env,ok=False); assert inv.read_bytes()==corrupt
    # Restore trusted inventory and freeze exact bytes into a canonical no-clobber snapshot.
    write(inv,second); bindings=d/'bindings.json'; write(bindings,{'worker':{'inventory_seat':'codex.premium','effort':'medium','speed':'unknown'}})
    mission=d/'docs/missions/x'; mission.mkdir(parents=True); fleet=mission/'fleet.json'
    run('python3',str(ROOT/'scripts/fleet_state.py'),'freeze','--mission-dir',str(mission),'--inventory',str(inv),'--bindings',str(bindings),'--approved-by','human','--approved-at','2026-08-21T00:00:00Z')
    frozen=fleet.read_bytes(); data=json.loads(frozen); assert data['inventory']['sha256']==hashlib.sha256(inv.read_bytes()).hexdigest() and stat.S_IMODE(fleet.stat().st_mode)==0o444
    run('python3',str(ROOT/'scripts/fleet_state.py'),'freeze','--mission-dir',str(mission),'--inventory',str(inv),'--bindings',str(bindings),'--approved-by','human','--approved-at','2026-08-21T00:00:00Z',ok=False); assert fleet.read_bytes()==frozen
    # Resolution reads only fleet: remove inventory and assert all equality/capability failure paths.
    inv.unlink(); good=run('python3',str(ROOT/'scripts/fleet_state.py'),'resolve','--fleet',str(fleet),'--seat','worker'); assert json.loads(good.stdout)['model']=='gpt-5.6-terra'
    for flag,value in (('--provider','agent'),('--model','wrong'),('--effort','high'),('--speed','fast')): run('python3',str(ROOT/'scripts/fleet_state.py'),'resolve','--fleet',str(fleet),'--seat','worker',flag,value,ok=False)
    run('python3',str(ROOT/'scripts/fleet_state.py'),'resolve','--fleet',str(fleet),'--seat','missing',ok=False)
    fleet.chmod(0o644); fleet.write_bytes(frozen+b' '); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(fleet),ok=False); fleet.write_bytes(frozen); fleet.chmod(0o444)
    unapproved=json.loads(frozen); unapproved['approval']['status']='draft'; write(d/'unapproved.json',unapproved); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(d/'unapproved.json'),ok=False)
    unsupported=json.loads(frozen); unsupported['seats']['worker']['effort']='bogus'; write(d/'unsupported.json',unsupported); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(d/'unsupported.json'),ok=False)
    # Guard proof 1: bypass retention in an isolated mounted public entry, which must fail this proof.
    copy=d/'copy'; (copy/'scripts').mkdir(parents=True); shutil.copy2(ROOT/'scripts/fleet_state.py',copy/'scripts/fleet_state.py'); shutil.copy2(ROOT/'scripts/fleet-inventory.sh',copy/'scripts/fleet-inventory.sh')
    altered=(copy/'scripts/fleet_state.py'); altered.write_text(altered.read_text().replace('retained=dict(previous)','retained={}'))
    guard=d/'guard.json'; (home/'.codex/models_cache.json').write_text(json.dumps({'models':['gpt-5.6-terra']})); run('/bin/bash',str(copy/'scripts/fleet-inventory.sh'),'--out',str(guard),env=env); (home/'.codex/models_cache.json').write_text('{bad'); run('/bin/bash',str(copy/'scripts/fleet-inventory.sh'),'--out',str(guard),env=env)
    assert json.loads(guard.read_text())['seats']['codex.premium']['source']!='last_good'
    # Guard proof 2: an isolated resolver changed to read mutable inventory fails
    # despite a valid frozen fleet, proving the mounted resolution test is non-vacuous.
    altered.write_text(altered.read_text().replace('doc,_=read_json(args.fleet,"fleet",require_canonical=True); validate_fleet(doc); seat=', 'doc,_=read_json(args.fleet,"fleet",require_canonical=True); read_json("/definitely/missing/inventory.json","inventory"); validate_fleet(doc); seat='))
    run('python3',str(altered),'resolve','--fleet',str(fleet),'--seat','worker',ok=False)
  print('fleet policy tests passed')
if __name__=='__main__': main()
