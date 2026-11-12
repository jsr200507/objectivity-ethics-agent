"""Authored sample data, never inferred from the user's narrative."""

from .models import Context


EXAMPLE_SCENARIO = (
    "You are the audit manager of a listed client. The CFO, a close personal "
    "friend from university, has asked you to 'go easy' on an aggressive revenue "
    "recognition judgement, hinting that your firm's tax advisory contract "
    "renewal depends on a smooth audit."
)

EXAMPLE_CONTEXT = Context(
    role="Audit manager of a listed client",
    parties="The CFO, the audit team, and the firm's tax advisory team",
    decision="How to audit and evaluate an aggressive revenue recognition judgment",
    relationship="Close personal relationship",
    interests="Commercial interest",
    pressure="Reported pressure or threatened consequences",
    relationship_notes="The CFO is described as a close personal friend from university.",
    interests_notes="Renewal of the firm's tax advisory contract is mentioned.",
    pressure_notes="The CFO reportedly asked for an easier audit approach and hinted at renewal consequences.",
)
