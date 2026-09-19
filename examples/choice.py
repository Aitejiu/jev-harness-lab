import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Choice

state = {
    "ticket": {
        "subject": "Duplicate charge",
        "message": "I was charged twice for order A-104. Please refund the duplicate.",
    },
    "order": {
        "id": "A-104",
        "charges": [
            {"amount_usd": 49, "status": "captured"},
            {"amount_usd": 49, "status": "captured"},
        ],
    },
    "refund_policy": "Duplicate charges are eligible for an automatic refund within 30 days.",
}

response = client.system_one(
    state=state,
    questions={
        "resolution": Choice(
            instructions="What is the correct resolution for this ticket?",
            criteria={
                "auto_refund": "Policy clearly supports a refund and no human judgment is needed",
                "manual_review": "A refund may be appropriate, but a human must confirm the facts",
                "reject": "Policy does not support a refund",
                "other": "None of the above fits",
            },
        ),
    },
)

print(response.model_dump_json(indent=2))
