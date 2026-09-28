import { execFileSync } from "node:child_process";

import { closeDb, resetE2E, seedMarket } from "./support/db";
import { MAILPIT_URL, PYTHON, SUPABASE_URL, WORKER_DIR } from "./support/env";

/**
 * The e2e runs against the local Supabase stack with its seed, plus:
 *   * Mailpit (magic links) and Realtime (web inbox) running;
 *   * the worker's Python environment (backfill and the simulated alert run
 *     the real worker code, worker/tools/rematch.py and simulate_alert.py).
 */
export default async function globalSetup() {
  for (const [name, url] of [
    ["Supabase Auth", `${SUPABASE_URL}/auth/v1/health`],
    ["Mailpit", `${MAILPIT_URL}/api/v1/messages?limit=1`],
  ]) {
    const ok = await fetch(url, { headers: { apikey: "e2e" } }).then((r) => r.status < 500, () => false);
    if (!ok) throw new Error(`${name} is not reachable at ${url}: run \`npx supabase start\` from the repo root`);
  }
  try {
    execFileSync(PYTHON, ["-c", "import psycopg, pipeline.rematch"], { cwd: WORKER_DIR, stdio: "pipe" });
  } catch {
    throw new Error(`The worker's Python environment is missing (${PYTHON}): pip install -r worker/requirements.txt`);
  }

  await resetE2E();
  await seedMarket();
  await closeDb();
}
