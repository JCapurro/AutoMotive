"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useTransition } from "react";

import { reportVisibleResults, trackProCta } from "@/app/app/pro/actions";
import { Button } from "@/components/ui/button";
import type { Placement } from "@/lib/pro";
import { cn } from "@/lib/utils";

/** pro_cta_viewed once per tab session and placement (the banner re-renders on every navigation). */
function useViewed(placement: Placement) {
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const key = `pro_cta_viewed:${placement}`;
    try {
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      // No storage (private mode): count it every time rather than never.
    }
    void trackProCta("viewed", placement);
  }, [placement]);
}

/** "Probar Automotive Pro": records pro_cta_clicked, then opens the plans. */
export function ProCtaButton({
  placement,
  variant = "default",
  className,
}: {
  placement: Placement;
  variant?: "default" | "outline";
  className?: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <Button
      variant={variant}
      className={className}
      disabled={pending}
      onClick={() =>
        start(async () => {
          await trackProCta("clicked", placement);
          router.push(`/app/pro?from=${placement}`);
        })
      }
    >
      Probar Automotive Pro <ArrowRight aria-hidden />
    </Button>
  );
}

const COPY = {
  activity: {
    title: "¿Querés enterarte antes?",
    body: "Con Pro buscamos cada pocos minutos y te avisamos al instante, en todas tus búsquedas.",
  },
  plan_limit: {
    title: "Pasaste el límite del plan gratuito",
    body: "Durante el piloto no cortamos nada. Con Pro vas a tener varias búsquedas y alertas inmediatas.",
  },
  results: {
    title: "¿Querés ver todos los resultados?",
    body: "El plan gratuito va a mostrar hasta 50 publicaciones por búsqueda. Pro las muestra todas.",
  },
} as const;

/** §52: the banner, shown after real activity (pro_cta_state) or a limit. */
export function ProBanner({
  placement,
  reason,
  className,
}: {
  placement: Placement;
  reason: keyof typeof COPY;
  className?: string;
}) {
  useViewed(placement);
  const copy = COPY[reason];
  return (
    <aside
      aria-label="Automotive Pro"
      data-testid="pro-banner"
      className={cn(
        "flex flex-col gap-3 rounded-xl bg-amber-50 p-4 text-amber-950 ring-1 ring-amber-200 sm:flex-row sm:items-center",
        className,
      )}
    >
      <Sparkles className="hidden size-5 shrink-0 sm:block" aria-hidden />
      <div className="min-w-0 flex-1 space-y-0.5 text-sm">
        <p className="font-medium">{copy.title}</p>
        <p className="text-amber-900/80">{copy.body}</p>
      </div>
      <ProCtaButton placement={placement} className="shrink-0" />
    </aside>
  );
}

/** Tells the database the search has more results than the free plan shows (once per render of the page). */
export function VisibleResultsReport({ profileId, total }: { profileId: number; total: number }) {
  const done = useRef<string | null>(null);
  useEffect(() => {
    const key = `${profileId}:${total}`;
    if (done.current === key) return;
    done.current = key;
    void reportVisibleResults(profileId, total);
  }, [profileId, total]);
  return null;
}
