import type { NextFunction, Request, Response } from "express";
import jwt from "jsonwebtoken";

export type AuthUser = { id: string; accountId: string; role: "owner" | "member" };

declare global {
  namespace Express {
    interface Request { user: AuthUser }
  }
}

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace(/^Bearer /, "");
  if (!token) return res.status(401).json({ error: "unauthorized" });
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET!, { algorithms: ["HS256"] }) as AuthUser;
    next();
  } catch {
    res.status(401).json({ error: "unauthorized" });
  }
}

export function requireRole(role: AuthUser["role"]) {
  return (req: Request, res: Response, next: NextFunction) =>
    req.user.role === role ? next() : res.status(403).json({ error: "forbidden" });
}
