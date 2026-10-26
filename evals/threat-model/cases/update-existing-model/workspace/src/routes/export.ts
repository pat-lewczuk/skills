import { Router } from "express";
import { db } from "../db.js";

export const exportRoutes = Router();

// CSV export of all invoices in a date range, for accountants.
exportRoutes.get("/invoices/export.csv", async (req, res) => {
  const from = typeof req.query.from === "string" ? req.query.from : "1970-01-01";
  const to = typeof req.query.to === "string" ? req.query.to : "2999-12-31";
  const { rows } = await db.query(
    `SELECT number, customer_name, customer_email, total_cents, status, issued_at
       FROM invoices WHERE account_id = $1 AND issued_at BETWEEN $2 AND $3
      ORDER BY issued_at`,
    [req.user.accountId, from, to]);

  res.setHeader("Content-Type", "text/csv");
  res.setHeader("Content-Disposition", 'attachment; filename="invoices.csv"');
  res.write("number,customer,email,total,status,issued\n");
  for (const r of rows) {
    res.write([r.number, r.customer_name, r.customer_email, (r.total_cents / 100).toFixed(2),
      r.status, r.issued_at.toISOString()].join(",") + "\n");
  }
  res.end();
});
