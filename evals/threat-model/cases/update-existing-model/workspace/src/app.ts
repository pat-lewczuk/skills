import express from "express";
import { requireAuth } from "./auth.js";
import { exportRoutes } from "./routes/export.js";
import { invoices } from "./routes/invoices.js";
import { login } from "./routes/login.js";

export const app = express();
app.use(express.json({ limit: "100kb" }));

app.use(login);
app.use(requireAuth);
app.use(exportRoutes);
app.use(invoices);

app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error(err);
  res.status(500).json({ error: "internal error" });
});
