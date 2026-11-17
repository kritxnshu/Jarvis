// Regenerates src/generated.ts from the backend's Pydantic models.
// `--check` regenerates in memory and fails if the committed file is stale.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../..");
const target = resolve(here, "../src/generated.ts");
const check = process.argv.includes("--check");

const work = mkdtempSync(join(tmpdir(), "jarvis-contracts-"));
try {
  const schemaPath = join(work, "schema.json");
  execFileSync("uv", ["run", "--quiet", "python", "scripts/export_schema.py", schemaPath], {
    cwd: repo,
    stdio: ["ignore", "inherit", "inherit"],
  });
  const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
  const body = await compile(schema, "JarvisContracts", {
    bannerComment:
      "/* Generated from the backend's Pydantic models by packages/contracts/scripts/generate.mjs.\n" +
      " * Do not edit by hand: run `pnpm --filter @jarvis/contracts generate`. */",
    additionalProperties: false,
    unreachableDefinitions: true,
    style: { printWidth: 100 },
  });
  if (check) {
    let current = "";
    try {
      current = readFileSync(target, "utf8");
    } catch {
      current = "";
    }
    if (current !== body) {
      console.error("contracts: src/generated.ts is stale; run `pnpm --filter @jarvis/contracts generate`");
      process.exit(1);
    }
    console.log("contracts: up to date");
  } else {
    writeFileSync(target, body);
    console.log(`contracts: wrote ${target}`);
  }
} finally {
  rmSync(work, { recursive: true, force: true });
}
