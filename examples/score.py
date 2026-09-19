import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from common import client
from typesafe_sdk import Score

state = {
    "review": (
        "The API docs are readable and the examples run, but rate limits are "
        "undocumented and error messages are cryptic."
    ),
}

response = client.system_one(
    state=state,
    questions={
        "doc_quality": Score(
            instructions="How would you rate the quality of this API documentation?",
            criteria=[
                "Unusable: key concepts missing, examples fail",
                "Weak: covers basics but gaps make integration painful",
                "Adequate: workable with some guesswork",
                "Good: clear and mostly complete",
                "Excellent: complete, precise, and example-driven",
            ],
        ),
    },
)

print(response.model_dump_json(indent=2))
