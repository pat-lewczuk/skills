import { db } from "./db";

export function listRequests(organizationId: string) {
  return db.request.findMany({
    where: { organizationId },
    orderBy: { createdAt: "desc" },
    take: 50,
  });
}

export function getRequestById(id: string) {
  return db.request.findUnique({ where: { id }, include: { documents: true } });
}

export function createRequest(input: { title: string; body: string; organizationId: string; createdById: string }) {
  return db.request.create({ data: input });
}
