import bcrypt from "bcryptjs";
import { z } from "zod";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";

const Invite = z.object({ email: z.string().email(), password: z.string().min(12) });

export async function POST(req: Request) {
  const user = await requireUser();
  if (user.role !== "ADMIN") return new Response("Forbidden", { status: 403 });
  const { email, password } = Invite.parse(await req.json());
  const created = await db.user.create({
    data: { email, passwordHash: await bcrypt.hash(password, 12), organizationId: user.organizationId },
  });
  return Response.json({ id: created.id, email: created.email }, { status: 201 });
}
