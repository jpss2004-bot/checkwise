/**
 * Normalize a fetched document Blob to `application/pdf`.
 *
 * Why: the document-preview surfaces render the blob in an `<iframe>`, and a
 * blob whose Content-Type is missing or `application/octet-stream` (some
 * storage/proxy responses) is treated by browsers as a download rather than an
 * inline-renderable PDF — i.e. a blank preview. Re-wrapping with an explicit
 * `application/pdf` type guarantees inline rendering. The re-wrap only happens
 * when the type isn't already correct, so the common path adds no extra copy.
 */
export async function toPdfBlob(blob: Blob): Promise<Blob> {
  if (blob.type === "application/pdf") return blob;
  return new Blob([await blob.arrayBuffer()], { type: "application/pdf" });
}
