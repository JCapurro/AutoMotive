import Link from "next/link";

import { cn } from "@/lib/utils";

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <span aria-hidden className="grid size-7 place-items-center rounded-md bg-primary text-sm text-primary-foreground">
        A
      </span>
      <span>Automotive</span>
    </Link>
  );
}
