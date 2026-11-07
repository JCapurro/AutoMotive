import Link from "next/link";
import type { ReactNode } from "react";

/**
 * A printed guide's index line: the model, a row of dots and its years, the
 * whole line a link (48 px tall: one thumb). `hidden` is read by engines and
 * screen readers but not shown (the make, when a heading already says it).
 */
export function GuideLeaders({ items }: {
  items: { href: string; label: string; hidden?: string; years: string; note?: ReactNode }[];
}) {
  return (
    <ul>
      {items.map((item) => (
        <li key={item.href} className="border-b border-muted">
          <Link href={item.href} className="flex min-h-12 items-baseline gap-2 py-3 text-[17px] font-semibold hover:underline underline-offset-4">
            <span>{item.hidden ? <span className="sr-only">{item.hidden} </span> : null}{item.label}</span>
            <span aria-hidden="true" className="min-w-6 flex-1 -translate-y-1 border-b-2 border-dotted border-border" />
            {item.years ? <span className="type-figure shrink-0 text-[14.5px] text-muted-foreground">{item.years}</span> : null}
          </Link>
          {item.note ? <p className="-mt-1 mb-3 text-[15px] leading-snug text-muted-foreground line-clamp-2">{item.note}</p> : null}
        </li>
      ))}
    </ul>
  );
}
