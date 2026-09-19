import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Choice, Noul, Score

state = {
    "source_text": (
        "Invoice #4471 issued March 3, 2026 to Beaver Dam Logistics for $12,840.00, net 30."
    ),
}

response = client.system_one(
    state=state,
    questions={
        "invoice_number_is_correct": Noul(
            instructions={
                "field": {
                    "name": "invoice_number",
                    "type": "string",
                    "description": "The identifier printed on the invoice.",
                },
                "extracted_value": "4471",
                "question": "Does `extracted_value` match the `field` as it appears in `source_text`?",
            },
        ),
        "customer_name": Choice(
            instructions={
                "field": {
                    "name": "customer_name",
                    "type": "string",
                    "description": "The organization the invoice was issued to.",
                },
                "question": "Which option is the value of `field` in `source_text`?",
            },
            criteria={
                "Beaver Logistics": None,
                "Dam Logistics": None,
                "Beaver Dam Logistics": None,
            },
        ),
        "payment_terms_days": Score(
            instructions={
                "field": {
                    "name": "payment_terms",
                    "type": "integer",
                    "unit": "days",
                    "description": 'Days allowed for payment, from terms such as "net 30".',
                },
                "question": "How many days does the `field` in `source_text` allow for payment?",
            },
            criteria=["Due on receipt", "Net 10", "Net 30", "Net 60", "Net 90"],
        ),
    },
)

print(response.model_dump_json(indent=2))
