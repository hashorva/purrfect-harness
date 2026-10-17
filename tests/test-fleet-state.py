#!/usr/bin/env python3
"""Mounted regressions for the public frozen-fleet policy entry points."""
import hashlib, json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FLEET_STATE=Path(os.environ.get('FLEET_STATE', ROOT/'scripts/fleet_state.py'))
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
    assert inventory['$defs']['family']=={'type':'string','pattern':'^[a-z][a-z0-9._-]*$'}
    for provider_def in ('agyPremium','claudePremium','codexPremium','cursorPremium'):
      rule=inventory['$defs'][provider_def]['allOf'][1]['properties']
      assert 'family' not in rule
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
    # 2.3.2: version beats digit sums and effort; dates only break ties; fast is never automatic.
    for models, expected in (
      (['gpt-terra-4.5-high','gpt-terra-5-high'],'gpt-terra-5-high'),
      (['gpt-terra-5.10','gpt-terra-5.6'],'gpt-terra-5.10'),
      (['gpt-terra-4-1-20250805','gpt-terra-5-5'],'gpt-terra-5-5'),
      (['gpt-terra-3.1-high','gpt-terra-3.6-low'],'gpt-terra-3.6-low'),
      (['gpt-terra-5-preview','gpt-terra-4'],'gpt-terra-4'),
      (['gpt-terra-5-high-fast','gpt-terra-4-low'],'gpt-terra-4-low'),
    ):
      write(home/'.codex/models_cache.json',{'models':models+['gpt-sol-1','gpt-luna-1']})
      selected=d/'selected.json'; run('/bin/bash',str(public),'--json','--out',str(selected),env=env)
      assert json.loads(selected.read_text())['seats']['codex.premium']['model']==expected, (models, expected)
    # A successful list with only fast variants (or no family member) is an honest
    # unavailable seat; the inventory itself must still validate and write.
    write(home/'.codex/models_cache.json',{'models':['gpt-terra-9-fast','gpt-sol-1','gpt-luna-1']})
    selected=d/'selected.json'; run('/bin/bash',str(public),'--json','--out',str(selected),env=env)
    seat=json.loads(selected.read_text())['seats']['codex.premium']
    assert (seat['model'],seat['source'],seat['health'])==('unavailable','unavailable','unknown'), seat
    # Real CLI output shapes. Grok Build owns a bare `agent`; Cursor must be probed as `cursor-agent`.
    clis=d/'clis'; clis.mkdir()
    stub(clis,'agent',"printf '%s\\n' 'Available models:' '  * grok-4.7 (default)' '  - grok-4.7-build-fast'")
    stub(clis,'cursor-agent',"[ \"$1\" = models ] || exit 2\nprintf '%s\\n' 'Available models' '' 'auto - Auto (default)' 'composer-2.5 - Composer 2.5' 'composer-2.5-fast - Composer 2.5 Fast' 'grok-4.7-xhigh - Grok 4.7  Extra High' 'grok-4.7-xhigh-fast - Grok 4.7  Extra High Fast' 'cursor-grok-4.5-high - Grok 4.5'")
    stub(clis,'agy',"[ \"$1\" = models ] || exit 2\nprintf '%s\\n' 'gemini-3.8-flash-high     Gemini 3.8 Flash (High)' 'gemini-3.8-flash-low      Gemini 3.8 Flash (Low)' 'claude-opus-5-5-high      Claude Opus 5.5 (High)' 'gemini-4-argon-low        Gemini 4 Argon (Low)' 'gemini-4-argon-high       Gemini 4 Argon (High)'")
    cli_env={**env,'PATH':str(clis)+os.pathsep+env['PATH']}; real=d/'real-clis.json'
    run('/bin/bash',str(public),'--json','--out',str(real),env=cli_env); doc=json.loads(real.read_text())
    assert doc['providers']['agent']['status']=='success' and doc['providers']['agent']['path'].endswith('/cursor-agent')
    assert doc['seats']['cursor.economy']['model']=='composer-2.5' and doc['seats']['cursor.premium']['model']=='grok-4.7-xhigh'
    assert doc['seats']['agy.economy']['model']=='gemini-3.8-flash-high' and doc['seats']['agy.economy']['source']=='observed'
    assert doc['seats']['agy.premium']['model']=='gemini-4-argon-high' and doc['seats']['agy.premium']['family']=='argon' and doc['seats']['agy.premium']['source']=='observed'
    # T-053: ranked families, unlisted models, registry-only family discovery.
    sys.path.insert(0,str(ROOT/'scripts'))
    import copy
    import harness_registry as H
    import fleet_state as F
    agy_nova_stub="[ \"$1\" = models ] || exit 2\nprintf '%s\\n' 'gemini-3.8-flash-high     Gemini 3.8 Flash (High)' 'gemini-4-argon-high       Gemini 4 Argon (High)' 'gemini-5-nova-high        Gemini 5 Nova (High)'"
    stub(clis,'agy',agy_nova_stub)
    nova_inv=d/'nova-inventory.json'
    human=run('/bin/bash',str(public),'--out',str(nova_inv),env=cli_env)
    nova_doc=json.loads(nova_inv.read_text())
    assert nova_doc['seats']['agy.premium']['model']=='gemini-4-argon-high'
    assert nova_doc['seats']['agy.premium']['family']=='argon'
    assert 'gemini-5-nova-high' in nova_doc['seats']['agy.premium']['unlisted']
    assert 'note: agy.premium unlisted: gemini-5-nova-high' in human.stdout
    run('/bin/bash',str(public),'--json','--out',str(nova_inv),env=cli_env)
    nova_mission=d/'docs/missions/t053'; nova_mission.mkdir(parents=True)
    bindings=d/'t053-bindings.json'
    write(bindings,{'agy.premium':{'family':'argon','effort':'high','speed':'unknown','doors':['agy']}})
    policy=d/'t053-policy.json'
    write(policy,{'billing_classes':['included'],'fast':False,'no_zdr':'forbid'})
    frozen=run('python3',str(FLEET_STATE),'freeze-v2','--mission-dir',str(nova_mission),'--inventory',str(nova_inv),'--bindings',str(bindings),'--policy',str(policy),'--approved-by','test','--approved-at','2026-10-17T00:00:00Z')
    frozen_doc=json.loads(frozen.stdout)
    assert frozen_doc['seats']['agy.premium']['approved_resolution']['model']=='gemini-4-argon-high'
    reg_path=d/'harness-registry.json'
    reg=copy.deepcopy(H.load_registry())
    reg['seat_specs']['agy.premium']=['agy','nova','argon']
    write(reg_path,reg)
    reg_env={**cli_env,'HARNESS_REGISTRY':str(reg_path)}
    nova2_inv=d/'nova2-inventory.json'
    run('/bin/bash',str(public),'--json','--out',str(nova2_inv),env=reg_env)
    nova2_doc=json.loads(nova2_inv.read_text())
    assert nova2_doc['seats']['agy.premium']['model']=='gemini-5-nova-high'
    assert nova2_doc['seats']['agy.premium']['family']=='nova'
    assert 'gemini-5-nova-high' not in nova2_doc['seats']['agy.premium']['unlisted']
    drift_log=d/'.tasks/drift/t053.jsonl'
    if drift_log.exists(): drift_log.unlink()
    resolved=run('python3',str(FLEET_STATE),'resolve','--fleet',str(nova_mission/'fleet.json'),'--seat','agy.premium','--inventory',str(nova2_inv),'--root',str(d),'--mission-path',str(nova_mission),env=reg_env)
    assert json.loads(resolved.stdout)['model']=='gemini-5-nova-high'
    events=[json.loads(line) for line in drift_log.read_text().splitlines()]
    assert events[-1]['from']['model']=='gemini-4-argon-high' and events[-1]['to']['model']=='gemini-5-nova-high'
    bad_unlisted=copy.deepcopy(nova_doc)
    bad_unlisted['seats']['agy.premium']['unlisted']='bad'
    reject(('python3',str(FLEET_STATE),'validate-inventory'),d/'bad-unlisted-type.json',bad_unlisted)
    bad_unlisted2=copy.deepcopy(nova_doc)
    bad_unlisted2['seats']['agy.premium']['unlisted']=['']
    reject(('python3',str(FLEET_STATE),'validate-inventory'),d/'bad-unlisted-empty.json',bad_unlisted2)
    dup=copy.deepcopy(reg); dup['seat_specs']['agy.premium']=['agy','argon','argon']
    try: H.validate_registry(dup)
    except H.RegistryError: pass
    else: raise AssertionError('duplicate families accepted')
    unsafe=copy.deepcopy(reg); unsafe['seat_specs']['agy.premium']=['agy','Nova!']
    try: H.validate_registry(unsafe)
    except H.RegistryError: pass
    else: raise AssertionError('unsafe family accepted')
    assert F.choose(['gemini-4-argonx-high'],'argon') is None
    write(home/'.codex/models_cache.json',{'models':['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna']})
    # A bad cache is a current failure and retains the old record byte-for-byte semantically.
    (home/'.codex/models_cache.json').write_text('{bad')
    run('/bin/bash',str(public),'--json','--out',str(inv),env=env); second=json.loads(inv.read_text())
    assert second['providers']['codex']['status']=='failure' and second['last_good']['codex']==old
    assert second['seats']['codex.premium']['source']=='last_good' and second['seats']['codex.premium']['health']=='degraded'
    # First-run failure must not guess a model; no empty model can validate.
    fresh=d/'fresh.json'; run('/bin/bash',str(public),'--json','--out',str(fresh),env=env); f=json.loads(fresh.read_text())
    assert f['seats']['codex.premium']['source']=='unavailable' and f['seats']['codex.premium']['model']=='unavailable'
    historical=json.loads(fresh.read_text()); historical['seats']['codex.premium'].update(model='gpt-5.6-terra',health='degraded',source='fallback')
    write(d/'historical-fallback-inventory.json',historical); run('python3',str(FLEET_STATE),'validate-inventory',str(d/'historical-fallback-inventory.json'))
    bad=json.loads(fresh.read_text()); bad['seats']['codex.premium']['model']=''; reject(('python3',str(FLEET_STATE),'validate-inventory'),d/'bad.json',bad)
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
      ('healthy-fallback',lambda x:(x['seats']['codex.premium'].update(model='gpt-5.6-terra',health='healthy',source='fallback'))),
      ('alias-non-claude',lambda x:(x['seats']['codex.premium'].__setitem__('source','alias'),x['seats']['codex.premium'].__setitem__('health','healthy'))),
      ('observed-claude',lambda x:(x['seats']['brain'].__setitem__('source','observed'),x['seats']['brain'].__setitem__('health','healthy'))),
    ):
      candidate=json.loads(json.dumps(second if label in {'partial-last-good','unknown-last-good'} else json.loads(fresh.read_text())))
      mutate(candidate)
      write(d/(label+'.json'),candidate)
      rejected=run('python3',str(FLEET_STATE),'validate-inventory',str(d/(label+'.json')),ok=False)
      if label=='healthy-fallback': assert rejected.stderr.strip()=='ERROR: inventory.seats.codex.premium invalid fallback source', rejected.stderr
    for label, base in (('fallback-retained-guard',second),('fallback-current-unavailable-guard',json.loads(fresh.read_text()))):
      candidate=json.loads(json.dumps(base)); candidate['seats']['codex.premium'].update(model='gpt-5.6-terra',health='degraded',source='fallback')
      if label=='fallback-current-unavailable-guard':
        provider=candidate['providers']['codex']; caps=provider['capabilities']; provider.clear(); provider.update(probed_at=candidate['probed_at'],capabilities=caps,status='unavailable',error='not on PATH')
      path=d/(label+'.json'); write(path,candidate)
      rejected=run('python3',str(FLEET_STATE),'validate-inventory',str(path),ok=False)
      assert rejected.stderr.strip()=='ERROR: inventory.seats.codex.premium invalid fallback source', rejected.stderr
    corrupt=b'{not json'; inv.chmod(0o644); inv.write_bytes(corrupt); run('/bin/bash',str(public),'--out',str(inv),env=env,ok=False); assert inv.read_bytes()==corrupt
    fallback_bindings=d/'fallback-bindings.json'; write(fallback_bindings,{'worker':{'inventory_seat':'codex.premium','effort':'medium','speed':'unknown'}})
    # Historical fallback inventories remain readable, but v1 freeze refuses every fallback model.
    for label, model in (('forged', 'gpt-forged-terra-99'), ('real-looking', 'gpt-5.6-terra')):
      fallback=json.loads(fresh.read_text()); fallback['seats']['codex.premium'].update(model=model,health='degraded',source='fallback')
      fallback_inv=d/(label+'-fallback-inventory.json'); write(fallback_inv,fallback)
      run('python3',str(FLEET_STATE),'validate-inventory',str(fallback_inv))
      fallback_mission=d/(label+'-fallback-mission'); fallback_mission.mkdir()
      fallback_fleet=fallback_mission/'fleet.json'
      result=run('python3',str(FLEET_STATE),'freeze','--mission-dir',str(fallback_mission),'--inventory',str(fallback_inv),'--bindings',str(fallback_bindings),'--approved-by','human','--approved-at','2026-08-21T00:00:00Z',ok=False)
      assert result.stderr.strip()=='ERROR: binding worker uses seat codex.premium with source fallback; fallback bindings are no longer allowed', result.stderr
      assert not fallback_fleet.exists(), fallback_fleet
    # Restore trusted inventory and freeze exact bytes into a canonical no-clobber snapshot.
    write(inv,second); bindings=d/'bindings.json'; write(bindings,{'worker':{'inventory_seat':'codex.premium','effort':'medium','speed':'unknown'}})
    mission=d/'docs/missions/x'; mission.mkdir(parents=True); fleet=mission/'fleet.json'
    run('python3',str(FLEET_STATE),'freeze','--mission-dir',str(mission),'--inventory',str(inv),'--bindings',str(bindings),'--approved-by','human','--approved-at','2026-08-21T00:00:00Z')
    frozen=fleet.read_bytes(); data=json.loads(frozen); assert data['inventory']['sha256']==hashlib.sha256(inv.read_bytes()).hexdigest() and stat.S_IMODE(fleet.stat().st_mode)==0o444
    run('python3',str(FLEET_STATE),'freeze','--mission-dir',str(mission),'--inventory',str(inv),'--bindings',str(bindings),'--approved-by','human','--approved-at','2026-08-21T00:00:00Z',ok=False); assert fleet.read_bytes()==frozen
    # Resolution reads only fleet: remove inventory and assert all equality/capability failure paths.
    inv.unlink(); good=run('python3',str(FLEET_STATE),'resolve','--fleet',str(fleet),'--seat','worker'); assert json.loads(good.stdout)['model']=='gpt-5.6-terra'
    for flag,value in (('--provider','agent'),('--model','wrong'),('--effort','high'),('--speed','fast')): run('python3',str(FLEET_STATE),'resolve','--fleet',str(fleet),'--seat','worker',flag,value,ok=False)
    run('python3',str(FLEET_STATE),'resolve','--fleet',str(fleet),'--seat','missing',ok=False)
    run('python3',str(FLEET_STATE),'resolve','--fleet',str(d/'missing-fleet.json'),'--seat','worker',ok=False)
    fleet.chmod(0o644); fleet.write_bytes(frozen+b' '); run('python3',str(FLEET_STATE),'validate-fleet',str(fleet),ok=False); fleet.write_bytes(frozen); fleet.chmod(0o444)
    unapproved=json.loads(frozen); unapproved['approval']['status']='draft'; write(d/'unapproved.json',unapproved); run('python3',str(FLEET_STATE),'validate-fleet',str(d/'unapproved.json'),ok=False)
    unsupported=json.loads(frozen); unsupported['seats']['worker']['effort']='bogus'; write(d/'unsupported.json',unsupported); run('python3',str(FLEET_STATE),'validate-fleet',str(d/'unsupported.json'),ok=False)
    # Degraded Claude provenance is valid for retained and fallback bindings.
    for source in ('last_good','fallback'):
      claude_degraded=json.loads(frozen)
      claude_degraded['seats']['worker'].update(provider='claude',model='sonnet',family='sonnet',speed='unknown',health='degraded',source=source,capabilities={'efforts':['low','medium','high','xhigh','max'],'speeds':['unknown']})
      write(d/(source+'-claude.json'),claude_degraded)
      run('python3',str(FLEET_STATE),'validate-fleet',str(d/(source+'-claude.json')))
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
      candidate=json.loads(frozen); mutate(candidate); reject(('python3',str(FLEET_STATE),'validate-fleet'),d/(label+'.json'),candidate)
    require_schema_policy()
  print('fleet policy tests passed')
if __name__=='__main__': main()
