"use client";

import { Children, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import { PLAN_CARD, PlanFeatures } from "@/components/plan-card-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Below lg the cards slide sideways and open on `start` (Particular); the tabs
 * jump to a card. From lg up it is a plain three-column grid.
 */
export function PlanCarousel({ labels, start, children }: { labels: string[]; start: number; children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(start);
  const count = Children.count(children);

  function cardAt(index: number) {
    return track.current?.children[index] as HTMLElement | undefined;
  }
  function show(index: number, smooth: boolean) {
    const el = track.current, card = cardAt(index);
    if (!el || !card) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ left: card.offsetLeft - (el.clientWidth - card.offsetWidth) / 2, behavior: smooth && !reduce ? "smooth" : "auto" });
    setActive(index);
  }

  // Open on the recommended plan; on wide screens there is nothing to scroll.
  useEffect(() => {
    if (!window.matchMedia("(min-width: 1024px)").matches) show(start, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start]);

  useEffect(() => {
    const el = track.current;
    if (!el) return;
    Array.from(el.children).forEach((card, i) => (card as HTMLElement).dataset.active = String(i === active));
  }, [active]);

  function onScroll() {
    const el = track.current;
    if (!el) return;
    const middle = el.scrollLeft + el.clientWidth / 2;
    let best = 0, distance = Infinity;
    Array.from(el.children).forEach((card, i) => {
      const c = card as HTMLElement;
      const d = Math.abs(c.offsetLeft + c.offsetWidth / 2 - middle);
      if (d < distance) { distance = d; best = i; }
    });
    if (best !== active) setActive(best);
  }

  return (
    <div>
      <div role="group" aria-label="Ir a un plan" className="mb-4 flex gap-6 border-b lg:hidden">
        {labels.map((label, i) => (
          <button key={label} type="button" aria-pressed={i === active} onClick={() => show(i, true)}
            className={cn("-mb-px border-b-2 px-1 py-2 text-[15px] font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
              i === active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {label}
          </button>
        ))}
      </div>
      <div ref={track} onScroll={onScroll}
        className="relative -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pt-1 pb-2 [scrollbar-width:none] sm:-mx-6 sm:px-6 lg:mx-0 lg:grid lg:grid-cols-3 lg:gap-x-5 lg:overflow-visible lg:px-0 lg:pt-0 lg:pb-0 [&::-webkit-scrollbar]:hidden">
        {children}
      </div>
      <div aria-hidden className="mt-3 flex justify-center gap-1.5 lg:hidden">
        {Array.from({ length: count }, (_, i) => (
          <span key={i} className={cn("h-2 rounded-full transition-all motion-reduce:transition-none", i === active ? "w-5 bg-foreground" : "w-2 bg-border")} />
        ))}
      </div>
    </div>
  );
}

export type PassVariant = {
  plan: "pass_7" | "pass_30";
  days: number;
  price: string;
  period: string;
  pitch: string;
  terms: string;
  cta: string;
  href: string;
};

/**
 * Particular: one plan, two durations. Both variants are rendered and the one
 * not chosen is hidden, so the page carries both prices without JavaScript.
 */
export function PassCard({ name, badge, variants, features, guarantee, initial }: {
  name: string; badge: string; variants: PassVariant[]; features: string[]; guarantee: string; initial: PassVariant["plan"];
}) {
  const [plan, setPlan] = useState(initial);
  const each = (render: (v: PassVariant) => ReactNode) => variants.map((v) => <div key={v.plan} hidden={v.plan !== plan}>{render(v)}</div>);
  return (
    <article aria-label={name} className={cn(PLAN_CARD, "border-2 border-foreground p-[19px]")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xl font-bold">{name}</h3>
        <Badge>{badge}</Badge>
      </div>
      <div role="group" aria-label="Duración del pase" className="mt-4 grid grid-cols-2 gap-0.5 rounded-lg bg-muted p-[3px]">
        {variants.map((v) => (
          <button key={v.plan} type="button" aria-pressed={v.plan === plan} onClick={() => setPlan(v.plan)}
            className={cn("h-8 rounded-md text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
              v.plan === plan ? "bg-background text-foreground shadow-[0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-foreground")}>
            {v.days} días
          </button>
        ))}
      </div>
      <div>{each((v) => <p className="mt-4 text-3xl font-bold"><span data-plan-price>{v.price}</span><span className="ml-1.5 text-sm font-medium text-muted-foreground">ARS</span></p>)}</div>
      <div>{each((v) => <p className="mt-1 text-sm text-muted-foreground">{v.period}</p>)}</div>
      <div>{each((v) => <p className="mt-4 text-muted-foreground">{v.pitch}</p>)}</div>
      <PlanFeatures items={features} />
      <div className="mt-5 space-y-3 text-sm">
        {each((v) => <p className="text-muted-foreground">{v.terms}</p>)}
        <p className="flex items-start gap-2.5 font-medium"><ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />{guarantee}</p>
      </div>
      <div className="mt-auto pt-6">
        {each((v) => (
          <Button asChild className="h-auto min-h-10 w-full whitespace-normal py-2 text-center">
            <Link href={v.href}>{v.cta}</Link>
          </Button>
        ))}
      </div>
    </article>
  );
}
