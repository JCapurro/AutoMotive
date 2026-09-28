import { execFileSync } from "node:child_process";

import { BASE_URL, DATABASE_URL, PYTHON, WORKER_DIR } from "./env";

/**
 * Runs one of the worker's tools (worker/tools/*.py) against the local
 * database: the e2e uses the real matching, scoring and notification engine.
 */
export function worker(tool: string, ...args: string[]): string {
  return execFileSync(PYTHON, ["-m", `tools.${tool}`, ...args], {
    cwd: WORKER_DIR,
    env: {
      ...process.env,
      DATABASE_URL,
      WEB_BASE_URL: BASE_URL,
      PYTHONIOENCODING: "utf-8",
      GEOCODING_ENABLED: "0",
    },
    encoding: "utf-8",
    timeout: 120_000,
  });
}
