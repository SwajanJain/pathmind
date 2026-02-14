import { execSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, "../../..");
const outputPath = resolve(__dirname, "../src/index.ts");
const checkMode = process.argv.includes("--check");
const providedOpenApiUrl = process.env.PATHMIND_OPENAPI_URL;
const providedOpenApiFile = process.env.PATHMIND_OPENAPI_FILE;

mkdirSync(dirname(outputPath), { recursive: true });
const tempDir = mkdtempSync(resolve(tmpdir(), "pathmind-openapi-"));
const generatedOpenApiFile = resolve(tempDir, "openapi.json");

let openApiSource = providedOpenApiUrl;
if (!openApiSource) {
  if (providedOpenApiFile) {
    openApiSource = providedOpenApiFile;
  } else {
    const apiDir = resolve(rootDir, "apps/api");
    const venvPython = resolve(apiDir, ".venv/bin/python");
    const pythonBin = existsSync(venvPython) ? venvPython : "python3";
    execSync(
      `cd ${apiDir} && PYTHONPATH=src ${pythonBin} -c "import json; from pathmind_api.main import app; print(json.dumps(app.openapi()))" > ${generatedOpenApiFile}`,
      { cwd: rootDir, stdio: "inherit" },
    );
    openApiSource = generatedOpenApiFile;
  }
}

const generatedOutputPath = checkMode ? resolve(tempDir, "contracts-index.ts") : outputPath;
execSync(`npx openapi-typescript ${openApiSource} --output ${generatedOutputPath}`, { cwd: rootDir, stdio: "inherit" });

const content = readFileSync(generatedOutputPath, "utf-8");
const banner = "/* AUTO-GENERATED FILE. DO NOT EDIT MANUALLY. */\n";
const nextContent = content.startsWith("/* AUTO-GENERATED") ? content : `${banner}${content}`;

if (checkMode) {
  const currentContent = readFileSync(outputPath, "utf-8");
  if (currentContent !== nextContent) {
    rmSync(tempDir, { recursive: true, force: true });
    throw new Error("Contract drift detected. Run: pnpm contracts:generate");
  }
} else {
  writeFileSync(outputPath, nextContent);
}

rmSync(tempDir, { recursive: true, force: true });
