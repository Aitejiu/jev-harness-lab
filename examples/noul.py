import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Noul

state = "I know where you work. If you do not approve my refund today, you will regret it."

response = client.system_one(
    state=state,
    questions={
        "explicit_threat": Noul(
            instructions="Does the message contain an explicit threat of physical harm?",
            criteria={
                "true": "States or clearly describes physical harm toward a specific person",
                "false": "No description of physical harm, even if the tone is hostile",
            },
        ),
        "coercive_intimidation": Noul(
            instructions="Does the message use intimidation or implied consequences to pressure the reader?",
            criteria={
                "true": "Implies that refusing the demand will bring harm, retaliation, or negative consequences, including veiled or indirect phrasing",
                "false": "Requests or complains without implying consequences for refusal",
            },
        ),
    },
)

print(response.model_dump_json(indent=2))
