// Draws an ablauf flow as SVG and fails on any diagnostic.
// Usage: node render.mjs ABLAUF_PREFIX FLOW SVG
// ABLAUF_PREFIX is the directory `npm install --prefix` put @uberblick/ablauf in.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [prefix, input, output] = process.argv.slice(2);
if (!prefix || !input || !output) {
  console.error("Usage: node render.mjs ABLAUF_PREFIX FLOW SVG");
  process.exit(2);
}
const entry = resolve(prefix, "node_modules/@uberblick/ablauf/dist/index.js");
if (!existsSync(entry)) {
  console.error(`No ablauf in ${prefix}: run npm install --prefix ${prefix} @uberblick/ablauf@0.2.0`);
  process.exit(2);
}
const { render } = await import(pathToFileURL(entry).href);
const { svg, diagnostics } = render(readFileSync(input, "utf8"), { idPrefix: "flow" });
for (const { line, severity, message } of diagnostics) {
  console.error(`${input}:${line} ${severity}: ${message}`);
}
// Keep the SVG for inspection, but fail on any source problem.
writeFileSync(output, svg);
if (diagnostics.length) process.exit(1);
console.log(`${output} clean`);
