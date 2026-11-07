/**
 * GEO · IndexNow (https://www.indexnow.org): tells Bing (and through it the
 * answer engines that search with Bing, like ChatGPT's) and Yandex that a
 * page changed, instead of waiting for the next crawl. The key is public by
 * design: anyone can read it at /indexnow.txt; it only proves the pings come
 * from whoever controls the site.
 */
import { siteUrl } from "@/lib/env";

export const INDEXNOW_KEY = "df05c95b9c5d997774f24553a8574c29";
export const INDEXNOW_KEY_PATH = "/indexnow.txt";
const ENDPOINT = "https://api.indexnow.org/indexnow";

/** Only the production site pings: not local, not a Vercel preview, not e2e. */
export function indexNowEnabled(vercelEnv: string | undefined = process.env.VERCEL_ENV, site = siteUrl): boolean {
  return vercelEnv === "production" && /^https:\/\//.test(site) && !/localhost|127\.0\.0\.1/.test(site);
}

/** The request body for some site paths ("/guias/toyota/corolla"), or null without any. */
export function indexNowBody(paths: string[], site = siteUrl): { host: string; key: string; keyLocation: string; urlList: string[] } | null {
  const urlList = [...new Set(paths)].map((p) => `${site}${p}`);
  if (!urlList.length) return null;
  return { host: new URL(site).host, key: INDEXNOW_KEY, keyLocation: `${site}${INDEXNOW_KEY_PATH}`, urlList };
}

/** Pings IndexNow; never throws (a failed ping only means the engines find out on their next crawl). */
export async function pingIndexNow(paths: string[]): Promise<void> {
  if (!indexNowEnabled()) return;
  const body = indexNowBody(paths);
  if (!body) return;
  try {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok && response.status !== 202) console.warn(`indexnow: ${response.status}`);
  } catch (error) {
    console.warn(`indexnow: ${error instanceof Error ? error.message : String(error)}`);
  }
}
