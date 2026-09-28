import { type NextRequest, NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { unsubscribeToken } from "@/lib/unsubscribe";

export const dynamic = "force-dynamic";

/**
 * One-click unsubscribe (RFC 8058): the mail client POSTs here from the
 * List-Unsubscribe header the worker sets on every alert email (F7, punto 7).
 */
export async function POST(request: NextRequest) {
  const token = unsubscribeToken(request.nextUrl.searchParams.get("t"));
  if (!token) return new NextResponse("Link inválido", { status: 400 });
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("unsubscribe_email", { p_token: token });
  if (error) return new NextResponse("No pudimos procesarlo", { status: 500 });
  if (!data) return new NextResponse("Link inválido", { status: 404 });
  return new NextResponse("Listo: no te mandamos más emails.", { status: 200 });
}
