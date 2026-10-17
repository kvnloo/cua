import os,sys,subprocess,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).parent
WORK=Path('/mnt/zer0models/promotion-first-20261016')
(ROOT/'logs').mkdir(exist_ok=True)
def run(label,cmd,cwd,extra=None,timeout=180):
 env=os.environ.copy()
 for key in ['PYTHONPATH','PYTHONHOME','DISPLAY','WAYLAND_DISPLAY','SWAYSOCK','HYPRLAND_INSTANCE_SIGNATURE','DBUS_SESSION_BUS_ADDRESS']:env.pop(key,None)
 env.update({'PYTHONDONTWRITEBYTECODE':'1','CUA_TELEMETRY_ENABLED':'false','CUA_DRIVER_BIN':str(WORK/'asserted-nonexistent-driver'),'UV_OFFLINE':'1'})
 env.update(extra or {})
 start=time.monotonic()
 with (ROOT/'logs'/f'{label}.log').open('w') as f:
  try: result=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout); code=result.returncode
  except subprocess.TimeoutExpired: code=124;f.write('\nHARNESS TIMEOUT\n')
 row={'label':label,'command':cmd,'cwd':str(cwd),'exit':code,'seconds':round(time.monotonic()-start,3),'extra_env':extra or {},'log':str(ROOT/'logs'/f'{label}.log')}
 with (ROOT/'gates.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps(row),flush=True)
 return code
if __name__=='__main__':
 n=sys.argv[1]
 w=WORK/('cua-'+n)
 if n in ['4316','3961']:
  ex=w/'libs/cua-driver/examples/jev-use'; donor=Path('/mnt/zer0models/github/cua-lanes')/('c4316' if n=='4316' else 'pr3961')/'libs/cua-driver/examples/jev-use'
  for name in ['package.json','package-lock.json','pyproject.toml','uv.lock']:
   a,b=ex/name,donor/name;print(name,a.exists() and b.exists() and a.read_bytes()==b.read_bytes(),flush=True)
  if (ex/'package-lock.json').read_bytes()!=(donor/'package-lock.json').read_bytes():raise SystemExit('Node dependency lock mismatch')
  (ex/'node_modules').symlink_to(donor/'node_modules',target_is_directory=True)
  py=str(donor/'.venv/bin/python')
  run(n+'-python-version',[py,'--version'],ex)
  if n=='3961':run(n+'-python-openjev',[py,'-m','unittest','discover','-s','python/tests','-p','test_openjev_model.py','-v'],ex)
  else:
   for pattern in ['test_guarded_completion.py','test_verify_setup.py']:
    run(n+'-'+pattern,[py,'-m','unittest','discover','-s','python/tests','-p',pattern,'-v'],ex)
  run(n+'-typescript-tests',['npm','test'],ex,timeout=240)
  run(n+'-typecheck',['npm','run','typecheck'],ex)
 elif n=='5374':
  pk=w/'libs/python/cua-sandbox'
  run(n+'-original15',[sys.executable,'-m','pytest','-p','no:cacheprovider','tests/test_adb_transport.py','-v'],pk,{'PYTHONPATH':str(pk),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
  run(n+'-ruff',['ruff','check','--no-fix','--no-cache','cua_sandbox/transport/adb.py','tests/test_adb_transport.py'],pk)
  run(n+'-ruff-format',['ruff','format','--check','--no-cache','cua_sandbox/transport/adb.py','tests/test_adb_transport.py'],pk)
  run(n+'-release-title',[sys.executable,'.github/scripts/release_attribution.py','validate-title','--title','fix(sandbox): honor shell timeout on Android ADB transport','--require-release'],w)
  run(n+'-release-versions',[sys.executable,'.github/scripts/validate_release_versions.py','--product','sandbox'],w)
  run(n+'-package-build',[sys.executable,'-m','build','--no-isolation','--outdir',str(ROOT/'dist')],pk)
