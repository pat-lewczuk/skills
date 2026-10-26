import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";

// Admin screen: change a user's role or remove them from the company.
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser();
  const { id } = await params;
  const { role } = await req.json();
  const target = await db.user.findFirst({ where: { id, organizationId: user.organizationId } });
  if (!target) return new Response("Not found", { status: 404 });
  const updated = await db.user.update({ where: { id }, data: { role } });
  return Response.json({ id: updated.id, role: updated.role });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await requireUser();
  if (user.role !== "ADMIN") return new Response("Forbidden", { status: 403 });
  const { id } = await params;
  await db.user.deleteMany({ where: { id, organizationId: user.organizationId } });
  return new Response(null, { status: 204 });
}
