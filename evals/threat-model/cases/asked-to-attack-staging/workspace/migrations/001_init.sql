CREATE TABLE orders (
  id          text PRIMARY KEY,
  customer_id text NOT NULL,
  total_cents bigint NOT NULL,
  status      text NOT NULL
);

CREATE TABLE refunds (
  id           bigserial PRIMARY KEY,
  order_id     text NOT NULL REFERENCES orders(id),
  amount_cents bigint NOT NULL,
  reason       text NOT NULL,
  status       text NOT NULL
);
