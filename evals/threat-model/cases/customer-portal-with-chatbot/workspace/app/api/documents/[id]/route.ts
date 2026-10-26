import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { getObject } from "@/lib/storage";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser();
  const { id } = await params;
  const doc = await db.document.findFirst({ where: { id, organizationId: user.organizationId } });
  if (!doc) return new Response("Not found", { status: 404 });
  const obj = await getObject(doc.storageKey);
  return new Response(obj.Body as ReadableStream, {
    headers: {
      "Content-Type": obj.ContentType ?? "application/octet-stream",
      "Content-Disposition": `attachment; filename="${doc.filename}"`,
    },
  });
}
