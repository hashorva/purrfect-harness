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
def reject(command, path, value): write(path,value); run(*command,str(path),ok=False)
def stub(path,name,body):
    p=path/name; p.write_text('#!/usr/bin/env bash\n'+body+'\n'); p.chmod(0o755)
def conditional_rules(schema):
    return {(json.dumps(rule['if'],sort_keys=True),json.dumps(rule['then'],sort_keys=True)) for rule in schema['$defs']['seat']['allOf']}
def require_schema_policy():
    inventory=json.loads((ROOT/'schemas/fleet-inventory.schema.json').read_text())
    mission=json.loads((ROOT/'schemas/mission-fleet.schema.json').read_text())
    for schema, unavailable, effort in ((inventory,True,False),(mission,False,True)):
      rules=conditional_rules(schema)
      for provider, efforts, speeds in (
        ('claude',['low','medium','high','xhigh','max'],['unknown']),
        ('codex',['low','medium','high','xhigh'],['unknown']),
        ('agent',['low','medium','high','xhigh'],['standard','fast']),
        ('agy',['low','medium','high'],['unknown']),
      ):
        matching=[json.loads(then)['properties'] for before,then in rules if json.loads(before)=={'properties':{'provider':{'const':provider}}}]
        assert len(matching)==1 and matching[0]['capabilities']['const']=={'efforts':efforts,'speeds':speeds}
        if effort: assert matching[0]['effort']['enum']==efforts and matching[0]['speed'] == ({'const':speeds[0]} if len(speeds)==1 else {'enum':speeds})
      required=[
        ({'source':{'enum':['observed','alias']}},{'health':{'const':'healthy'}}),
        ({'source':{'enum':['last_good','fallback']}},{'health':{'const':'degraded'}}),
        ({'source':{'const':'alias'}},{'provider':{'const':'claude'}}),
        ({'source':{'const':'observed'}},{'provider':{'enum':['codex','agent','agy']}}),
      ]
      if unavailable: required.append(({'source':{'const':'unavailable'}},{'health':{'const':'unknown'},'model':{'const':'unavailable'}}))
      for condition, properties in required:
        assert (json.dumps({'properties':condition},sort_keys=True),json.dumps({'properties':properties},sort_keys=True)) in rules
def main():
  with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp); bin=d/'bin'; bin.mkdir(); home=d/'home'; (home/'.codex').mkdir(parents=True)
    # First inventory: Codex observed; all other providers deliberately absent.
    stub(bin,'codex','exit 0'); write(home/'.codex/models_cache.json',{'models':['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna']})
    env={**os.environ,'PATH':str(bin)+os.pathsep+os.environ['PATH'],'HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1'}; inv=d/'inventory.json'
    public=ROOT/'scripts/fleet-inventory.sh'; run('/bin/bash',str(public),'--json','--out',str(inv),env=env)
    first=json.loads(inv.read_text()); old=first['last_good']['codex']; assert first['seats']['codex.premium']['health']=='healthy'
    # The public inventory path preserves exact historical chooser scoring and input-order ties.
    for models, expected in (
      (['gpt-terra-9-high','gpt-terra-10-high'],'gpt-terra-10-high'),
      (['gpt-terra-10-fast-xhigh','gpt-terra-1-low'],'gpt-terra-1-low'),
      (['gpt-terra-1-low','gpt-terra-1-medium','gpt-terra-1-high','gpt-terra-1-max','gpt-terra-1-xhigh'],'gpt-terra-1-xhigh'),
      (['gpt-terra-z','gpt-terra-a'],'gpt-terra-z'),
      (['gpt-terra-100-breakfast','gpt-terra-1-low'],'gpt-terra-100-breakfast'),
      (['gpt-terra-20-low','gpt-terra-1-notxhighish'],'gpt-terra-20-low'),
    ):
      write(home/'.codex/models_cache.json',{'models':models+['gpt-sol-1','gpt-luna-1']})
      selected=d/'selected.json'; run('/bin/bash',str(public),'--json','--out',str(selected),env=env)
      assert json.loads(selected.read_text())['seats']['codex.premium']['model']==expected
    write(home/'.codex/models_cache.json',{'models':['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna']})
    # A bad cache is a current failure and retains the old record byte-for-byte semantically.
    (home/'.codex/models_cache.json').write_text('{bad')
    run('/bin/bash',str(public),'--json','--out',str(inv),env=env); second=json.loads(inv.read_text())
    assert second['providers']['codex']['status']=='failure' and second['last_good']['codex']==old
    assert second['seats']['codex.premium']['source']=='last_good' and second['seats']['codex.premium']['health']=='degraded'
    # First-run failure only permits degraded fallback; no empty model can validate.
    fresh=d/'fresh.json'; run('/bin/bash',str(public),'--json','--out',str(fresh),env=env); f=json.loads(fresh.read_text()); assert f['seats']['codex.premium']['source']=='fallback'
    bad=json.loads(fresh.read_text()); bad['seats']['codex.premium']['model']=''; reject(('python3',str(ROOT/'scripts/fleet_state.py'),'validate-inventory'),d/'bad.json',bad)
    # Exact nested inventory shape and provenance: this reproduces the formerly accepted forgery.
    for label, mutate in (
      ('partial-provider',lambda x:x['providers'].pop('codex')),
      ('partial-last-good',lambda x:x['last_good']['codex'].pop('path')),
      ('unknown-last-good',lambda x:x['last_good'].__setitem__('evil',x['last_good']['codex'])),
      ('invalid-timestamp',lambda x:x.__setitem__('probed_at','never')),
      ('provider-extra',lambda x:x['providers']['codex'].__setitem__('junk',True)),
      ('seat-extra',lambda x:x['seats']['codex.premium'].__setitem__('junk',True)),
      ('seat-family',lambda x:x['seats']['codex.premium'].__setitem__('family','luna')),
      ('seat-provider',lambda x:x['seats']['codex.premium'].__setitem__('provider','agent')),
      ('seat-capabilities',lambda x:x['seats']['codex.premium'].__setitem__('capabilities',{'efforts':['bogus'],'speeds':['wild']})),
      ('forged-healthy-source',lambda x:(x['seats']['codex.premium'].__setitem__('health','healthy'),x['seats']['codex.premium'].__setitem__('source','observed'))),
      ('healthy-fallback',lambda x:x['seats']['codex.premium'].__setitem__('health','healthy')),
      ('alias-non-claude',lambda x:(x['seats']['codex.premium'].__setitem__('source','alias'),x['seats']['codex.premium'].__setitem__('health','healthy'))),
      ('observed-claude',lambda x:(x['seats']['brain'].__setitem__('source','observed'),x['seats']['brain'].__setitem__('health','healthy'))),
    ):
      candidate=json.loads(json.dumps(second if label in {'partial-last-good','unknown-last-good'} else json.loads(fresh.read_text())))
      mutate(candidate); reject(('python3',str(ROOT/'scripts/fleet_state.py'),'validate-inventory'),d/(label+'.json'),candidate)
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
    run('python3',str(ROOT/'scripts/fleet_state.py'),'resolve','--fleet',str(d/'missing-fleet.json'),'--seat','worker',ok=False)
    fleet.chmod(0o644); fleet.write_bytes(frozen+b' '); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(fleet),ok=False); fleet.write_bytes(frozen); fleet.chmod(0o444)
    unapproved=json.loads(frozen); unapproved['approval']['status']='draft'; write(d/'unapproved.json',unapproved); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(d/'unapproved.json'),ok=False)
    unsupported=json.loads(frozen); unsupported['seats']['worker']['effort']='bogus'; write(d/'unsupported.json',unsupported); run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(d/'unsupported.json'),ok=False)
    # Degraded Claude provenance is valid for retained and fallback bindings.
    for source in ('last_good','fallback'):
      claude_degraded=json.loads(frozen)
      claude_degraded['seats']['worker'].update(provider='claude',model='sonnet',family='sonnet',speed='unknown',health='degraded',source=source,capabilities={'efforts':['low','medium','high','xhigh','max'],'speeds':['unknown']})
      write(d/(source+'-claude.json'),claude_degraded)
      run('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet',str(d/(source+'-claude.json')))
    for label, mutate in (
      ('invalid-hash',lambda x:x['inventory'].__setitem__('sha256','bad')),
      ('fleet-extra',lambda x:x.__setitem__('junk',True)),
      ('approval-extra',lambda x:x['approval'].__setitem__('junk',True)),
      ('empty-approval',lambda x:x['approval'].__setitem__('approved_by','')),
      ('invalid-approval-time',lambda x:x['approval'].__setitem__('approved_at','bad')),
      ('empty-seats',lambda x:x.__setitem__('seats',{})),
      ('empty-model',lambda x:x['seats']['worker'].__setitem__('model','')),
      ('forged-fleet-caps',lambda x:x['seats']['worker'].__setitem__('capabilities',{'efforts':['bogus'],'speeds':['wild']})),
      ('fleet-provider-family',lambda x:x['seats']['worker'].__setitem__('family','grok')),
      ('fleet-speed',lambda x:x['seats']['worker'].__setitem__('speed','fast')),
      ('fleet-alias-non-claude',lambda x:x['seats']['worker'].update(source='alias',health='healthy')),
      ('fleet-observed-claude',lambda x:x['seats']['worker'].update(provider='claude',model='sonnet',family='sonnet',source='observed',health='healthy',capabilities={'efforts':['low','medium','high','xhigh','max'],'speeds':['unknown']})),
      ('fleet-observed-degraded',lambda x:x['seats']['worker'].update(source='observed',health='degraded')),
      ('fleet-last-good-healthy',lambda x:x['seats']['worker'].update(source='last_good',health='healthy')),
      ('fleet-alias-degraded',lambda x:x['seats']['worker'].update(source='alias',health='degraded')),
    ):
      candidate=json.loads(frozen); mutate(candidate); reject(('python3',str(ROOT/'scripts/fleet_state.py'),'validate-fleet'),d/(label+'.json'),candidate)
    require_schema_policy()
  print('fleet policy tests passed')
if __name__=='__main__': main()
