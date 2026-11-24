"""Bounded Step 2 question planning, separate from ethical and safeguard verdicts.

The existing reasoning snapshot remains the input to Address. This planner adds
decision-relevant depth to the interview without changing those decision rules.
Only recorded typed facts close questions; optional explanations are not parsed.
"""
from dataclasses import dataclass
import hashlib

from .case_model import CaseState, MaterialQuestion, ReasoningSnapshot
from .case_reasoning import (
    ACCEPTABLE, _NO_INVOLVEMENT, _is_yes, _live, _lookup, _question_id, reason_case,
)

MAX_STEP2_QUESTIONS = 7
FINANCING_CONSEQUENCES = (
    "Possible covenant breach", "Renegotiation or lender consent", "Additional security",
    "Changes to borrowing terms", "Several possible consequences",
    "No financing consequence identified", "Other", "Unknown",
)
PRESSURE_AUTHORITY = (
    "Directs or can override my work", "Influences performance assessment or career progression",
    "Both work and career influence", "No such authority or influence", "Other", "Unknown",
)
CHALLENGE_SAFETY = (
    "I can challenge or escalate without adverse consequences",
    "Adverse consequences have been reported",
    "I am concerned but no consequence has been stated",
    "No practicable route is known", "Other", "Unknown",
)
WORK_CHANGE_DETAILS = (
    "Investigation or evidence gathering", "Analysis or professional judgment",
    "Recommendation or conclusion", "Disclosure or escalation", "Several aspects", "Other", "Unknown",
)


@dataclass(frozen=True)
class QuestionPlan:
    questions: tuple[MaterialQuestion, ...]
    deferred: tuple[MaterialQuestion, ...]
    answered_count: int

    @property
    def limit_reached(self):
        return bool(self.deferred) and not self.questions


def _answer_id(question):
    return 'answer-' + hashlib.sha256(question.id.encode()).hexdigest()[:16]


def _asked_ids(case):
    # Superseded answers continue to count. Revising the same scoped question
    # reuses its slot; source edits cannot reset the seven-question budget.
    return {fact.id for fact in (*case.facts, *case.fact_history)
            if fact.source == 'user' and fact.id.startswith('answer-')}


def plan_questions(case: CaseState, snapshot: ReasoningSnapshot | None = None) -> QuestionPlan:
    """Group each threat's Identify then Evaluate questions, with a shared cap."""
    snapshot = snapshot if snapshot is not None else reason_case(case)
    facts = _live(case)
    pending = {q.id: q for q in snapshot.questions}
    evaluations = {item.threat_id: item for item in snapshot.evaluations}
    actors = {actor.id: actor for actor in case.actors}

    def known(predicate, subject, obj, decision):
        return _lookup(facts, predicate, subject, obj, decision)

    def add(threat, predicate, subject, obj, prompt, options, why, impact, phase, dependencies=(), priority=2):
        if known(predicate, subject, obj, threat.decision_id) is not None:
            return
        qid = _question_id(predicate, subject, obj, threat.decision_id)
        ids = (*threat.evidence_ids, *(f.id for f in facts
                 if f.predicate in {'decision', 'decision_responsibility'} and f.decision_id == threat.decision_id),
               *(f.id for f in dependencies if f is not None))
        prior = pending.get(qid)
        if prior:
            ids = (*prior.depends_on, *ids)
        pending[qid] = MaterialQuestion(qid, prompt, options, why, impact, predicate,
            subject, obj, threat.decision_id, tuple(dict.fromkeys(ids)),
            tuple(dict.fromkeys((*(prior.threat_ids if prior else ()), threat.id))), priority, phase)

    for threat in snapshot.threats:
        evaluation = evaluations.get(threat.id)
        responsibility = known('decision_responsibility', 'user', '', threat.decision_id)
        if evaluation and evaluation.outcome == ACCEPTABLE:
            continue
        if responsibility and responsibility.status == 'reported' and responsibility.value in _NO_INVOLVEMENT:
            continue  # Existing earlier-work clarification remains in the snapshot.
        source = next((f for f in facts if f.id == threat.evidence_ids[0]), None)
        if source is None:
            continue
        party = actors.get(threat.subject)
        name = party.label if party else 'the relevant party'
        if name.startswith('Your '):
            name = 'your ' + name[5:]
        elif party and party.role and party.role.casefold() == name.casefold():
            name = 'the ' + name
        if threat.kind == 'Self-interest' and party and party.kind in {'organisation', 'organization'} and source.value == 'Organisational financing or loan covenant interest':
            connection = known('interest_connection', source.subject, source.object_id, threat.decision_id)
            decision = known('decision', 'user', '', threat.decision_id)
            outcome = 'a lower valuation' if decision and 'valuation' in decision.value.casefold() else 'a less favourable outcome of this decision'
            add(threat, 'financing_consequences', source.subject, source.object_id,
                f"What practical consequences could {outcome} have for {name}'s financing or loan covenant?",
                FINANCING_CONSEQUENCES,
                'The financing interest is reported, but its practical consequences have not been established.',
                'A possible breach, renegotiation, extra security or different borrowing terms can strengthen the incentive to favour an outcome. These remain possibilities, not established results.',
                'evaluate', (connection,))
        elif threat.kind == 'Intimidation':
            authority = known('pressure_authority', source.subject, 'user', threat.decision_id)
            add(threat, 'pressure_authority', source.subject, 'user',
                f'What authority or influence does {name} have over your work, performance assessment or career progression?',
                PRESSURE_AUTHORITY,
                'A job title or reported request alone does not establish power over your work or career.',
                'Reported control or career influence may make the request harder to resist. An absence of such authority narrows that factor without proving the pressure harmless.',
                'identify', priority=1)
            add(threat, 'challenge_safety', 'user', source.subject,
                f'Could you challenge the request from {name}, or escalate your concern, without adverse consequences?',
                CHALLENGE_SAFETY,
                'Authority and a safe opportunity to challenge are different circumstances; neither is assumed from the other.',
                'A reported consequence or lack of a practicable route can heighten concern. A stated ability to challenge is not evidence that an effective safeguard has been implemented.',
                'evaluate', (authority,), priority=1)
            changed = known('work_changed', 'user', source.subject, threat.decision_id)
            if _is_yes(changed):
                add(threat, 'work_change_details', 'user', source.subject,
                    f'Which aspects of your work or recommendation changed in response to {name}?',
                    WORK_CHANGE_DETAILS,
                    'A change is reported, but the affected work has not been specified.',
                    'The affected aspect helps locate work that may need review or correction. A change alone does not prove a technical error or misconduct.',
                    'evaluate', (changed,), priority=0)

    positions = {threat.id: i for i, threat in enumerate(snapshot.threats)}
    def order(q):
        group = min((positions[id] for id in q.threat_ids if id in positions), default=-1)
        depth = {'challenge_safety': 0, 'work_changed': 1, 'work_change_details': 2}.get(q.predicate, q.priority)
        return group, q.phase == 'evaluate', depth, q.id
    ordered = sorted(pending.values(), key=order)
    asked = _asked_ids(case)
    slots = max(0, MAX_STEP2_QUESTIONS - len(asked))
    selected, deferred = [], []
    for q in ordered:
        if _answer_id(q) in asked:
            selected.append(q)  # Explicit source revisions may reopen this same slot.
        elif slots:
            selected.append(q)
            slots -= 1
        else:
            deferred.append(q)
    return QuestionPlan(tuple(selected), tuple(deferred), len(asked))
