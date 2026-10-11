import {readFileSync,writeFileSync} from 'node:fs';
import {planGuardedCompletion,resolveGuardedCompletion} from './cua/libs/cua-driver/examples/jev-use/typescript/guarded_completion.ts';
import {FixtureFormTask,fixtureSources} from './cua/libs/cua-driver/examples/jev-use/typescript/tasks.ts';
const cases=JSON.parse(readFileSync(new URL('./parity-cases.json',import.meta.url),'utf8'));
const snapshot=(value:string,refs:string[])=>({target_id:'target',tab_id:'tab',refs:[{role:'textbox',name:'verification value',ref:'p1:0',value},...refs.map(ref=>({role:'button',name:'Submit',ref}))]});
const rows=cases.map((c:any)=>{let task=new FixtureFormTask('proof');let initial=fixtureSources(snapshot('',['p1:1']));let plan=planGuardedCompletion(task,initial,task.candidates(initial)[0],'session-a');if(!plan)throw Error('no plan');let fresh=fixtureSources(snapshot(c.value,c.refs));let r=resolveGuardedCompletion(plan,task,fresh,task.candidates(fresh),c.session);return {telemetry:r.telemetry,candidate_ref:r.candidate?.arguments.ref??null}});
writeFileSync(new URL('./parity-typescript.json',import.meta.url),JSON.stringify(rows,null,2));
