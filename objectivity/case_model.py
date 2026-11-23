"""Provider-neutral source records and deterministic reasoning contracts.

User review never authenticates a statement. Findings and effectiveness are
computed from these records and are not trusted inputs to saved progress.
"""
from dataclasses import dataclass, field
from typing import Protocol

THREAT_KINDS = ("Self-interest", "Self-review", "Advocacy", "Familiarity", "Intimidation")
PREDICATES = (
    "role", "decision", "family_relationship", "close_relationship", "professional_relationship",
    "employment", "interest", "pressure", "self_review", "advocacy", "participation",
    "decision_responsibility", "relationship_active", "interest_connection", "commercial_dependence",
    "work_changed", "prior_work_affected", "claim", "assurance", "context",
)
FACT_STATUSES = ("reported", "unknown", "disputed", "withdrawn", "denied")
SOURCES = ("scenario", "user", "legacy")
ACTION_KINDS = ("independent_review", "eliminate", "remove_from_decision", "escalate", "disclose", "document", "decline", "none", "other")
ACTION_STAGES = ("Unknown", "Not Taken", "Planned", "Implemented")

@dataclass
class CaseActor:
    id: str
    label: str
    role: str = ""
    kind: str = "person"

@dataclass
class CaseFact:
    id: str
    subject: str
    predicate: str
    value: str
    object_id: str = ""
    decision_id: str = "decision"
    source: str = "scenario"
    excerpt: str = ""
    status: str = "reported"
    reviewed: bool = False
    attribution: str = ""
    depends_on: tuple[str, ...] = ()
    revision: int = 0

@dataclass
class CaseAnswer:
    question_id: str
    choice: str
    explanation: str = ""
    fact_id: str = ""
    depends_on: tuple[str, ...] = ()
    basis_signature: str = ""
    prompt: str = ""

@dataclass
class CaseHistory:
    label: str
    value: str
    detail: str = ""
    revision: int = 0
    reason: str = ""

@dataclass
class CaseAction:
    id: str
    description: str
    kind: str = "other"
    stage: str = "Unknown"
    actor_id: str = "user"
    threat_ids: tuple[str, ...] = ()
    source: str = "user"
    excerpt: str = ""
    checks: dict[str, str] = field(default_factory=dict)
    reviewed: bool = False
    basis_signature: str = ""
    revision: int = 0
    evidence_detail: str = ""

@dataclass
class CaseState:
    scenario: str
    actors: list[CaseActor] = field(default_factory=list)
    facts: list[CaseFact] = field(default_factory=list)
    actions: list[CaseAction] = field(default_factory=list)
    answers: dict[str, CaseAnswer] = field(default_factory=dict)
    history: list[CaseHistory] = field(default_factory=list)
    fact_history: list[CaseFact] = field(default_factory=list)
    action_history: list[CaseAction] = field(default_factory=list)
    revision: int = 0
    reviewed: bool = False
    actions_reviewed: bool = False
    limitations: list[str] = field(default_factory=list)
    legacy_records: list[CaseHistory] = field(default_factory=list)

@dataclass
class UnderstandingResult:
    actors: tuple[CaseActor, ...] = ()
    facts: tuple[CaseFact, ...] = ()
    actions: tuple[CaseAction, ...] = ()
    limitations: tuple[str, ...] = ()

class UnderstandingProvider(Protocol):
    def understand(self, scenario: str) -> UnderstandingResult: ...

@dataclass(frozen=True)
class ThreatInstance:
    id: str
    kind: str
    subject: str
    decision_id: str
    mechanism: str
    evidence_ids: tuple[str, ...]
    uncertainty: tuple[str, ...] = ()

@dataclass(frozen=True)
class MaterialQuestion:
    id: str
    prompt: str
    options: tuple[str, ...]
    why: str
    impact: str
    predicate: str
    subject: str = "user"
    object_id: str = ""
    decision_id: str = "decision"
    depends_on: tuple[str, ...] = ()
    threat_ids: tuple[str, ...] = ()
    priority: int = 2  # Ordering of questions, never an ethics/risk score.

@dataclass(frozen=True)
class ThreatEvaluation:
    threat_id: str
    outcome: str
    reasoning: tuple[str, ...]
    material_gaps: tuple[str, ...]
    third_party: str

@dataclass(frozen=True)
class ReasoningSnapshot:
    threats: tuple[ThreatInstance, ...]
    evaluations: tuple[ThreatEvaluation, ...]
    questions: tuple[MaterialQuestion, ...]
    interactions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
