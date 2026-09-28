"use client";

import { useEffect, useRef } from "react";

import { markOpened } from "@/app/app/inbox/actions";

import { useInbox } from "./inbox-provider";

/** Marks the alerts on screen as opened, then updates the badge. */
export function MarkOpened({ ids }: { ids: number[] }) {
  const { refresh } = useInbox();
  const done = useRef(new Set<number>());
  const key = ids.join(",");
  useEffect(() => {
    const fresh = ids.filter((id) => !done.current.has(id));
    if (!fresh.length) return;
    fresh.forEach((id) => done.current.add(id));
    void markOpened(fresh).then(refresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands for the ids
  }, [key, refresh]);
  return null;
}
