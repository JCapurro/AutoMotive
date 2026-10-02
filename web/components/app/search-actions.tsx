"use client";

import { Pause, Play, Trash2 } from "lucide-react";
import { useTransition } from "react";
import { toast } from "sonner";

import { deleteSearch, setSearchEnabled, setSearchFrequency } from "@/app/app/searches/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { FREQUENCY, type Frequency } from "@/lib/copy";

export function PauseButton({ id, enabled }: { id: number; enabled: boolean }) {
  const [pending, start] = useTransition();
  return (
    <Button variant="outline" size="sm" disabled={pending} onClick={() => start(async () => {
      const result = await setSearchEnabled(id, !enabled);
      if (result.error) toast.error(result.error);
    })}>
      {enabled ? <Pause aria-hidden /> : <Play aria-hidden />}
      {enabled ? "Pausar" : "Reanudar"}
    </Button>
  );
}

export function FrequencySelect({ id, value, dailyOnly = false }: { id: number; value: Frequency; dailyOnly?: boolean }) {
  const [pending, start] = useTransition();
  return (
    <NativeSelect
      size="sm"
      aria-label="Frecuencia de alertas"
      value={dailyOnly ? "daily" : value}
      disabled={pending || dailyOnly}
      title={dailyOnly ? "La prueba gratis incluye resumen diario. Tu preferencia se conserva para el plan pago." : undefined}
      onChange={(e) => {
        const next = e.target.value as Frequency;
        start(() => setSearchFrequency(id, next));
      }}
    >
      {(Object.keys(FREQUENCY) as Frequency[]).map((f) => (
        <NativeSelectOption key={f} value={f}>
          Alertas: {FREQUENCY[f].label.toLowerCase()}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}

export function DeleteSearchButton({ id, name }: { id: number; name: string }) {
  const [pending, start] = useTransition();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive">
          <Trash2 aria-hidden /> Eliminar
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Eliminar «{name}»?</DialogTitle>
          <DialogDescription>
            Dejamos de monitorearla y se borran sus resultados. Las publicaciones que guardaste siguen en Guardados.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancelar</Button>
          </DialogClose>
          <Button variant="destructive" disabled={pending} onClick={() => start(() => deleteSearch(id))}>
            Eliminar búsqueda
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
