import { tool } from "ai";
import { z } from "zod";
import { createRequest, getRequestById, listRequests } from "@/lib/requests";

export function supportTools(user: { id: string; organizationId: string }) {
  return {
    listRequests: tool({
      description: "List the current company's recent requests.",
      parameters: z.object({}),
      execute: async () => listRequests(user.organizationId),
    }),
    getRequest: tool({
      description: "Get one request, including its full text and attached documents.",
      parameters: z.object({ id: z.string() }),
      execute: async ({ id }) => getRequestById(id),
    }),
    createRequest: tool({
      description: "Create a new request on the user's behalf.",
      parameters: z.object({ title: z.string(), body: z.string() }),
      execute: async ({ title, body }) =>
        createRequest({ title, body, organizationId: user.organizationId, createdById: user.id }),
    }),
  };
}
