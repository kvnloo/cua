// Load the exact c78 runner after installing a recipe-local provider counter.
import {register} from 'node:module';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
register('./provider-loader.mjs',import.meta.url);
const secret=JSON.parse(readFileSync(0,'utf8')).token;
const entry=process.env.ECON_EXAMPLES+'/typescript/run.ts';
process.argv=[process.execPath,entry,...process.argv.slice(2),'--token',secret];
console.log(JSON.stringify({event:'bootstrap',guarded_flag:process.argv.includes('--guarded-completion'),source_file_sha256:createHash('sha256').update(readFileSync(entry)).digest('hex')}));
await import(pathToFileURL(entry).href);
