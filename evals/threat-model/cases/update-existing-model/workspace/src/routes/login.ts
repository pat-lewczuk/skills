import bcrypt from "bcryptjs";
import { Router } from "express";
import jwt from "jsonwebtoken";
import { db } from "../db.js";

export const login = Router();

login.post("/login", async (req, res) => {
  const { email, password } = req.body ?? {};
  const { rows } = await db.query(
    "SELECT id, account_id, role, password_hash FROM users WHERE email = $1", [email]);
  const user = rows[0];
  if (!user || !(await bcrypt.compare(String(password), user.password_hash))) {
    return res.status(401).json({ error: "invalid credentials" });
  }
  const token = jwt.sign({ id: user.id, accountId: user.account_id, role: user.role },
    process.env.JWT_SECRET!, { algorithm: "HS256", expiresIn: "8h" });
  res.json({ token });
});
