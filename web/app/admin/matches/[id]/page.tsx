import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Inspector } from "@/components/admin/inspector";
import { PageHeader, TextLink } from "@/components/admin/ui";
import { inspectMatch } from "@/lib/admin-inspect";

export const metadata: Metadata = { title: "Match" };

// The inspector (sección 10, §45) for one match, alerted or not.
export default async function MatchInspector({ params }: PageProps<"/admin/matches/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const data = await inspectMatch(Number(id));
  if (!data?.match) notFound();

  return (
    <>
      <PageHeader
        title={`Match #${id}`}
        description={`Listing #${data.match.listing_id} · búsqueda #${data.match.search_profile_id}${data.email ? ` de ${data.email}` : ""}`}
      >
        <TextLink href="/admin/matches" className="text-sm">
          ← Matches
        </TextLink>
      </PageHeader>
      <Inspector data={data} />
    </>
  );
}
