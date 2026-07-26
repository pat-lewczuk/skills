select id, customer_id, total_cents from {{ source('shop', 'orders') }}
