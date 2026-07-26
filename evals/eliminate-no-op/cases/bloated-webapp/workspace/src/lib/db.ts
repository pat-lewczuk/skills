import { Pool } from 'pg';

// Single pool for the whole app. Importing `pg` anywhere else creates a second pool and
// exhausts the connection limit under load.
const pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 12 });

export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const res = await pool.query(sql, params);
  return res.rows as T[];
}
