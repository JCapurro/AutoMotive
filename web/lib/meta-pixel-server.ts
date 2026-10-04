import "server-only";

import { cookies } from "next/headers";

import { metaPixelId, PIXEL_QUEUE_COOKIE, type PixelEvent, type PixelParams, type QueuedPixel } from "@/lib/meta-pixel";

/**
 * Conversions decided on the server (signup, first search) reach the pixel
 * through a short-lived cookie that <MetaPixel> reads and clears. Only from a
 * Server Action or Route Handler; a Server Component can't set cookies.
 */
export async function queuePixel(event: PixelEvent, params?: PixelParams, id?: string): Promise<void> {
  if (!metaPixelId) return;
  try {
    const store = await cookies();
    let queue: QueuedPixel[] = [];
    try {
      queue = JSON.parse(store.get(PIXEL_QUEUE_COOKIE)?.value ?? "[]");
    } catch {}
    queue.push({ event, params, id });
    store.set(PIXEL_QUEUE_COOKIE, JSON.stringify(queue.slice(-5)), { path: "/", maxAge: 600, sameSite: "lax" });
  } catch {
    // Ads attribution never breaks the action.
  }
}
