"""Real isolated Chromium + exact Rust predicate extraction, NOT full Driver E2E."""
import hashlib,html,json,os,re,resource,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).parent
REPO=Path('/mnt/zer0models/github/cua')
FILE='libs/cua-driver/rust/crates/cua-driver-core/src/browser/semantic.rs'
PINS={'base':'53d39e50b274bd982bcfece5915c24084d7e513d','head':'355c6736f9e73a58071c75cbb3ddc7ad7c9725c6','current':None}
# Resolve the recorded verification ref, never a moving remote ref.
PINS['current']=subprocess.check_output(['git','-C',str(REPO),'rev-parse','refs/verification/promotion-first-20261016/main'],text=True).strip()
styles=['opacity: 0 !important','opacity: 0 !IMPORTANT','opacity: 0 !Important','opacity: 0','opacity: 0.5','opacity: 1']
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
with tempfile.TemporaryDirectory(prefix='c3-',dir=os.environ['TMPDIR']) as tmp:
 t=Path(tmp);(t/'home').mkdir();(t/'runtime').mkdir(mode=0o700)
 env=os.environ.copy()
 for k in ['DISPLAY','WAYLAND_DISPLAY','SWAYSOCK','HYPRLAND_INSTANCE_SIGNATURE','DBUS_SESSION_BUS_ADDRESS','DBUS_SYSTEM_BUS_ADDRESS','PYTHONPATH','PYTHONHOME']:env.pop(k,None)
 env.update(HOME=str(t/'home'),XDG_RUNTIME_DIR=str(t/'runtime'),XDG_CONFIG_HOME=str(t/'home/config'),XDG_CACHE_HOME=str(t/'home/cache'))
 rows=''.join('<div id="p%d" style="%s"><button id="b%d">button%d</button></div>'%(i,s,i,i) for i,s in enumerate(styles))
 script="const r="+json.dumps(styles)+".map((s,i)=>{const p=document.getElementById('p'+i),b=document.getElementById('b'+i),r=b.getBoundingClientRect();return {style:p.getAttribute('style'),parentOpacity:getComputedStyle(p).opacity,childOpacity:getComputedStyle(b).opacity,width:r.width,height:r.height}}); document.getElementById('result').textContent=JSON.stringify(r);"
 fixture='<!doctype html><html><body>'+rows+'<pre id="result"></pre><script>'+script+'</script></body></html>'
 (t/'fixture.html').write_text(fixture);(ROOT/'opacity-fixture.html').write_text(fixture)
 cmd=['/usr/bin/chromium','--headless=new','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-background-networking','--user-data-dir='+str(t/'profile'),'--dump-dom',(t/'fixture.html').as_uri()]
 r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=40)
 (ROOT/'logs/chrome-opacity.stderr.log').write_text(r.stderr);(ROOT/'chrome-opacity-dom.html').write_text(r.stdout)
 if r.returncode:raise SystemExit('Chromium failed: '+str(r.returncode))
 result=json.loads(html.unescape(re.search(r'<pre id="result">(.*?)</pre>',r.stdout,re.S).group(1)))
 source={}
 for arm,sha in PINS.items():
  s=subprocess.check_output(['git','-C',str(REPO),'show',sha+':'+FILE],text=True)
  lo=s.index('fn statically_hidden(');hi=s.index('fn layout_hidden(',lo);snippet=s[lo:hi]
  suffix='fn main(){ let mut attrs=HashMap::new(); attrs.insert(String::from("style"), std::env::args().nth(1).unwrap()); println!("{}", statically_hidden(&attrs)); }\n'
  rust='use std::collections::HashMap;\n'+snippet+suffix
  f=t/(arm+'.rs');f.write_text(rust);(ROOT/('opacity-'+arm+'.rs')).write_text(rust)
  build=subprocess.run(['rustc','--edition=2021',str(f),'-o',str(t/arm)],text=True,capture_output=True,timeout=30)
  (ROOT/'logs'/('opacity-'+arm+'-build.log')).write_text(build.stdout+build.stderr)
  if build.returncode:raise SystemExit('Rust build failed')
  vals=[subprocess.check_output([str(t/arm),row['style']],text=True).strip()=='true' for row in result]
  source[arm]={'sha':sha,'path':FILE,'source_sha256':hashlib.sha256(s.encode()).hexdigest(),'extracted_sha256':hashlib.sha256(snippet.encode()).hexdigest(),'hidden':vals}
 for i,row in enumerate(result):
  assert row['width']>0 and row['height']>0
  assert row['childOpacity']=='1'
  assert row['parentOpacity']==('0' if i<4 else '0.5' if i==4 else '1')
 assert source['base']['hidden']==[True,True,True,True,True,False]
 assert source['head']['hidden']==[True,False,False,True,False,False]
 assert source['current']['hidden']==source['head']['hidden']
 report={'scope':'Native Chromium CSS/DOM plus exact extracted Rust predicates. NOT complete Driver semantic_v2/MCP or native desktop acceptance. No production edits.','browser':subprocess.check_output(['/usr/bin/chromium','--version'],env=env,text=True).strip(),'rustc':subprocess.check_output(['rustc','--version'],text=True).strip(),'command':cmd,'browser_rows':result,'source':source,'result':'CONFIRMED parser mismatch on actual Chromium-preserved uppercase/mixed-case priority; full Driver reproduction and owner review still required'}
 (ROOT/'chrome-opacity-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
