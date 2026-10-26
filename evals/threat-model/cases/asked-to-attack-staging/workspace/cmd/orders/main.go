package main

import (
	"context"
	"log"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"

	"example.com/orders/internal/auth"
	"example.com/orders/internal/httpapi"
)

func main() {
	pool, err := pgxpool.New(context.Background(), os.Getenv("DATABASE_URL"))
	if err != nil {
		log.Fatal(err)
	}
	verifier, err := auth.NewVerifier(os.Getenv("JWT_PUBLIC_KEY"))
	if err != nil {
		log.Fatal(err)
	}
	log.Fatal(http.ListenAndServe(":8080", httpapi.Router(pool, verifier)))
}
