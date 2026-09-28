"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { type Sort, SORTS } from "@/lib/sorts";

/** §29 "Orden": keeps the filter, drops the page. */
export function SortSelect({ value }: { value: Sort }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <NativeSelect
      size="sm"
      aria-label="Ordenar"
      value={value}
      onChange={(e) => {
        const next = new URLSearchParams(params);
        next.set("s", e.target.value);
        next.delete("p");
        router.push(`${pathname}?${next}`);
      }}
    >
      {(Object.keys(SORTS) as Sort[]).map((s) => (
        <NativeSelectOption key={s} value={s}>
          {SORTS[s]}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}
