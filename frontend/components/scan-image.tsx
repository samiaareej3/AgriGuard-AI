"use client";

import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchBlobUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Scan images require auth, so they are fetched as blobs rather than via <img src>. */
export function ScanImage({ scanId, alt, className }: { scanId: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setUrl(null);
    fetchBlobUrl(`/scans/${scanId}/image`)
      .then((u) => {
        objectUrl = u;
        if (!revoked) setUrl(u);
      })
      .catch(() => !revoked && setFailed(true));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [scanId]);
  if (failed) {
    return (
      <div className={cn("grid place-items-center bg-muted text-muted-foreground", className)} title="Image unavailable (retention policy or missing file)">
        <ImageOff className="size-5" aria-hidden />
        <span className="sr-only">Image unavailable</span>
      </div>
    );
  }
  if (!url) return <Skeleton className={className} />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className={cn("object-cover", className)} />;
}
