package auth

import (
	"context"
	"crypto/rsa"
	"errors"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

type ctxKey struct{}

type Customer struct{ ID string }

type Verifier struct{ key *rsa.PublicKey }

func NewVerifier(pem string) (*Verifier, error) {
	key, err := jwt.ParseRSAPublicKeyFromPEM([]byte(pem))
	return &Verifier{key: key}, err
}

func (v *Verifier) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		tok, err := jwt.Parse(raw, func(t *jwt.Token) (any, error) { return v.key, nil },
			jwt.WithValidMethods([]string{"RS256"}))
		if err != nil || !tok.Valid {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		sub, _ := tok.Claims.GetSubject()
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), ctxKey{}, Customer{ID: sub})))
	})
}

func FromContext(ctx context.Context) (Customer, error) {
	c, ok := ctx.Value(ctxKey{}).(Customer)
	if !ok {
		return Customer{}, errors.New("no customer")
	}
	return c, nil
}
