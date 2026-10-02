"use client";
import { useTransition } from "react";
import { toast } from "sonner";
import { declineRenewal } from "@/app/app/pro/renewal-actions";
import { Button } from "@/components/ui/button";

export function RenewalButton({ declined }: { declined: boolean }) {
  const [pending, start] = useTransition();
  return <Button variant="outline" disabled={pending || declined} onClick={() => start(async () => {
    const res = await declineRenewal();
    if (res.error) toast.error(res.error); else toast.success("Aviso registrado. Tu acceso sigue hasta el fin del período pagado.");
  })}>{declined ? "Registramos que no vas a renovar" : "Avisar que no voy a renovar"}</Button>;
}
