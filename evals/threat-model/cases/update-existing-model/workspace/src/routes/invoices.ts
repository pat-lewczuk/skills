import { Router } from "express";
import { z } from "zod";
import { requireRole } from "../auth.js";
import { db } from "../db.js";

export const invoices = Router();

invoices.get("/invoices", async (req, res) => {
  const q = typeof req.query.q === "string" ? `%${req.query.q}%` : "%";
  const { rows } = await db.query(
    "SELECT * FROM invoices WHERE account_id = $1 AND customer_name ILIKE $2 ORDER BY issued_at DESC LIMIT 100",
    [req.user.accountId, q]);
  res.json(rows);
});

invoices.get("/invoices/:id", async (req, res) => {
  const { rows } = await db.query(
    "SELECT * FROM invoices WHERE id = $1 AND account_id = $2", [req.params.id, req.user.accountId]);
  if (!rows[0]) return res.status(404).json({ error: "not found" });
  res.json(rows[0]);
});

const NewInvoice = z.object({
  customerName: z.string().min(1).max(200),
  customerEmail: z.string().email(),
  totalCents: z.number().int().nonnegative(),
});

invoices.post("/invoices", async (req, res) => {
  const body = NewInvoice.parse(req.body);
  const { rows } = await db.query(
    `INSERT INTO invoices (account_id, customer_name, customer_email, total_cents, status, issued_at)
     VALUES ($1, $2, $3, $4, 'draft', now()) RETURNING *`,
    [req.user.accountId, body.customerName, body.customerEmail, body.totalCents]);
  res.status(201).json(rows[0]);
});

invoices.post("/invoices/:id/void", requireRole("owner"), async (req, res) => {
  const { rowCount } = await db.query(
    "UPDATE invoices SET status = 'void' WHERE id = $1 AND account_id = $2",
    [req.params.id, req.user.accountId]);
  res.status(rowCount ? 204 : 404).end();
});
