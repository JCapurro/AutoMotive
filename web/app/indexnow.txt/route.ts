import { INDEXNOW_KEY } from "@/lib/indexnow";

export const dynamic = "force-static";

/** IndexNow's key file (the keyLocation of every ping): the key, nothing else. */
export function GET(): Response {
  return new Response(INDEXNOW_KEY, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
