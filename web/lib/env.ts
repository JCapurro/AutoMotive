/** Public Supabase settings; the same on the server and in the browser. */
export const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
export const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
export const telegramBot = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ?? "";
/** Where users write about their data (F7, punto 7): shown in /privacidad and /terminos. */
export const contactEmail = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "";
