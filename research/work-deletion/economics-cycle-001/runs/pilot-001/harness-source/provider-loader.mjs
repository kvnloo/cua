// Recipe-local entry counter around the ORIGINAL deterministic chooser.
// Only the adapter is instrumented in memory. run.ts is byte-for-byte original.
import {createHash} from 'node:crypto';
import {appendFileSync} from 'node:fs';
export async function load(url, context, nextLoad) {
  const result = await nextLoad(url, context);
  if (!url.endsWith('/typescript/jev_adapter.ts')) return result;
  let source = result.source.toString();
  const pattern=/\bfunction chooseMockForTask\(/g;
  if ((source.match(pattern)||[]).length!==1) throw new Error('provider hook shape mismatch');
  const originalHash=createHash('sha256').update(source).digest('hex');
  source=source.replace(pattern,'function econOriginalMock(');
  source += `\nimport {appendFileSync as econAppend} from 'node:fs';
let econCount=0;
function chooseMockForTask(...args) {
  const index=++econCount;
  const emit=(event)=>econAppend(process.env.ECON_PROVIDER_JOURNAL,JSON.stringify({event,index,ns:Number(process.hrtime.bigint())})+'\\n');
  emit('provider_enter');
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,Number(process.env.ECON_PROVIDER_MS));
    return econOriginalMock(...args);
  } finally { emit('provider_exit'); }
}\n`;
  appendFileSync(process.env.ECON_PROVIDER_JOURNAL, JSON.stringify({event:'instrumentation',original_transpiled_sha256:originalHash,instrumented_transpiled_sha256:createHash('sha256').update(source).digest('hex')})+'\n');
  return {...result, source};
}
