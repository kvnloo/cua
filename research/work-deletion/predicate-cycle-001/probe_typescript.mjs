// Evidence-only harness: import the exact pinned modules, mock external I/O only.
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { randomBytes } from 'node:crypto';
const ex = process.env.AUDIT_TS_EX;
const from = (name) => import(pathToFileURL(`${ex}/typescript/${name}.ts`).href);
const { FixtureFormTask, fixtureSources } = await from('tasks');
const { planGuardedCompletion, resolveGuardedCompletion } = await from('guarded_completion');
const { immutableCandidate } = await from('sources');

function snapshot(c,before,token) {
  const prefix = before ? 'initial' : 'fresh';
  const fs = before ? undefined : c.field_state;
  const value = before || fs === 'empty' ? '' : fs === 'other' ? 'not-the-required-value' : fs === 'unavailable' ? undefined : token;
  const field = {role:'textbox',name:'verification value',ref:before?'p1:0':'p2:0',value};
  let refs = fs === 'missing' ? [] : [field];
  if (!before && c.duplicate_field) {
    const other={...field,ref:'p2:9',value:''};
    refs=c.duplicate_field==='valid-first'?[field,other]:[other,field];
  }
  if(c.extra_field) refs.push({role:'textbox',name:'family name',ref:'p2:8',value:''});
  if(c[prefix+'_submit']!==false) {
    const button={role:'button',name:c[prefix+'_name']??'Submit',ref:c[prefix+'_ref']??(before?'p1:1':'p2:1')};
    refs.push(button);
    if(c[prefix+'_duplicate']) refs.push({...button,ref:c[prefix+'_duplicate']==='same'?button.ref:'p2:7'});
  }
  const out={target_id:before?'target':c.fresh_target??'target',tab_id:'tab',refs};
  if(!before&&c.content_duplicate) out.content_refs=[{role:'button',name:'Submit',ref:'p2:7',states:{disabled:true}}];
  return out;
}
function resolveCase(c) {
  const token=randomBytes(18).toString('hex');
  const task=new FixtureFormTask(token);
  if(c.task_id) Object.defineProperty(task,'id',{value:c.task_id,configurable:true});
  const initial=fixtureSources(snapshot(c,true,token));
  let selected=task.candidates(initial)[0];
  selected=immutableCandidate({...selected,...Object.fromEntries(['id','tool','source'].filter(k=>'first_'+k in c).map(k=>[k,c['first_'+k]]))});
  const plan=planGuardedCompletion(task,initial,selected,c.plan_session??'session-a');
  const row={case:c.id,plan_produced:!!plan,producer_reachable:c.reachability==='producer',reachability:c.reachability};
  if(!plan) return {...row,branch:'no-plan',proof:null,candidate:null};
  if(c.resolve_task_id) Object.defineProperty(task,'id',{value:c.resolve_task_id,configurable:true});
  const fresh=c.page_missing?{visualPath:false}:fixtureSources(snapshot(c,false,token));
  let candidates=c.page_missing?[]:task.candidates(fresh);
  const change=c.candidate_mutation;
  if(change==='none') candidates=[];
  else if(change==='duplicate') candidates=[candidates[0],candidates[0]];
  else if(change) {
    const a={...candidates[0].arguments}, opts={};
    if(change==='wrong-ref') a.ref='p2:foreign';
    if(change==='target') a.target_id='foreign-target';
    if(change==='session') a.session='foreign-session';
    if(['visual','ax'].includes(change)) opts.source=change;
    if(change==='wrong-id') opts.id='another-submit';
    if(change==='capture') opts.captureId='stale-capture';
    candidates=[immutableCandidate({...candidates[0],...opts,arguments:a})];
  }
  const r=resolveGuardedCompletion(plan,task,fresh,candidates,c.resolve_session??'session-a');
  const v=r.candidate;
  Object.assign(row,{branch:r.telemetry.reason??r.telemetry.status,proof:r.telemetry,candidate:v?{id:v.id,tool:v.tool,source:v.source,ref:v.arguments.ref,target_matches_snapshot:v.arguments.target_id===fresh.page.snapshot.target_id,capture_metadata:v.captureId!==undefined}:null});
  if(JSON.stringify(row).includes(token)) throw Error('token leak');
  return row;
}

async function runnerCase(scenario,output) {
  const {Client}=await import(pathToFileURL(`${ex}/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js`).href);
  const {TypeSafeClient}=await import(pathToFileURL(`${ex}/node_modules/@typesafe-ai/sdk/dist/index.mjs`).href);
  const token=process.env.AUDIT_TOKEN, url=process.env.AUDIT_URL;
  let value='',observations=0,label=null,closed=false,providerCalls=0,exception=null;
  const mutations=[],requests=[];
  // This process never launches MCP or a GUI. Every call reaches this owned adapter.
  Client.prototype.connect=async()=>{};
  Client.prototype.listTools=async()=>({tools:scenario==='capture-mismatch'?['click','get_window_state','parse_visual_regions'].map(name=>({name,inputSchema:{properties:{capture_id:{}}}})):[]});
  Client.prototype.close=async()=>{closed=true};
  Client.prototype.callTool=async({name,arguments:args})=>{
    label??=args.session;
    requests.push({tool:name,session_matches:args.session===label});
    let data={};
    if(name==='browser_prepare') data={prepared_pid:42};
    else if(name==='list_windows') data={windows:[{window_id:7,is_on_screen:true,bounds:{width:800,height:600}}]};
    else if(name==='get_browser_state') {
      if(args.snapshot_format!=='semantic_v2') data={target_id:'target',tabs:[{tab_id:'tab',active:true}]};
      else {
        observations++;
        const n=observations;
        data={target_id:'target',tab_id:'tab',refs:[{role:'textbox',name:'verification value',ref:`p${n}:0`,value}]};
        if(scenario==='field-unavailable'&&n===2) delete data.refs[0].value;
        const missing=(scenario==='reobserve'&&n===2)||(scenario==='capture-mismatch'&&n>1);
        if(!missing) data.refs.push({role:'button',name:'Submit',ref:scenario==='ref-reused'?'p1:1':`p${n}:1`});
        if(['duplicate-after','provider-failure'].includes(scenario)&&n===2) data.refs.push({role:'button',name:'Submit',ref:`p${n}:7`});
      }
    } else if(['browser_type','browser_click'].includes(name)) {
      mutations.push({tool:name,ref:args.ref,session_matches:args.session===label,current_ref:[`p${observations}:0`,`p${observations}:1`].includes(args.ref)});
      const refused=(scenario==='first-refused'&&name==='browser_type')||(['second-refused','session-refusal'].includes(scenario)&&name==='browser_click');
      if(refused) return {content:[],structuredContent:{status:'refused',refusal:{code:scenario==='session-refusal'?'session_mismatch':'stale_ref'}}};
      if(name==='browser_type') value=args.text;
      const response=await fetch(url+(name==='browser_type'?'type':'submit'),{method:'POST',body:value});
      if(!response.ok) throw Error('oracle transport failed');
      if((scenario==='first-response-lost'&&name==='browser_type')||(scenario==='second-response-lost'&&name==='browser_click')) throw Error(token);
    } else if(name==='get_window_state') data={capture_id:'fresh-capture'};
    else if(name==='parse_visual_regions') {
      data=JSON.parse(readFileSync(`${ex}/fixtures/jev-visual-replay-v1.json`,'utf8')).visual_regions;
      data.capture.capture_id='wrong-capture';data.capture.source={kind:'window',pid:42,window_id:7};
    } else if(name!=='browser_navigate') throw Error('unexpected transport request');
    return {content:[],structuredContent:data};
  };
  // Count actual mock-provider boundary via task input generation, not timing.
  // Live SDK is replaced only in the provider-failure cell; no network call.
  if(scenario==='provider-failure') {
    process.env.TYPESAFE_API_KEY='hermetic-not-a-real-key';
    TypeSafeClient.prototype.systemOne=async()=>{
      providerCalls++;
      if(providerCalls>1) throw Error(token);
      return {answers:{driver_action:{type:'choice',choice:'type-verification-value',confidence:1,probabilities:{'type-verification-value':1,reobserve:0,abstain:0}}}};
    };
  }
  const oldError=console.error;
  console.error=()=>{exception='Error';}; // Preserve status only, never an exception's field content.
  process.argv=[process.execPath,`${ex}/typescript/run.ts`,'--provider',scenario==='provider-failure'?'live':'mock','--fixture-url',url,'--token',token,'--max-steps','3','--visual-observation',scenario==='capture-mismatch'?'auto':'off','--log',`${output}/events.jsonl`,...(process.env.AUDIT_GUARDED==='1'?['--guarded-completion']:[])];
  process.on('beforeExit',()=>{
    const raw=readFileSync(`${output}/events.jsonl`,'utf8');
    if(raw.includes(token)) {process.exitCode=9;throw Error('token leak');}
    const events=raw.trim().split('\n').filter(Boolean).map(JSON.parse);
    const outcome=events.at(-1)?.event==='outcome'?events.at(-1).outcome:null;
    const mockCalls=events.filter(e=>e.decision_route==='provider').length;
    writeFileSync(`${output}/transport.json`,JSON.stringify({outcome,exception,closed,provider_calls:scenario==='provider-failure'?providerCalls:mockCalls,provider_count_basis:scenario==='provider-failure'?'SDK-call':'provider-route-events',requests,mutations,token_absent:true},null,2)+'\n');
    console.error=oldError;
  });
  await from('run');
}
if(process.argv[2]==='resolver') console.log(JSON.stringify(JSON.parse(readFileSync(process.argv[3],'utf8')).map(resolveCase)));
else await runnerCase(process.argv[3],process.argv[4]);
