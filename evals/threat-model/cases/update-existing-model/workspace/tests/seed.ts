import { db } from "../src/db.js";

export async function seedTwoAccounts() {
  const mk = async (name: string) => {
    const { rows: [acct] } = await db.query("INSERT INTO accounts (name) VALUES ($1) RETURNING id", [name]);
    const { rows: [member] } = await db.query(
      "INSERT INTO users (account_id, email, role, password_hash) VALUES ($1, $2, 'member', 'x') RETURNING id",
      [acct.id, `${name}@example.test`]);
    const { rows: [inv] } = await db.query(
      `INSERT INTO invoices (account_id, customer_name, customer_email, total_cents, status, issued_at)
       VALUES ($1, 'Synthetic Co', 'billing@example.test', 1000, 'draft', now()) RETURNING id`, [acct.id]);
    return { member: { id: member.id, accountId: acct.id, role: "member" }, invoiceId: inv.id };
  };
  return { accountA: await mk("a"), accountB: await mk("b") };
}
