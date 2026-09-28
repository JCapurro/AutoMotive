"use client";

import { Loader2 } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { deleteAccount } from "@/app/app/settings/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const CONFIRM = "BORRAR";

/** «Borrar mi cuenta» (F7, punto 7): typed confirmation, then it's gone. */
export function DeleteAccount() {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [pending, start] = useTransition();

  const confirm = () =>
    start(async () => {
      const result = await deleteAccount();
      if (result?.error) toast.error("No pudimos borrar la cuenta. Probá de nuevo.");
    });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        setTyped("");
      }}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" className="text-destructive hover:text-destructive">
          Borrar mi cuenta
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Borrar tu cuenta?</DialogTitle>
          <DialogDescription>
            Borramos tu email, tus búsquedas, alertas, publicaciones guardadas y todo tu historial. No se puede
            deshacer.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="delete-confirm">
            Escribí <strong>{CONFIRM}</strong> para confirmar
          </Label>
          <Input id="delete-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button variant="destructive" onClick={confirm} disabled={pending || typed.trim().toUpperCase() !== CONFIRM}>
            {pending ? <Loader2 className="animate-spin" /> : null}
            Borrar definitivamente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
