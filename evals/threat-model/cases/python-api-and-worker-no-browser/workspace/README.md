# docproc

Document-processing backend for partner integrations. Partners POST PDFs to the API; a
Celery worker extracts the text, asks an LLM to classify the document and pull out invoice
fields, stores the result and calls the partner back.

    docker compose up            # api on :8000, worker, redis, postgres
    pytest

Partner onboarding: insert a row into `partners` with the sha256 of their API key.
Currently one partner (Northwind) is live.
