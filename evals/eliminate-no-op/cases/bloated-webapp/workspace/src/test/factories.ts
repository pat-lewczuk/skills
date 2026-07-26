let seq = 0;

export function makeCustomer(overrides: Partial<{ id: string; email: string }> = {}) {
  seq += 1;
  return { id: `cust_${seq}`, email: `customer${seq}@example.test`, ...overrides };
}

export function makeOrder(overrides: Partial<{ id: string; total: number }> = {}) {
  seq += 1;
  return { id: `ord_${seq}`, total: 1999, ...overrides };
}
