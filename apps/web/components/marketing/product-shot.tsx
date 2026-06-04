import Image from "next/image";

import { cn } from "@/lib/utils";

export type ProductShotFocus = {
  zoom?: number;
  origin?: string;
  position?: string;
};

type ProductShotProps = {
  src: string;
  alt: string;
  sizes: string;
  className?: string;
  priority?: boolean;
  loading?: "eager" | "lazy";
  focus?: ProductShotFocus;
  fit?: "cover" | "contain";
};

export function ProductShot({
  src,
  alt,
  sizes,
  className,
  priority,
  loading,
  focus,
  fit = "cover",
}: ProductShotProps) {
  const zoom = focus?.zoom ?? 1;

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden bg-[color:var(--surface-page)]",
        className,
      )}
    >
      <Image
        src={src}
        alt={alt}
        fill
        priority={priority}
        loading={priority ? undefined : loading}
        sizes={sizes}
        className={cn(
          "transition-transform duration-deliberate ease-enter",
          fit === "contain" ? "object-contain" : "object-cover",
        )}
        style={{
          objectPosition: focus?.position ?? "top center",
          transform: zoom === 1 ? undefined : `scale(${zoom})`,
          transformOrigin: focus?.origin ?? "50% 0%",
          willChange: zoom === 1 ? undefined : "transform",
        }}
      />
    </div>
  );
}
