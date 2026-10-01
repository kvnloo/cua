// Run only through documented cua_repl after observing the application/window.
// Do not substitute these historical IDs for a new fresh inventory.
// This is a reproducible API recipe, not an unattended native authority service.
// 1. Launch org.xfce.mousepad.desktop; use fresh listWindows/getApp binding.
// 2. Fresh AT-SPI tree must report one Match case checkbox in an open Find bar.
// 3. Re-derive its index from every new tree; refuse absent/ambiguous matches.
async function semanticToggle(native) {
  const start=Date.now();
  const before=await native.getAXState({emit:false});
  const lines=before.split('\n').filter(x=>/check box.*Match case/.test(x));
  if(lines.length!==1 || /disabled/.test(lines[0]))throw Error('target unavailable');
  const index=Number(lines[0].trim().match(/^\d+/)[0]);
  const wasChecked=/checked/.test(lines[0]);
  const resolveMs=Date.now()-start;
  const actionStart=Date.now();
  await native.click(index);
  const actionMs=Date.now()-actionStart;
  const after=await native.getAXState({emit:false});
  const result=after.split('\n').filter(x=>/check box.*Match case/.test(x));
  if(result.length!==1 || /checked/.test(result[0])===wasChecked)throw Error('outcome refuted');
  return {whole_task_ms:Date.now()-start,resolve_ms:resolveMs,action_ms:actionMs,before:lines[0],after:result[0],verified:true};
}
// Pointer comparison must use a freshly inspected screenshot and current window bounds.
// The measured run used alternating AB/BA pairs; both routes verified checked state.
// No backend trace, CPU, memory, or Driver-build identity is exposed by this interface.
