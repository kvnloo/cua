// Token counts with an actual tokenizer: gpt-tokenizer (MIT), pure-JS BPE with bundled ranks (no network).
// usage: node count_tokens.mjs <dir-containing-node_modules/gpt-tokenizer>   < {"name": "text", ...}
// prints {"tokenizer": {...}, "counts": {"o200k_base": {name: n}, "cl100k_base": {name: n}}}
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.argv[2] ?? '.');
const require = createRequire(path.join(root, 'noop.js'));
const pkg = JSON.parse(readFileSync(require.resolve('gpt-tokenizer/package.json'), 'utf8'));
const texts = JSON.parse(readFileSync(0, 'utf8'));
const counts = {};
for (const encoding of ['o200k_base', 'cl100k_base']) {
  const { encode } = require(`gpt-tokenizer/encoding/${encoding}`);
  counts[encoding] = Object.fromEntries(Object.entries(texts).map(([name, text]) => [name, encode(text).length]));
}
console.log(JSON.stringify({ tokenizer: { package: pkg.name, version: pkg.version, license: pkg.license }, counts }));
