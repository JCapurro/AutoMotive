/** Fixed owner requested for the private health dashboard; never taken from a URL. */
export const HEALTH_OWNER_EMAIL = "jcapurro97@gmail.com";

export function isHealthOwner(user: { email?: string | null; email_confirmed_at?: string | null } | null): boolean {
  return Boolean(user?.email_confirmed_at && user.email?.trim().toLowerCase() === HEALTH_OWNER_EMAIL);
}
