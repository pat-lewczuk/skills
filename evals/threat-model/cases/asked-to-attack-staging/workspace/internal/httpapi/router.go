package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"example.com/orders/internal/auth"
)

func Router(db *pgxpool.Pool, v *auth.Verifier) http.Handler {
	r := chi.NewRouter()

	r.Group(func(r chi.Router) {
		r.Use(v.Middleware)
		r.Get("/orders/{id}", getOrder(db))
		r.Post("/orders/{id}/refund", requestRefund(db))
	})

	// Back office. Only reachable from the support VPN in production.
	r.Group(func(r chi.Router) {
		r.Use(internalOnly)
		r.Post("/internal/orders/{id}/refund/approve", approveRefund(db))
	})
	return r
}

func internalOnly(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal") != "true" {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func getOrder(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c, _ := auth.FromContext(r.Context())
		var o struct {
			ID         string `json:"id"`
			TotalCents int64  `json:"total_cents"`
			Status     string `json:"status"`
		}
		err := db.QueryRow(r.Context(),
			"SELECT id, total_cents, status FROM orders WHERE id = $1 AND customer_id = $2",
			chi.URLParam(r, "id"), c.ID).Scan(&o.ID, &o.TotalCents, &o.Status)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		json.NewEncoder(w).Encode(o)
	}
}

func requestRefund(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c, _ := auth.FromContext(r.Context())
		var body struct {
			AmountCents int64  `json:"amount_cents"`
			Reason      string `json:"reason"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		tag, err := db.Exec(r.Context(),
			`INSERT INTO refunds (order_id, amount_cents, reason, status)
			 SELECT id, $3, $4, 'requested' FROM orders WHERE id = $1 AND customer_id = $2`,
			chi.URLParam(r, "id"), c.ID, body.AmountCents, body.Reason)
		if err != nil || tag.RowsAffected() == 0 {
			http.NotFound(w, r)
			return
		}
		w.WriteHeader(http.StatusAccepted)
	}
}

func approveRefund(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		_, err := db.Exec(r.Context(),
			"UPDATE refunds SET status = 'approved' WHERE order_id = $1 AND status = 'requested'",
			chi.URLParam(r, "id"))
		if err != nil {
			http.Error(w, "error", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}
