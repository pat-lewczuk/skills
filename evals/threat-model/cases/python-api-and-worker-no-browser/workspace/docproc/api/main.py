import os
import uuid

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from docproc.api.auth import current_partner, get_db
from docproc.models import Document, Partner, Result
from docproc.settings import settings
from docproc.worker.tasks import process_document

app = FastAPI(title="docproc")


@app.post("/v1/documents", status_code=202)
async def submit_document(
    file: UploadFile = File(...),
    webhook_url: str = Form(...),
    partner: Partner = Depends(current_partner),
    db=Depends(get_db),
):
    doc_id = str(uuid.uuid4())
    path = os.path.join(settings.upload_dir, f"{doc_id}.pdf")
    with open(path, "wb") as out:
        out.write(await file.read())

    doc = Document(id=doc_id, partner_id=partner.id, filename=file.filename,
                   storage_path=path, webhook_url=webhook_url)
    db.add(doc)
    db.commit()

    process_document.delay(doc_id=doc_id, partner_id=partner.id, path=path,
                           webhook_url=webhook_url)
    return {"id": doc_id, "status": "queued"}


@app.get("/v1/documents/{document_id}")
def get_document(document_id: str, partner: Partner = Depends(current_partner), db=Depends(get_db)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@app.get("/v1/documents/{document_id}/result")
def get_result(document_id: str, partner: Partner = Depends(current_partner), db=Depends(get_db)):
    result = db.get(Result, document_id)
    if result is None:
        raise HTTPException(status_code=404)
    return {"document_id": document_id, "type": result.doc_type, "fields": result.fields}
