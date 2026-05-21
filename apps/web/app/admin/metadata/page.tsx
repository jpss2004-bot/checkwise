import { redirect } from "next/navigation";

export default function AdminMetadataRedirectPage() {
  redirect("/admin/clients");
}
