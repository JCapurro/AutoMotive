/**
 * X (Twitter) pixel, for ads attribution. Empty id = no pixel: local and e2e
 * runs stay out of the ads data, as with Meta. Shared by the browser component
 * and the server's Conversion API (lib/x-capi.ts).
 */
export const xPixelId = process.env.NEXT_PUBLIC_X_PIXEL_ID ?? "";

/**
 * The `twclid` of the ad click that brought the visitor (X adds it to the
 * landing URL). Kept 30 days so a later signup or payment can be matched to it.
 */
export const TWCLID_COOKIE = "x_twclid";

/**
 * The X Events Manager ID of each conversion we report (tw-<pixel>-xxxxx).
 * Empty = that conversion isn't sent.
 */
export const X_EVENTS = {
  purchase: "tw-rimgs-rimt6",
  signup: "tw-rimgs-rimt7",
  firstSearch: "tw-rimgs-rimt9",
} as const;

export type XConversion = keyof typeof X_EVENTS;
