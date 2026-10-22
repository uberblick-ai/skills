// Draws each ablauf flow as an SVG next to it (issue.flow -> issue.svg) and fails on any diagnostic.
// Usage: node render.mjs ABLAUF_PREFIX FLOW...
// ABLAUF_PREFIX is the directory `npm install --prefix` put @uberblick/ablauf in.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { basename, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [prefix, ...inputs] = process.argv.slice(2);
if (!prefix || !inputs.length || inputs.some((f) => !f.endsWith(".flow"))) {
  console.error("Usage: node render.mjs ABLAUF_PREFIX FLOW...  (each FLOW ends in .flow)");
  process.exit(2);
}
const entry = resolve(prefix, "node_modules/@uberblick/ablauf/dist/index.js");
if (!existsSync(entry)) {
  console.error(`No ablauf in ${prefix}: run npm install --prefix ${prefix} @uberblick/ablauf@0.2.0`);
  process.exit(2);
}
const { render } = await import(pathToFileURL(entry).href);
let failed = false;
for (const input of inputs) {
  const output = input.replace(/\.flow$/, ".svg");
  // One page holds several drawings, so each needs its own marker ids.
  const { svg, diagnostics } = render(readFileSync(input, "utf8"), { idPrefix: basename(input, ".flow") });
  for (const { line, severity, message } of diagnostics) {
    console.error(`${input}:${line} ${severity}: ${message}`);
  }
  // Keep the SVG for inspection, but fail on any source problem.
  writeFileSync(output, svg);
  if (diagnostics.length) failed = true;
  else console.log(`${output} clean`);
}
process.exitCode = failed ? 1 : 0;
