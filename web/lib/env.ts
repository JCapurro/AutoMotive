/** Public Supabase settings; the same on the server and in the browser. */
export const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
export const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
export const telegramBot = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ?? "";
/** Where users write about their data (F7, punto 7): shown in /privacidad and /terminos. */
export const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "";
/** Public URL of the app (F7): canonical links, sitemap and Open Graph. */
export const siteUrl = (process.env.SITE_URL ?? "http://127.0.0.1:3000").replace(/\/$/, "");
/**
 * Local stack only (Supabase on 127.0.0.1): the magic links land in Mailpit,
 * not in a real inbox, so the login page links to it. Empty in the pilot.
 */
export const localMailbox = /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?$/.test(supabaseUrl ?? "")
  ? (process.env.NEXT_PUBLIC_LOCAL_MAILBOX_URL ?? "http://127.0.0.1:54324")
  : "";
