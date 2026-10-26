import jwt from "jsonwebtoken";
import request from "supertest";
import { beforeAll, describe, expect, it } from "vitest";
import { app } from "../src/app.js";
import { seedTwoAccounts } from "./seed.js";

const token = (u: { id: string; accountId: string; role: string }) =>
  jwt.sign(u, process.env.JWT_SECRET!, { algorithm: "HS256" });

describe("invoice access across accounts (T-03)", () => {
  let seed: Awaited<ReturnType<typeof seedTwoAccounts>>;
  beforeAll(async () => { seed = await seedTwoAccounts(); });

  it("returns 404 when account A asks for account B's invoice", async () => {
    const res = await request(app)
      .get(`/invoices/${seed.accountB.invoiceId}`)
      .set("Authorization", `Bearer ${token(seed.accountA.member)}`);
    expect(res.status).toBe(404);
  });

  it("returns the invoice to its own account", async () => {
    const res = await request(app)
      .get(`/invoices/${seed.accountA.invoiceId}`)
      .set("Authorization", `Bearer ${token(seed.accountA.member)}`);
    expect(res.status).toBe(200);
  });
});
