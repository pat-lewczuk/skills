import { z } from "zod";
import { requireUser } from "@/lib/auth";
import { createRequest, listRequests } from "@/lib/requests";

export async function GET() {
  const user = await requireUser();
  return Response.json(await listRequests(user.organizationId));
}

const Body = z.object({ title: z.string().min(1).max(200), body: z.string().max(10_000) });

export async function POST(req: Request) {
  const user = await requireUser();
  const input = Body.parse(await req.json());
  const created = await createRequest({ ...input, organizationId: user.organizationId, createdById: user.id });
  return Response.json(created, { status: 201 });
}
