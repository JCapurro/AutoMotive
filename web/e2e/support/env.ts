import path from "node:path";

/** Local stack (`npx supabase start`) defaults; override with env vars. */
export const DATABASE_URL = process.env.E2E_DATABASE_URL ?? "postgresql://postgres:postgres@127.0.0.1:54322/postgres";
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://127.0.0.1:54324";
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
export const WORKER_DIR = path.resolve(__dirname, "../../../worker");
export const PYTHON = process.env.WORKER_PYTHON ?? "python";

/** Everything the e2e creates carries this prefix, so global setup can clean it. */
export const E2E_EMAIL_DOMAIN = "e2e.automotive.test";
export const E2E_LISTING_PREFIX = "e2e-";
