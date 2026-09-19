import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Choice, Noul

messages = [
    "I know where you work. If you do not approve my refund today, you will regret it.",
    "You are useless and this company is a scam. I want my money back.",
    "I am coming to your office tomorrow to get this sorted, one way or another.",
    "Please refund order A-104 or I will dispute the charge with my bank.",
    "Hi, my payout has been failing for 3 days, can you check?",
]

THREAT_ESCALATE = 0.9
THREAT_REVIEW = 0.35
CONFIDENCE_FLOOR = 0.6

for message in messages:
    response = client.system_one(
        state=message,
        questions={
            "intimidation": Noul(
                instructions="Does the message use pressure or implied consequences to push the reader toward a demand?",
                criteria={
                    "true": "Implies that refusing the demand will bring harm, retaliation, or negative consequences, including veiled or indirect phrasing",
                    "false": "Requests or complains without implying consequences for refusal",
                },
            ),
            "legitimate_escalation": Noul(
                instructions="Is the pressure based on a legitimate consumer right or escalation channel?",
                criteria={
                    "true": "Invokes a legitimate channel or right: bank dispute, chargeback, regulator, or legal process",
                    "false": "Uses threats, harassment, or implied harm outside legitimate channels",
                },
            ),
            "intent": Choice(
                instructions="What does the sender want?",
                criteria={
                    "refund": "A refund, chargeback, or money back",
                    "complaint": "To vent or complain without a specific request",
                    "question": "To get information or help with an issue",
                    "other": "None of the above",
                },
            ),
        },
    )

    intimidation = response.answers["intimidation"].noul
    legitimate = response.answers["legitimate_escalation"].noul
    intent = response.answers["intent"].choice
    confidence = response.answers["intent"].confidence

    if intimidation >= THREAT_ESCALATE and legitimate < 0.5:
        decision = "escalate_security"
    elif intimidation >= THREAT_REVIEW and legitimate < 0.5:
        decision = "human_review (threat)"
    elif intimidation >= THREAT_REVIEW and legitimate >= 0.5:
        decision = "priority_billing"
    elif confidence < CONFIDENCE_FLOOR:
        decision = "human_review (low confidence)"
    else:
        decision = f"auto:{intent}"

    print(
        f"threat={intimidation:.2f}  legit={legitimate:.2f}  "
        f"intent={intent:<9} conf={confidence:.2f}  ->  {decision}"
    )
    print(f'   "{message}"')
