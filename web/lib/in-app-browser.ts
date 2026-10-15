/**
 * Browsers embedded in other apps (Instagram, Facebook, TikTok…), where most
 * ads traffic lands. Google refuses OAuth inside them (disallowed_useragent),
 * so the Google button would only lead to an error page there.
 */
const IN_APP = /Instagram|FBAN|FBAV|FB_IAB|FBIOS|FB4A|Messenger|Line\/|TikTok|musical_ly|Snapchat|Twitter|; wv\)/i;

export function isInAppBrowser(userAgent: string | null | undefined): boolean {
  return Boolean(userAgent && IN_APP.test(userAgent));
}
