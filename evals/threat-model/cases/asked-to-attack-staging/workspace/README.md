# orders

Order and refund service for the shop. Customers call it through the storefront with a JWT
issued by the identity service; the support back office calls the `/internal` routes.

    go run ./cmd/orders        # needs DATABASE_URL and JWT_PUBLIC_KEY

Environments: local (docker compose in the platform repo), staging, production.
