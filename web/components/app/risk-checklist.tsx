"use client";

import { ClipboardList, Copy, ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { trackRiskChecklist } from "@/app/app/listings/actions";
import { Button } from "@/components/ui/button";
import {
  checklistItems,
  checklistText,
  RISK_COPIED,
  RISK_COPY_FAILED,
  RISK_COPY_LABEL,
  RISK_EMPHASIS,
  RISK_HEADER,
  RISK_OFFICIAL_LABEL,
  type RiskConfig,
  type RiskItem,
  type RiskLink,
  safeRiskUrl,
} from "@/lib/risk-checklist";

/**
 * PAR-02 «Antes de señar»: controls the user should do, never something Ese
 * Auto checked. Closed by default; open with an emphasis line when the price
 * itself is a reason for care. risk_checklist_viewed is logged once per mount:
 * when the open block enters the screen, or when the closed one is expanded.
 */
export function RiskChecklist({
  listingId,
  title,
  config,
  emphasized,
}: {
  listingId: number;
  title: string;
  config: RiskConfig;
  emphasized: boolean;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  const viewed = useRef(false);

  function view() {
    if (viewed.current) return;
    viewed.current = true;
    void trackRiskChecklist(listingId, "viewed");
  }

  useEffect(() => {
    const node = ref.current;
    if (!node || !emphasized || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting) || !node.open) return;
      observer.disconnect();
      if (viewed.current) return;
      viewed.current = true;
      void trackRiskChecklist(listingId, "viewed");
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [emphasized, listingId]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(checklistText(title));
      toast.success(RISK_COPIED);
    } catch {
      toast.error(RISK_COPY_FAILED);
    }
    void trackRiskChecklist(listingId, "copied");
  }

  return (
    <details
      ref={ref}
      open={emphasized}
      data-testid="risk-checklist"
      className="mt-3 rounded-lg bg-muted p-4"
      onToggle={(event) => {
        if (event.currentTarget.open) view();
      }}
    >
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
        <ClipboardList className="size-4" aria-hidden /> Ver los controles
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-sm">{RISK_HEADER}</p>
        {emphasized ? (
          <p data-testid="risk-emphasis" className="text-sm font-semibold text-warn">
            {RISK_EMPHASIS}
          </p>
        ) : null}
        <ol className="list-decimal space-y-2 pl-5 text-[15px]">
          {checklistItems(config).map((item) => (
            <Item key={item.id} item={item} />
          ))}
        </ol>
        <Button onClick={copy}>
          <Copy aria-hidden /> {RISK_COPY_LABEL}
        </Button>
      </div>
    </details>
  );
}

function OfficialLink({ link, children }: { link: RiskLink; children: React.ReactNode }) {
  if (!safeRiskUrl(link.url)) return null;
  return (
    <a href={link.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm underline">
      {children}
      <ExternalLink className="size-3.5" aria-hidden />
    </a>
  );
}

function Item({ item }: { item: RiskItem }) {
  const groups = (item.groups ?? [])
    .map((group) => ({ ...group, links: group.links.filter((link) => safeRiskUrl(link.url)) }))
    .filter((group) => group.links.length > 0);
  return (
    <li data-risk-item={item.id} className="break-words">
      {item.text}
      {item.official && safeRiskUrl(item.official.url) ? (
        <span className="ml-1.5">
          <OfficialLink link={item.official}>
            {RISK_OFFICIAL_LABEL}
            <span className="sr-only"> ({item.official.label})</span>
          </OfficialLink>
        </span>
      ) : null}
      {groups.map((group) => (
        <div key={group.title} className="mt-1">
          <span className="text-sm text-muted-foreground">{group.title}:</span>
          <ul className="mt-0.5 flex flex-wrap gap-x-3 gap-y-1">
            {group.links.map((link) => (
              <li key={`${link.label}-${link.url}`}>
                <OfficialLink link={link}>{link.label}</OfficialLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </li>
  );
}
