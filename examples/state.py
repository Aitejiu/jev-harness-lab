import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Choice, Noul

state = {
    "ticket": {
        "subject": "Duplicate charge",
        "messages": [
            {
                "from": "customer",
                "text": "I was charged twice for order A-104. Please refund the duplicate.",
            },
            {"from": "support", "text": "We are checking the charges and will follow up."},
            {
                "from": "customer",
                "text": "Still waiting. If this is not fixed by Friday I want a full refund and compensation.",
            },
        ],
    },
    "order": {
        "id": "A-104",
        "charges": [
            {"amount_usd": 49, "status": "captured"},
            {"amount_usd": 49, "status": "captured"},
        ],
        "promotions_applied": [],
    },
    "refund_policy": "Duplicate charges are eligible for a full refund within 30 days.",
}

response = client.system_one(
    state=state,
    questions={
        "refund_requested": Noul(
            instructions="Does the customer request a refund in `ticket.messages`?",
            criteria={
                "true": "Any message asks for money back or a refund, including implied requests",
                "false": "No request for money back appears in the conversation",
            },
        ),
        "duplicate_confirmed": Noul(
            instructions={
                "question": "Do `order.charges` show a duplicate charge for the same amount?",
                "focus": 'Compare the captured charges; ignore statuses other than "captured".',
            },
            criteria={
                "true": {
                    "what": "Two or more captured charges of the same amount for this order",
                    "examples": ["Two captured charges of $49"],
                },
                "false": {
                    "what": "No repeated captured charge of the same amount",
                    "examples": ["One captured charge of $49", "Two charges of different amounts"],
                },
            },
        ),
        "policy_supports_refund": Noul(
            instructions="Does `refund_policy` support the refund requested in `ticket.messages`?",
            criteria={
                "true": "The policy covers the situation described by the customer",
                "false": "The policy does not cover the situation, or required conditions are not met",
            },
        ),
        "recommended_action": Choice(
            instructions="What should support do next?",
            criteria={
                "auto_refund": "Evidence and policy clearly support an immediate refund",
                "request_info": "Needed facts are missing from the state",
                "manual_review": "Facts are present but a human must decide",
                "reject": "Policy clearly does not support a refund",
            },
        ),
    },
)

print(response.model_dump_json(indent=2))
