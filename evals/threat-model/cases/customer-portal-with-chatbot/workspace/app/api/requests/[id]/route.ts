import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { getRequestById } from "@/lib/requests";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const { id } = await params;
  const request = await getRequestById(id);
  if (!request) return new Response("Not found", { status: 404 });
  return Response.json(request);
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  await requireUser();
  const { id } = await params;
  const data = await req.json();
  const updated = await db.request.update({ where: { id }, data });
  return Response.json(updated);
}
