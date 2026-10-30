import type { Database } from "@/types/database";

export type MatchCard = Database["public"]["Views"]["match_cards"]["Row"];
export type Listing = Database["public"]["Tables"]["listings"]["Row"];
export type SearchProfile = Database["public"]["Tables"]["search_profiles"]["Row"];
export type Notification = Database["public"]["Tables"]["notifications"]["Row"];

/** One entry of matches.match_reasons (worker/intelligence/matching.py). */
export type Reason = { result: "ok" | "fail" | "unknown"; detail: string; kind?: "hard" | "soft" };

/** One component of matches.score_breakdown (worker/intelligence/scoring.py). */
export type Component = { c: number; w: number; contribution: number; explanation: string };

/** matches.price_ref (worker/intelligence/comparables.py). */
export type PriceRef = {
  n: number;
  level_used: string;
  median: number | null;
  p25: number | null;
  p75: number | null;
  median_km: number | null;
  diff_pct: number | null;
  /**
   * F-02 paso 3: the same pool and level split by seller (dealer = dealer or
   * «posible agencia»; private = private and not inferred). Missing on a
   * price_ref stored before it. Data for PRO-02; nothing shows them yet.
   */
  dealer_median?: number | null;
  dealer_n?: number;
  private_median?: number | null;
  private_n?: number;
};

export type RedFlag = { id: string; text: string; severity: "info" | "warning" };

/** search_profiles.filters (sección 4.3). */
export type Filters = {
  make?: string;
  model?: string;
  trims?: string[];
  trim_strict?: boolean;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  currency?: "USD" | "ARS";
  km_min?: number;
  km_max?: number;
  transmission?: "manual" | "automatic";
  fuel?: string;
  /** Body type codes (docs/CARROCERIA.md); omitted when empty. Without make and model: a model-less search. */
  body_types?: string[];
  sources?: string[];
  location_label?: string;
  /** Places added to the search's own (origin_*, radius_km): a listing in any of them qualifies. */
  extra_locations?: SearchPlace[];
};

/** A place a search looks around: the center and how far, in km. */
export type SearchPlace = { label: string; lat: number; lon: number; radius_km: number };

/** search_profiles.preferences (sección 4.3): soft, they feed the score. */
export type Preferences = {
  km_target?: number;
  price_target?: number;
  price_target_currency?: "USD" | "ARS";
  seller_type?: "private" | "dealer";
  preferred_trims?: string[];
  colors?: string[];
  max_distance_km?: number;
};
