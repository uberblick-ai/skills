// Checks every ablauf and wireframe fence in the documents and draws each ablauf as an SVG for the review page.
// Usage: node viz.mjs PREFIX DOC.md...
// PREFIX is the directory `npm install --prefix` put @uberblick/ablauf and @uberblick/wireframe in.
// SVGs land in viz/ next to the documents as <doc>-<n>.svg, and <doc>-<n>.flat.svg with the light colours written
// in for image viewers. Exits 1 on any diagnostic, naming the file and line.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [prefix, ...docs] = process.argv.slice(2);
if (!prefix || !docs.length || docs.some((f) => !f.endsWith(".md"))) {
  console.error("Usage: node viz.mjs PREFIX DOC.md...  (each DOC ends in .md)");
  process.exit(2);
}
const mod = (name) => resolve(prefix, `node_modules/@uberblick/${name}/dist/index.js`);
for (const name of ["ablauf", "wireframe"]) {
  if (!existsSync(mod(name))) {
    console.error(`No ${name} in ${prefix}: run npm install --prefix ${prefix} @uberblick/ablauf@0.2.0 @uberblick/wireframe@0.3.0`);
    process.exit(2);
  }
}
const { render } = await import(pathToFileURL(mod("ablauf")).href);
const { parseWireframe } = await import(pathToFileURL(mod("wireframe")).href);

let failed = false;
// Image viewers and rasterizers ignore CSS custom properties: resolve the light colours into the SVG itself.
function flat(svg) {
  const colours = {};
  for (const [, name, value] of svg.matchAll(/--([\w-]+):var\(--ab-[\w-]+,(#[0-9a-fA-F]{3,8})\)/g)) {
    colours[name] ??= value;
  }
  return svg.replace("<svg ", '<svg style="background:#ffffff" ').replace(/var\(--([\w-]+)(?:,([^()]*))?\)/g, (m, name, fallback) => colours[name] ?? fallback ?? m);
}

let drawn = 0;
let checked = 0;
for (const doc of docs) {
  const lines = readFileSync(doc, "utf8").split("\n");
  const slug = basename(doc, ".md");
  const out = join(dirname(doc), "viz");
  let n = 0;
  for (let i = 0; i < lines.length; i++) {
    const fence = /^(```+|~~~+)\s*(ablauf|wireframe)\s*$/.exec(lines[i]);
    if (!fence) continue;
    let j = i + 1;
    while (j < lines.length && !lines[j].startsWith(fence[1])) j++;
    const source = lines.slice(i + 1, j).join("\n");
    const at = (line) => `${doc}:${i + 1 + line}`;
    if (fence[2] === "ablauf") {
      n++;
      const { svg, diagnostics } = render(source, { idPrefix: `${slug}-${n}` });
      mkdirSync(out, { recursive: true });
      writeFileSync(join(out, `${slug}-${n}.svg`), svg);
      writeFileSync(join(out, `${slug}-${n}.flat.svg`), flat(render(source, { idPrefix: `${slug}-${n}`, scheme: "light" }).svg));
      for (const d of diagnostics) console.error(`${at(d.line)} ablauf ${d.severity}: ${d.message}`);
      if (diagnostics.length) failed = true;
      else drawn++;
    } else {
      const { diagnostics } = parseWireframe(source);
      for (const d of diagnostics) console.error(`${at(d.line)} wireframe ${d.severity}: ${d.message}`);
      if (diagnostics.length) failed = true;
      else checked++;
    }
    i = j;
  }
}
console.log(`${drawn} ablauf drawn, ${checked} wireframes clean${failed ? "; fix the diagnostics above" : ""}`);
process.exitCode = failed ? 1 : 0;
