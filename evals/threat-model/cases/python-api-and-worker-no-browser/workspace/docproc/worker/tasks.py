import httpx
from celery import Celery
from pypdf import PdfReader

from docproc.models import Document, Result, SessionLocal
from docproc.settings import settings
from docproc.worker.llm import classify

celery = Celery("docproc", broker=settings.broker_url)
celery.conf.update(task_serializer="json", accept_content=["json", "pickle"])


@celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=None)
def process_document(self, doc_id: str, partner_id: str, path: str, webhook_url: str):
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    extracted = classify(text)

    with SessionLocal() as db:
        db.merge(Result(document_id=doc_id, doc_type=extracted["type"], fields=extracted.get("fields", {})))
        doc = db.get(Document, doc_id)
        doc.status = "done"
        db.commit()

    httpx.post(webhook_url, json={"document_id": doc_id, "partner_id": partner_id, **extracted},
               follow_redirects=True)
