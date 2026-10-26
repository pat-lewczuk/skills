import express from "express";
import { tickets } from "./routes/tickets.js";
import { webhooks } from "./routes/webhooks.js";

const app = express();
app.use(express.json());
app.use(webhooks);
app.use(tickets);
app.listen(3000);
