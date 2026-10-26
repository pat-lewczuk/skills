import { Router } from "express";
import pg from "pg";

const db = new pg.Pool();
export const tickets = Router();

tickets.get("/tickets/:id", async (req, res) => {
  const { rows } = await db.query("SELECT * FROM tickets WHERE id = $1", [req.params.id]);
  rows[0] ? res.json(rows[0]) : res.sendStatus(404);
});

export function priorityScore(ageHours: number, vip: boolean) {
  return Math.min(100, Math.round(ageHours * 2) + (vip ? 30 : 0));
}
