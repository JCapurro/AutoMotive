/** Public Supabase settings; the same on the server and in the browser. */
export const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
export const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
export const telegramBot = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME ?? "";
