import Link from "next/link";

import { cn } from "@/lib/utils";

/** The wordmark, marked with the highlighter like everything worth a look. */
export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} aria-label="S Auto · eseauto.com.ar" className={cn("text-[21px] leading-none font-extrabold tracking-[-0.01em] [font-stretch:118%]", className)}>
      <span className="mark">S Auto</span>
    </Link>
  );
}
