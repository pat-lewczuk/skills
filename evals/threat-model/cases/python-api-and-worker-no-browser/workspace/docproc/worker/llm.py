import json

import anthropic

from docproc.settings import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

PROMPT = """Classify the document below as one of: invoice, credit_note, receipt, other.
If it is an invoice or credit note, extract: supplier_name, supplier_vat_id, invoice_number,
issue_date, due_date, currency, total_amount, iban.
Reply with a single JSON object: {{"type": ..., "fields": {{...}}}}.

Document text:
{text}
"""


def classify(text: str) -> dict:
    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=2048,
        messages=[{"role": "user", "content": PROMPT.format(text=text)}],
    )
    return json.loads(msg.content[0].text)
