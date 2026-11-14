import { describe, expect, it } from "vitest";

import { buildUsersDashboard, periodDays, type UserRow, weekStart } from "./admin-users-data";

const now = new Date("2026-11-14T12:00:00Z");
const daysAgo = (d: number) => new Date(now.getTime() - d * 86_400_000).toISOString();
const user = (id: string, created: number, extra: Partial<UserRow> = {}): UserRow => ({
  id, email: `${id}@x.test`, plan: "free", plan_expires_at: null, role: "user", created_at: daysAgo(created),
  telegram_linked: false, email_only: true, searches: 0, enabled_searches: 0, waitlist_plan: null, ...extra,
});
const ev = (user_id: string, name: string, at: number, props: unknown = {}) => ({ user_id, name, props, created_at: daysAgo(at) });

const input = {
  users: [user("a", 3, { searches: 1 }), user("b", 10), user("c", 40), user("d", 20)],
  events: [
    ev("a", "signup_completed", 3, { method: "email_only", origin: { source: "facebook", medium: "paid", landing: "/" } }),
    ev("a", "search_created", 3),
    ev("a", "listing_detail_viewed", 2),
    ev("b", "signup_completed", 10, { method: "google", origin: { referrer: "google.com.ar", landing: "/guias/ford/focus" } }),
    ev("b", "alert_sent", 1),
    ev("c", "signup_completed", 40, { method: "email" }),
    ev("d", "signup_completed", 20, { method: "email_only" }),
    ev("d", "search_created", 20),
    ev("d", "listing_saved", 12),
  ],
  notifications: [
    { user_id: "a", sent_at: daysAgo(2), opened_at: daysAgo(2), clicked_at: null },
    { user_id: "b", sent_at: daysAgo(1), opened_at: null, clicked_at: null },
    { user_id: "d", sent_at: daysAgo(15), opened_at: daysAgo(15), clicked_at: daysAgo(15) },
  ],
  payments: [
    { user_id: "d", amount: "5000", paid_at: daysAgo(14), refunded_at: null },
    { user_id: "b", amount: 5000, paid_at: daysAgo(5), refunded_at: daysAgo(4) },
  ],
};

describe("buildUsersDashboard", () => {
  const d = buildUsersDashboard(input, now, 30);
  const by = Object.fromEntries(d.users.map((u) => [u.id, u]));

  it("reads the channel from the signup's first touch, unknown without one", () => {
    expect(by.a.channel).toBe("meta_ads");
    expect(by.b.channel).toBe("search");
    expect(by.c.channel).toBe("unknown");
    expect(by.a.method).toBe("email_only");
  });

  it("counts what each user did, ignoring what the system wrote", () => {
    expect(by.a).toMatchObject({ alerts: 1, alertsOpened: 1, alertsClicked: 0, detailViews: 1, engaged: true, paid: false });
    expect(by.b).toMatchObject({ alerts: 1, engaged: false, paid: false, activeDays: 1 });
    expect(by.d).toMatchObject({ saved: 1, alertsClicked: 1, paid: true, revenue: 5000 });
  });

  it("builds the funnel over the period's signups", () => {
    expect(d.inPeriod.map((u) => u.id).sort()).toEqual(["a", "b", "d"]);
    expect(d.funnel.map((s) => s.users)).toEqual([3, 2, 3, 2, 1]);
    expect(d.kpis).toMatchObject({ signups: 3, prevSignups: 1, paidPct: 33, withOrigin: 2 });
  });

  it("splits by channel with each one's outcomes", () => {
    const unknown = d.channels.find((c) => c.channel === "unknown")!;
    expect(unknown).toMatchObject({ users: 1, searched: 1, engaged: 1, paid: 1, revenue: 5000 });
    expect(d.landings).toEqual(expect.arrayContaining([{ label: "Guía", users: 1 }, { label: "Inicio", users: 1 }]));
    expect(d.campaigns).toEqual([{ label: "facebook / paid", users: 1 }]);
  });

  it("measures weekly retention only for weeks that ended", () => {
    const week = d.cohorts.find((c) => c.week === weekStart(Date.parse(daysAgo(20))))!;
    expect(week.users).toBe(1);
    expect(week.retention[0]).toBe(100); // saved a car 8 days after signing up
    expect(week.retention[1]).toBe(0);
    expect(d.cohorts[0].retention.every((r) => r === null)).toBe(true);
  });

  it("covers every account with no period", () => {
    expect(buildUsersDashboard(input, now, null).kpis).toMatchObject({ signups: 4, prevSignups: null });
  });
});

it("reads the period, 30 days by default", () => {
  expect(periodDays(undefined)).toBe(30);
  expect(periodDays("7")).toBe(7);
  expect(periodDays("todo")).toBeNull();
  expect(periodDays("999")).toBe(30);
});

it("starts weeks on Monday", () => {
  expect(weekStart(Date.parse("2026-11-14T12:00:00Z"))).toBe("2026-11-09");
  expect(weekStart(Date.parse("2026-11-09T00:00:00Z"))).toBe("2026-11-09");
});
