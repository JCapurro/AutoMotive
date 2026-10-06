import { loadEnvConfig } from "@next/env";
import { defineConfig, devices } from "@playwright/test";

loadEnvConfig(process.cwd(), true);
process.env.E2E_BASE_URL = "http://127.0.0.1:3201";
if (!["localhost", "127.0.0.1", "::1"].includes(new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321").hostname)) {
  throw new Error("Las pruebas de autenticación requieren Supabase local.");
}

/** Runs Auth in isolation, without resetting shared market fixtures or reusing port 3000. */
export default defineConfig({
  testDir: "./e2e", testMatch: "confirmation-preview.spec.ts", workers: 1, timeout: 120_000,
  expect: { timeout: 20_000 },
  use: { baseURL: process.env.E2E_BASE_URL, locale: "es-AR", trace: "retain-on-failure" },
  projects: [{ name: "desktop", use: devices["Desktop Chrome"] }, { name: "mobile", use: devices["Pixel 7"] }],
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3201",
    url: `${process.env.E2E_BASE_URL}/login`, reuseExistingServer: false, timeout: 120_000,
    env: { SITE_URL: process.env.E2E_BASE_URL },
  },
});
