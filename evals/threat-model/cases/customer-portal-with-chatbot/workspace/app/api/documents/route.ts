import { randomUUID } from "node:crypto";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { putObject } from "@/lib/storage";

export async function POST(req: Request) {
  const user = await requireUser();
  const form = await req.formData();
  const file = form.get("file") as File;
  const requestId = form.get("requestId") as string | null;

  const storageKey = `${user.organizationId}/${randomUUID()}`;
  await putObject(storageKey, Buffer.from(await file.arrayBuffer()), file.type);

  const doc = await db.document.create({
    data: { filename: file.name, storageKey, organizationId: user.organizationId, requestId },
  });
  return Response.json(doc, { status: 201 });
}
