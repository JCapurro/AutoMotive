import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DeleteSearchButton } from "@/components/app/search-actions";
import { SearchForm } from "@/components/app/search-form";
import { requireUser } from "@/lib/auth";
import { fromProfile } from "@/lib/search-form";
import { createClient } from "@/lib/supabase/server";

import { loadFormData } from "../../form-data";

export const metadata: Metadata = { title: "Editar búsqueda" };

export default async function EditSearchPage({ params }: PageProps<"/app/searches/[id]/edit">) {
  await requireUser();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const supabase = await createClient();
  const [{ data: profile }, formData] = await Promise.all([
    supabase.from("search_profiles").select("*").eq("id", Number(id)).maybeSingle(),
    loadFormData(supabase),
  ]);
  if (!profile) notFound();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <Link href={`/app/searches/${profile.id}`} className="text-sm text-muted-foreground hover:underline">
            ← {profile.name}
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">Editar búsqueda</h1>
        </div>
        <DeleteSearchButton id={profile.id} name={profile.name} />
      </div>
      <SearchForm
        catalog={formData.catalog}
        sources={formData.sources}
        initial={fromProfile(profile, formData.sources.map((s) => s.id))}
        profileId={profile.id}
      />
    </div>
  );
}
