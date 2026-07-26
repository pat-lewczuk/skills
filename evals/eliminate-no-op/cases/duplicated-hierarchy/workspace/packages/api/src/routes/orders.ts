import { assertSession } from '../auth';

export async function listOrders(req, reply) {
  assertSession(req);
  return reply.send([]);
}
