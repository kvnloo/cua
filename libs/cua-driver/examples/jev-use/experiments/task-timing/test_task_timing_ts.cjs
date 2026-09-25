/** Controlled dependencies, actual pinned runner control flow; no native qualification. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const { performance } = require('node:perf_hooks');
const { pathToFileURL } = require('node:url');
const crypto = require('node:crypto');

function compile(source) {
  const parsed = ts.createSourceFile('runner.ts', source, ts.ScriptTarget.Latest, true);
  const statements = parsed.statements.filter((n) => !(ts.isIfStatement(n) && n.getText(parsed).includes('import.meta')));
  const text = ts.createPrinter().printFile(ts.factory.updateSourceFile(parsed, statements));
  return ts.transpileModule(text, { compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
    reportDiagnostics:true }).outputText;
}
function loadTimer() {
  const output = {exports:{}};
  vm.runInNewContext(compile(fs.readFileSync(path.join(__dirname,'task_timing.ts'),'utf8')),
    {require, exports:output.exports, module:output, performance, Error, RangeError}, {filename:'task_timing.js'});
  return output.exports.TaskTiming;
}
const Timer = loadTimer();

function prepare(filename, scenario, options={}) {
  const evidence = {calls:[],events:[],state:{typed:false,submitted:null},oracle_reads:0,sleeps:[],cleanup:[]};
  let now=0;
  const clock = options.realClock ? () => performance.now() : () => (now += 0.01);
  class Client {
    async connect() { evidence.calls.push(['connect',{}]); }
    async listTools() {
      evidence.calls.push(['list_tools',{}]);
      return {tools: scenario.startsWith('visual') ? [
        {name:'click',inputSchema:{properties:{capture_id:{}}}}, {name:'get_window_state'}, {name:'parse_visual_regions'}
      ] : []};
    }
    async close() {
      evidence.cleanup.push('client');
      if (scenario==='cleanup_delay') now += 25;
      if (scenario==='cleanup_error') throw new Error('test cleanup failure');
    }
    async callTool({name,arguments:args}) {
      const {session,...argumentsWithoutSession}=args;
      evidence.calls.push([name,argumentsWithoutSession]);
      let data={};
      if (name==='browser_prepare') data={prepared_pid:1};
      else if (name==='list_windows') data={windows:[{window_id:1,is_on_screen:true,bounds:{width:100,height:100}}]};
      else if (name==='get_browser_state') {
        if (args.snapshot_format && scenario==='observe_error') throw new Error('test observation');
        data={target_id:'owned-fixture',tabs:[{tab_id:'one'}],typed:evidence.state.typed};
      } else if (name==='get_window_state') {
        if (scenario==='visual_error') throw new Error('test visual unavailable');
        data={capture_id:'owned-capture'};
      } else if (name==='parse_visual_regions') data={};
      else if (name!=='browser_navigate') {
        if (scenario==='action_error') throw new Error('test action');
        if (scenario==='abort_action') { const e=new Error('test cancelled');e.name='AbortError';throw e; }
        if (name==='type_text') evidence.state.typed=true;
        if (name==='submit') evidence.state.submitted=scenario==='refuted'?'different':'fixed';
      }
      return {isError:false,structuredContent:data};
    }
  }
  const candidates=()=>{
    if (scenario==='empty_candidates') return [];
    const id=['abstain','reobserve'].includes(scenario)?scenario:
      evidence.state.typed?'submit-form':'type-verification-value';
    return [{id,tool:id==='submit-form'?'submit':'type_text',arguments:{value:'fixed'}}];
  };
  const choose=()=>{
    if (scenario==='provider_error' || (scenario==='provider_error_second' && evidence.state.typed)) throw new Error('test provider');
    return {choice:scenario==='provider_none'?null:candidates()[0].id,confidence:1,probabilities:{}};
  };
  function log(text) {
    const row=JSON.parse(text);
    if (options.failSink && ['span','task_root'].includes(row.event)) throw new Error('test timing sink');
    evidence.events.push(row);
  }
  const modules={
    'node:fs/promises':{appendFile:async()=>{},writeFile:async()=>{}},
    'node:process':{default:{env:{},argv:[]}},
    'node:crypto':{randomUUID:()=> '11111111-1111-4111-8111-111111111111'},
    'node:url':{pathToFileURL},
    '@modelcontextprotocol/sdk/client/index.js':{Client},
    '@modelcontextprotocol/sdk/client/stdio.js':{StdioClientTransport:class {}},
    './core.js':{buildCandidates:candidates,
      classify:(submitted,token)=>submitted===token?'verified':submitted!==null?'refuted':'unknown',
      parseVisualRegions:()=>({captureId:'owned-capture'}),validateChoice:()=>candidates()[0]},
    './jev_adapter.js':{chooseMockAdapter:choose,chooseLive:async()=>choose()},
    './task_timing.js':{TaskTiming:class extends Timer {
      constructor(){super(clock,options.maxSpans??512);}
    }},
  };
  const output={exports:{}};
  const source=fs.readFileSync(path.join(__dirname,filename),'utf8')+'\nexport { run };\n';
  const sandbox={exports:output.exports,module:output,require:(name)=>{
    if (!(name in modules)) throw new Error(`Unexpected import ${name}`); return modules[name];
  },console:{log},URL,Error,RangeError,performance:{now:clock},
    setTimeout:(fn,delay)=>{evidence.sleeps.push(delay);now+=delay;fn();},
    fetch:async(url)=>{
      if (url.pathname==='/reset') {
        if(scenario==='reset_error') throw new Error('test reset');
        return {status:204};
      }
      assert.equal(url.pathname,'/state'); evidence.oracle_reads++;
      if(scenario==='verify_error' && evidence.state.typed) throw new Error('test verifier');
      const value=scenario==='delayed_verify' && evidence.oracle_reads<5?null:evidence.state.submitted;
      return {ok:true,json:async()=>({submitted:value})};
    },
  };
  vm.runInNewContext(compile(source),sandbox,{filename});
  const args={token:'fixed',fixtureUrl:'http://127.0.0.1:8765/',maxSteps:3,
    dryRun:scenario==='dry_run',provider:scenario==='live_provider'?'live':'mock'};
  return {evidence,run:async()=>{
    try {evidence.outcome=await output.exports.run(args); evidence.error=null;}
    catch(error){evidence.outcome=null;evidence.error=error.name;}
    return evidence;
  }};
}
function nonTiming(events){return events.filter(e=>!['span','task_root'].includes(e.event))
  .map(e=>Object.fromEntries(Object.entries(e).filter(([k])=>!k.endsWith('_ms'))));}
const scenarios=['verified','refuted','empty_candidates','provider_none','abstain','reobserve','dry_run',
  'action_error','observe_error','provider_error','verify_error','reset_error','abort_action',
  'cleanup_error','delayed_verify','cleanup_delay','provider_error_second','visual','visual_error','live_provider'];
async function main(){
  let comparisons=0;
  const summaries=[];
  for(const scenario of scenarios){
    const before=await prepare('baseline-ts.ts',scenario).run();
    const after=await prepare('run-ts.ts',scenario).run();
    for(const key of ['calls','state','oracle_reads','sleeps','cleanup','outcome','error'])
      assert.deepEqual(JSON.parse(JSON.stringify(after[key])),JSON.parse(JSON.stringify(before[key])),`${scenario}:${key}`);
    assert.deepEqual(nonTiming(after.events),nonTiming(before.events),scenario);
    const expected = ['verified','delayed_verify','cleanup_delay','visual','visual_error','live_provider'].includes(scenario)
      ? 'verified' : scenario==='refuted' ? 'refuted'
      : ['empty_candidates','provider_none','abstain'].includes(scenario) ? 'abstained'
      : ['action_error','abort_action','reobserve','dry_run'].includes(scenario) ? 'unknown' : null;
    assert.equal(after.outcome,expected,`intended branch reached:${scenario}`);
    const roots=after.events.filter(e=>e.event==='task_root'); assert.equal(roots.length,1,scenario);
    const root=roots[0];
    assert.equal(root.error_type,after.error,scenario);
    assert.equal(root.outcome,after.error?'unknown':after.outcome,scenario);
    const spans=after.events.filter(e=>e.event==='span');
    assert.equal(spans.filter(e=>e.phase==='verify').length,after.oracle_reads,scenario);
    for(const span of spans){
      assert.equal(span.task_id,root.task_id);assert.equal(span.clock_id,root.clock_id);
      assert.ok(span.start_ms>=0 && span.end_ms>=span.start_ms && span.end_ms<=root.end_ms,scenario);
    }
    const terminal=after.state.submitted!==null && !['verify_error'].includes(scenario);
    assert.equal(root.terminal_observation!==null,terminal,scenario);
    if(terminal){
      assert.equal(root.terminal_observation.verdict,scenario==='refuted'?'refuted':'verified',scenario);
      assert.ok(root.terminal_observation.at_ms<=root.end_ms,scenario);
    }
    if(scenario==='delayed_verify') assert.ok(spans.some(e=>e.phase==='wait'));
    if(scenario==='cleanup_error'){assert.equal(root.outcome,'unknown');assert.equal(root.terminal_observation.verdict,'verified');}
    if(scenario==='cleanup_delay') assert.ok(root.post_terminal_observation_ms>=25);
    summaries.push({scenario,outcome:after.outcome,error:after.error,root});comparisons++;
  }
  for(const scenario of ['verified','provider_error','abort_action','cleanup_error']){
    const before=await prepare('baseline-ts.ts',scenario).run();
    const after=await prepare('run-ts.ts',scenario,{failSink:true}).run();
    for(const key of ['calls','cleanup','outcome','error'])assert.deepEqual(JSON.parse(JSON.stringify(after[key])),JSON.parse(JSON.stringify(before[key])),`sink:${scenario}`);
  }
  const dropped=await prepare('run-ts.ts','verified',{maxSpans:1}).run();
  assert.ok(dropped.events.find(e=>e.event==='task_root').dropped_spans>0);
  const timer=new Timer(); const secret=new Error('private fixture payload');
  assert.throws(()=>timer.measureSync('verify',()=>{throw secret;}),e=>e===secret);
  assert.ok(!JSON.stringify(timer.finish('unknown')).includes('private fixture payload'));
  assert.throws(()=>timer.finish('unknown'));
  const ticks=[0,1,5,7,11];
  const golden=new Timer(()=>ticks.shift());golden.measureSync('verify',()=>{});golden.classified('verified');
  const goldenRows=golden.finish('unknown',false,'CleanupError');
  if(process.argv.includes('--golden')) console.log(JSON.stringify(goldenRows));
  else console.log(JSON.stringify({suite:'controlled TypeScript runner',comparisons,sink_cases:4,
    recorder_checks:['explicit overflow','original exception identity','no exception payload','single finish'],
    native:false,results:summaries},null,2));
}
module.exports={prepare,scenarios,Timer};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
