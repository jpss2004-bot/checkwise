import { MessageCircle, QrCode } from "lucide-react";

import { Button } from "@/components/ui/button";

export function SupportCard() {
  const whatsappUrl = process.env.NEXT_PUBLIC_WHATSAPP_SUPPORT_URL;
  const qrUrl = process.env.NEXT_PUBLIC_SUPPORT_QR_PLACEHOLDER_URL;

  return (
    <section className="rounded-md border border-border bg-white p-5 shadow-soft">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-muted text-primary">
          <MessageCircle className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-base font-semibold">Soporte documental</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ¿No sabes qué documento subir? Contacta soporte antes de enviar un archivo incorrecto.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-dashed border-border bg-muted/50 p-4 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <QrCode className="h-4 w-4 text-primary" aria-hidden="true" />
          WhatsApp Business
        </div>
        {qrUrl ? (
          <div
            role="img"
            aria-label="QR de soporte WhatsApp"
            className="mt-3 h-28 w-28 rounded-md border bg-cover bg-center"
            style={{ backgroundImage: `url(${qrUrl})` }}
          />
        ) : (
          <div className="mt-3 flex h-28 w-28 items-center justify-center rounded-md border border-border bg-white text-xs text-muted-foreground">
            QR pendiente
          </div>
        )}
      </div>

      {whatsappUrl ? (
        <Button asChild className="mt-4 w-full" variant="outline">
          <a href={whatsappUrl} target="_blank" rel="noreferrer">
            Abrir soporte
          </a>
        </Button>
      ) : (
        <p className="mt-4 text-xs text-muted-foreground">
          Configura `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL` cuando exista el número final.
        </p>
      )}
    </section>
  );
}
