/**
 * Admin «Usuarios» dashboard: where users come from (lib/acquisition.ts, kept
 * in signup_completed) and what they did after (events, alerts, payments).
 * The builder is pure; loadUsersDashboard reads every row with the service
 * role, page by page (the REST API stops at 1000 rows).
 */
import { type Channel, channelOf, landingKind, type Origin, parseOrigin } from "@/lib/acquisition";

/** Events the system writes on its own: they never count as the user doing something. */
export const SYSTEM_EVENTS = new Set([
  "alert_sent",
  "lifecycle_email_sent",
  "founder_email_sent",
  "search_paused_by_plan",
  "trial_ended",
  "free_trial_started",
  "assisted_review_shown",
  "assisted_fallback_shown",
]);

/** Signs that a user looked at a car we found for them. */
const ENGAGED = new Set(["alert_clicked", "listing_detail_viewed", "listing_outbound_clicked", "listing_saved", "listing_discarded"]);
const SEARCH_EVENTS = new Set(["search_created", "search_profile_created"]);

export type UserRow = {
  id: string;
  email: string | null;
  plan: string | null;
  plan_expires_at: string | null;
  role: string | null;
  created_at: string;
  telegram_linked: boolean | null;
  email_only: boolean | null;
  searches: number | null;
  enabled_searches: number | null;
  waitlist_plan: string | null;
};
export type EventRow = { user_id: string; name: string; props: unknown; created_at: string };
export type NotificationRow = { user_id: string; sent_at: string | null; opened_at: string | null; clicked_at: string | null };
export type PaymentRow = { user_id: string; amount: number | string; paid_at: string | null; refunded_at: string | null };

export type UserStats = UserRow & {
  channel: Channel;
  origin: Origin | null;
  method: string | null;
  firstSearchAt: string | null;
  activeDays: number;
  lastActivityAt: string | null;
  alerts: number;
  alertsOpened: number;
  alertsClicked: number;
  detailViews: number;
  outbound: number;
  saved: number;
  discarded: number;
  engaged: boolean;
  paid: boolean;
  revenue: number;
};

export type FunnelStep = { label: string; users: number };
export type ChannelRow = { channel: Channel; users: number; searched: number; engaged: number; paid: number; revenue: number };
export type Cohort = { week: string; users: number; retention: (number | null)[] };
export type Breakdown = { label: string; users: number };

export type UsersDashboard = {
  periodDays: number | null;
  users: UserStats[];
  inPeriod: UserStats[];
  kpis: { signups: number; prevSignups: number | null; searchedPct: number; engagedPct: number; paidPct: number; paid: number; active7d: number; withOrigin: number };
  funnel: FunnelStep[];
  channels: ChannelRow[];
  methods: Breakdown[];
  landings: Breakdown[];
  campaigns: Breakdown[];
  cohorts: Cohort[];
};

const DAY = 86_400_000;
const WEEKS_TRACKED = 4;

const pct = (part: number, total: number) => (total ? Math.round((part / total) * 100) : 0);

function tally(values: string[]): Breakdown[] {
  const map = new Map<string, number>();
  for (const v of values) map.set(v, (map.get(v) ?? 0) + 1);
  return [...map].map(([label, users]) => ({ label, users })).sort((a, b) => b.users - a.users);
}

/** Monday 00:00 UTC of the week of `t`, as YYYY-MM-DD. */
export function weekStart(t: number): string {
  const d = new Date(t);
  const day = (d.getUTCDay() + 6) % 7;
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - day)).toISOString().slice(0, 10);
}

export function buildUsersDashboard(
  input: { users: UserRow[]; events: EventRow[]; notifications: NotificationRow[]; payments: PaymentRow[] },
  now: Date,
  periodDays: number | null,
): UsersDashboard {
  const byUser = new Map<string, EventRow[]>();
  for (const e of input.events) {
    const list = byUser.get(e.user_id);
    if (list) list.push(e);
    else byUser.set(e.user_id, [e]);
  }
  const notes = new Map<string, NotificationRow[]>();
  for (const n of input.notifications) {
    const list = notes.get(n.user_id);
    if (list) list.push(n);
    else notes.set(n.user_id, [n]);
  }
  const pays = new Map<string, PaymentRow[]>();
  for (const p of input.payments) {
    if (p.refunded_at || !p.paid_at) continue;
    const list = pays.get(p.user_id);
    if (list) list.push(p);
    else pays.set(p.user_id, [p]);
  }

  const users: UserStats[] = input.users.map((u) => {
    const events = (byUser.get(u.id) ?? []).slice().sort((a, b) => a.created_at.localeCompare(b.created_at));
    const signup = events.find((e) => e.name === "signup_completed");
    const props = (signup?.props ?? {}) as Record<string, unknown>;
    const origin = parseOrigin(props.origin);
    const own = events.filter((e) => !SYSTEM_EVENTS.has(e.name));
    const count = (name: string) => own.filter((e) => e.name === name).length;
    const n = notes.get(u.id) ?? [];
    const p = pays.get(u.id) ?? [];
    const firstSearch = own.find((e) => SEARCH_EVENTS.has(e.name));
    return {
      ...u,
      origin,
      channel: origin ? channelOf(origin) : typeof props.channel === "string" ? (props.channel as Channel) : "unknown",
      method: typeof props.method === "string" ? props.method : null,
      firstSearchAt: firstSearch?.created_at ?? ((u.searches ?? 0) > 0 ? u.created_at : null),
      activeDays: new Set(own.map((e) => e.created_at.slice(0, 10))).size,
      lastActivityAt: own.at(-1)?.created_at ?? null,
      alerts: n.length,
      alertsOpened: n.filter((x) => x.opened_at || x.clicked_at).length,
      alertsClicked: n.filter((x) => x.clicked_at).length,
      detailViews: count("listing_detail_viewed"),
      outbound: count("listing_outbound_clicked"),
      saved: count("listing_saved"),
      discarded: count("listing_discarded"),
      engaged: own.some((e) => ENGAGED.has(e.name)) || n.some((x) => x.clicked_at),
      paid: p.length > 0,
      revenue: p.reduce((sum, x) => sum + Number(x.amount || 0), 0),
    };
  });

  const nowMs = now.getTime();
  const since = periodDays ? nowMs - periodDays * DAY : -Infinity;
  const inPeriod = users.filter((u) => Date.parse(u.created_at) >= since);
  const prevSignups = periodDays
    ? users.filter((u) => {
        const t = Date.parse(u.created_at);
        return t >= since - periodDays * DAY && t < since;
      }).length
    : null;

  const searched = inPeriod.filter((u) => u.firstSearchAt);
  const alerted = inPeriod.filter((u) => u.alerts > 0);
  const engaged = inPeriod.filter((u) => u.engaged);
  const paid = inPeriod.filter((u) => u.paid);

  const channelMap = new Map<Channel, ChannelRow>();
  for (const u of inPeriod) {
    const row = channelMap.get(u.channel) ?? { channel: u.channel, users: 0, searched: 0, engaged: 0, paid: 0, revenue: 0 };
    row.users += 1;
    if (u.firstSearchAt) row.searched += 1;
    if (u.engaged) row.engaged += 1;
    if (u.paid) row.paid += 1;
    row.revenue += u.revenue;
    channelMap.set(u.channel, row);
  }

  // Weekly cohorts: of the users who signed up in a week, the share that did
  // something of their own k weeks later (null while that week has not ended).
  const cohortMap = new Map<string, UserStats[]>();
  for (const u of users) {
    const key = weekStart(Date.parse(u.created_at));
    cohortMap.set(key, [...(cohortMap.get(key) ?? []), u]);
  }
  const cohorts: Cohort[] = [...cohortMap]
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, 8)
    .map(([week, members]) => ({
      week,
      users: members.length,
      retention: Array.from({ length: WEEKS_TRACKED }, (_, i) => {
        const k = i + 1;
        if (Date.parse(week) + (k + 1) * 7 * DAY > nowMs) return null;
        const back = members.filter((u) => {
          const start = Date.parse(u.created_at) + k * 7 * DAY;
          return (byUser.get(u.id) ?? []).some((e) => {
            const t = Date.parse(e.created_at);
            return !SYSTEM_EVENTS.has(e.name) && t >= start && t < start + 7 * DAY;
          });
        }).length;
        return pct(back, members.length);
      }),
    }));

  const METHOD: Record<string, string> = { email_only: "Búsqueda con email", email: "Email y contraseña", google: "Google", email_code: "Código por email" };

  return {
    periodDays,
    users,
    inPeriod,
    kpis: {
      signups: inPeriod.length,
      prevSignups,
      searchedPct: pct(searched.length, inPeriod.length),
      engagedPct: pct(engaged.length, inPeriod.length),
      paidPct: pct(paid.length, inPeriod.length),
      paid: paid.length,
      active7d: users.filter((u) => u.lastActivityAt && Date.parse(u.lastActivityAt) >= nowMs - 7 * DAY).length,
      withOrigin: inPeriod.filter((u) => u.origin).length,
    },
    funnel: [
      { label: "Se registraron", users: inPeriod.length },
      { label: "Crearon una búsqueda", users: searched.length },
      { label: "Recibieron una alerta", users: alerted.length },
      { label: "Miraron un auto", users: engaged.length },
      { label: "Pagaron", users: paid.length },
    ],
    channels: [...channelMap.values()].sort((a, b) => b.users - a.users),
    methods: tally(inPeriod.map((u) => (u.method ? (METHOD[u.method] ?? u.method) : "Sin evento de registro"))),
    landings: tally(inPeriod.filter((u) => u.origin).map((u) => landingKind(u.origin!.landing))),
    campaigns: tally(inPeriod.filter((u) => u.origin?.campaign || u.origin?.source).map((u) => [u.origin!.source, u.origin!.medium, u.origin!.campaign].filter(Boolean).join(" / "))),
    cohorts,
  };
}

export const PERIODS = [
  { key: "7", label: "7 días", days: 7 },
  { key: "30", label: "30 días", days: 30 },
  { key: "90", label: "90 días", days: 90 },
  { key: "todo", label: "Todo", days: null },
] as const;

export function periodDays(raw: string | string[] | undefined): number | null {
  const key = Array.isArray(raw) ? raw[0] : raw;
  const found = PERIODS.find((p) => p.key === key);
  return found ? found.days : 30;
}
