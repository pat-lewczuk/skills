import { Router } from "express";

export const webhooks = Router();

webhooks.post("/webhooks/inbound-email", async (req, res) => {
  const { from, subject, text } = req.body;
  console.log("inbound", from, subject, text?.length);
  res.sendStatus(202);
});
