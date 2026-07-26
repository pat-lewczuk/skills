'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

export function Cart() {
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ['cart'], queryFn: () => fetch('/api/cart').then((r) => r.json()) });
  return <button onClick={() => setOpen(!open)}>{data?.items?.length ?? 0} items</button>;
}
