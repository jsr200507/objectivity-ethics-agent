"""Assessment data without any dependency on the user interface."""

from dataclasses import dataclass, field


RELATIONSHIP_OPTIONS = (
    "Close personal relationship",
    "Professional relationship only",
    "No relevant relationship",
    "Unknown",
    "Not applicable",
    "Other",
)
INTEREST_OPTIONS = (
    "Commercial interest",
    "Personal financial interest",
    "Both commercial and personal interests",
    "No known interest",
    "Unknown",
    "Not applicable",
    "Other",
)
PRESSURE_OPTIONS = (
    "Reported pressure or threatened consequences",
    "No reported pressure",
    "Unknown",
    "Not applicable",
    "Other",
)
DEFAULT_BASIS = "User account — not independently verified"


@dataclass
class Context:
    role: str = ""
    parties: str = ""
    decision: str = ""
    relationship: str = "Unknown"
    interests: str = "Unknown"
    pressure: str = "Unknown"
    relationship_notes: str = ""
    interests_notes: str = ""
    pressure_notes: str = ""
    basis: str = DEFAULT_BASIS


@dataclass(frozen=True)
class Answer:
    choice: str
    explanation: str = ""


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    options: tuple[str, ...]
    why: str
    topic: str


@dataclass(frozen=True)
class ArchivedAnswer:
    question_id: str
    answer: Answer
    reason: str
    revision: int


@dataclass
class Assessment:
    scenario: str = ""
    context: Context = field(default_factory=Context)
    confirmed: bool = False
    answers: dict[str, Answer] = field(default_factory=dict)
    archive: list[ArchivedAnswer] = field(default_factory=list)
    revision: int = 0
