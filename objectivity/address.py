"""Address-stage questions and conditional residual-threat reasoning.

All inputs remain user reports. A reported external check is distinguished from
application verification: this application never independently verifies facts.
"""

from copy import deepcopy
from dataclasses import astuple, dataclass, field

from .evaluation import evaluate
from .models import Answer, Assessment, Question
from .questions import eligible_questions, next_question
from .review import ReviewState, next_review_question, sync_review


UNKNOWN = ("Unknown", "Not applicable", "Other")
REMOVAL = "Remove me from the decision"
REVIEW = "Arrange independent review"
ESCALATE = "Escalate to an appropriate independent person"
DISCLOSE = "Disclose the circumstances"
DOCUMENT = "Document the concern"
DECLINE = "Decline or end the professional activity"
NO_ACTION = "No action identified"
ELIMINATE = {
    "Familiarity": "Eliminate the relevant personal tie or obligation",
    "Intimidation": "Eliminate the source of pressure",
    "Self-interest": "Remove the relevant financial or commercial incentive",
}
ACTION_OPTIONS = {
    kind: (ELIMINATE[kind], REMOVAL, REVIEW, ESCALATE, DISCLOSE, DOCUMENT, DECLINE, NO_ACTION) + UNKNOWN
    for kind in ELIMINATE
}
IMPLEMENTATION_OPTIONS = (
    "Proposed, not yet started", "Requested or in progress", "Implemented according to my account",
    "Attempted but unsuccessful",
) + UNKNOWN
EVIDENCE_OPTIONS = (
    "An independent person checked implementation and outcome against records",
    "Implementation records exist but no independent check", "My assertion only",
) + UNKNOWN
IMPLEMENTED = IMPLEMENTATION_OPTIONS[2]
CHECKED = EVIDENCE_OPTIONS[0]
SUPPORTED = "Conditional support for reduction; professional judgment required"
NOT_ESTABLISHED = "Acceptability not yet established"
REMAINS = "Threat remains; further action required"
ENDED = "Activity reportedly ended; obligations and prior work still require judgment"


@dataclass(frozen=True)
class AddressHistory:
    question_id: str
    prompt: str
    answer: Answer
    reason: str
    revision: int


@dataclass
class AddressState:
    answers: dict[str, Answer] = field(default_factory=dict)
    archive: list[AddressHistory] = field(default_factory=list)
    extra_slots: list[tuple[str, int]] = field(default_factory=list)
    prompts: dict[str, str] = field(default_factory=dict)
    source_signature: tuple | None = None
    next_slot: int = 1


@dataclass(frozen=True)
class ActionSummary:
    description: str
    stage: str
    evidence_status: str
    details: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ResidualThreat:
    kind: str
    status: str
    reasoning: tuple[str, ...]
    unknowns: tuple[str, ...]
    actions: tuple[ActionSummary, ...]


@dataclass(frozen=True)
class AddressAssessment:
    outcomes: tuple[ResidualThreat, ...]
    conclusion: str
    third_party: str
    next_steps: tuple[str, ...]
    unknowns: tuple[str, ...]
    current: bool


def _current_review(assessment: Assessment, review: ReviewState) -> ReviewState:
    current = deepcopy(review)
    sync_review(assessment, current)
    return current


def _signature(assessment: Assessment, review: ReviewState) -> tuple:
    current = _current_review(assessment, review)
    applicable = {q.id for q in eligible_questions(assessment)}
    return (
        assessment.confirmed, assessment.scenario, astuple(assessment.context),
        tuple(sorted((id, answer.choice) for id, answer in assessment.answers.items() if id in applicable)),
        tuple(sorted((id, answer.choice) for id, answer in current.answers.items())),
    )


def address_ready(assessment: Assessment, review: ReviewState) -> bool:
    return (
        assessment.confirmed and next_question(assessment) is None
        and next_review_question(assessment, _current_review(assessment, review)) is None
    )


def _archive(assessment: Assessment, state: AddressState, ids: set[str], reason: str) -> None:
    for id in list(state.answers):
        if id in ids:
            state.archive.append(AddressHistory(
                id, state.prompts.get(id, "Earlier action question"), state.answers.pop(id),
                reason, assessment.revision,
            ))


def sync_address(assessment: Assessment, review: ReviewState, state: AddressState) -> None:
    signature = _signature(assessment, review)
    if signature != state.source_signature:
        _archive(assessment, state, set(state.answers), "The underlying assessment changed; reconfirm the action.")
        state.extra_slots.clear()
        state.prompts.clear()
        state.source_signature = signature


def _slots(assessment: Assessment, review: ReviewState, state: AddressState):
    kinds = [f.kind for f in evaluate(assessment, _current_review(assessment, review).answers).findings]
    return [(kind, 0) for kind in kinds] + [(kind, slot) for kind, slot in state.extra_slots if kind in kinds]


def _questions(assessment: Assessment, kind: str, slot: int, answers: dict[str, Answer]) -> list[Question]:
    prefix = f"{kind}:{slot}:"
    result: list[Question] = []

    def add(name, prompt, options, why):
        result.append(Question(prefix + name, prompt, options, why, f"Address {kind.lower()}"))

    def choice(name):
        return answers.get(prefix + name, Answer("")).choice

    def gate(name, prompt, positive, negative, why):
        add(name, prompt, (positive, negative) + UNKNOWN, why)
        return choice(name) == positive

    add("action", f"How do you propose to address the potential {kind.lower()} threat?", ACTION_OPTIONS[kind],
        "Choose a response to this specific finding. Eliminating circumstances, effective safeguards, "
        "or declining/ending the activity are alternatives; a proposal is not implementation.")
    action = choice("action")
    if action not in ACTION_OPTIONS[kind][:7]:
        return result
    add("implementation", f"What is the implementation status of: {action.lower()}?", IMPLEMENTATION_OPTIONS,
        "A request, intention or discussion must not be treated as a completed action.")
    if choice("implementation") != IMPLEMENTED:
        return result

    if action == REVIEW:
        if not gate("independence", "Is the reviewer independent of the relationship, interest and pressure?",
                    "Reviewer is independent of the relevant influences", "Reviewer is not independent",
                    "A review by someone subject to the same influences may not provide independent challenge."):
            return result
        if not gate("competence", "Does the reviewer have the relevant competence?",
                    "Relevant competence is established", "Competence is not established",
                    "Review effectiveness depends on competence for this particular professional decision."):
            return result
        if not gate("authority", "Can the reviewer require further work or a changed conclusion?",
                    "Can require changes before the decision is final", "Advisory only or no authority",
                    "A nominal review is not equivalent to effective authority to challenge the decision."):
            return result
        if not gate("scope", f"Did the review cover the relevant aspects of the {kind.lower()} threat?",
                    "All relevant aspects of this threat were reviewed", "Only part of this threat was reviewed",
                    "A narrow review cannot automatically address the whole identified threat."):
            return result
    elif action == REMOVAL:
        if not gate("authority", "Has reassignment been authorised by the responsible decision-maker?",
                    "Reassignment is authorised", "Requested but not authorised",
                    "Asking to be removed does not transfer responsibility."):
            return result
        if not gate("scope", "Do you retain any direct or indirect influence over this decision?",
                    "I have no remaining direct or indirect influence", "I retain some influence",
                    "A change of title or reviewer is insufficient if influence over the decision continues."):
            return result
        if not gate("replacement", "Who now holds the responsibility?",
                    "A competent person independent of this threat", "Replacement competence or independence is not established",
                    "Transferring responsibility to someone affected by the same threat may not address it."):
            return result
    elif action == ELIMINATE[kind]:
        positive, negative = {
            "Familiarity": ("The relevant tie or obligation and its influence have ended", "The tie or its influence remains"),
            "Intimidation": ("The pressure source and its ability to affect this decision have been removed", "The pressure or its influence remains"),
            "Self-interest": ("All relevant commercial and personal incentives have been removed", "An incentive remains or only part was removed"),
        }[kind]
        if not gate("scope", f"What circumstances creating the {kind.lower()} threat have actually changed?",
                    positive, negative,
                    "Elimination must cover the actual source of influence, including both commercial and personal interests where relevant; a promise of impartiality does not eliminate circumstances."):
            return result
    elif action == DECLINE:
        if not gate("scope", "Has the professional activity ended without continuing decision influence?",
                    "The activity ended and I have no continuing decision influence", "Responsibilities or influence continue",
                    "An intention to withdraw is not completed withdrawal."):
            return result
        if not gate("obligations", "Have the relevant handover, professional and legal obligations been considered?",
                    "An appropriate responsible person reviewed these obligations", "Obligations remain unresolved",
                    "Ending an activity may leave obligations and affected prior work to address; this app does not determine those obligations."):
            return result
    elif action in {ESCALATE, DISCLOSE}:
        add("recipient", "Who received the concern or disclosure?", (
            "An independent person with authority to require a response",
            "A person affected by the same interest or pressure", "A person without authority",
        ) + UNKNOWN, "Reporting to a recipient is distinct from that recipient implementing an effective response.")
        add("response", "What response has actually occurred?", (
            "Concern acknowledged only", "Concrete action authorised but not implemented",
            "Action implemented and outcome checked", "No response",
        ) + UNKNOWN, "If a concrete measure was implemented, record it as an additional action so its effectiveness can be examined.")
    elif action == DOCUMENT:
        add("documentation", "What has been documented?", (
            "The concern, response and outcome", "The concern only", "No usable record",
        ) + UNKNOWN, "Documentation provides an accountable record; it does not itself remove the source of a threat.")

    if action not in {ESCALATE, DISCLOSE, DOCUMENT}:
        if not gate("timing", "Did the measure take effect before the decision or affected work was relied upon?",
                    "Before the decision or affected work was relied upon", "After finalisation or too late",
                    "A late measure cannot retrospectively protect an already completed judgment."):
            return result
        current_ids = {q.id for q in eligible_questions(assessment)}
        pressure_changed = "pressure_effect" in current_ids and assessment.answers.get("pressure_effect", Answer("")).choice == "Yes"
        if pressure_changed:
            if not gate("prior_work", "Has work reportedly changed under pressure been independently reconsidered?",
                        "Affected work independently reconsidered and corrected where necessary",
                        "Affected work has not been independently reconsidered",
                        "Removal, review or withdrawal does not by itself repair work already influenced by pressure."):
                return result
        if not gate("effect", "What does the recorded outcome indicate about continuing influence?",
                    "No continuing influence identified in the outcome check", "Continuing influence remains",
                    "Implementation alone does not demonstrate effectiveness. The outcome must address this threat, not merely the performance of a procedure."):
            return result
    add("evidence", "What supports the recorded implementation and outcome?", EVIDENCE_OPTIONS,
        "An external independent check is still a user-reported check. The application does not inspect or independently verify records.")
    return result


def eligible_address_questions(assessment: Assessment, review: ReviewState, state: AddressState) -> list[Question]:
    if not address_ready(assessment, review):
        return []
    current = state.source_signature == _signature(assessment, review)
    answers = state.answers if current else {}
    working = state if current else AddressState()
    return [q for kind, slot in _slots(assessment, review, working) for q in _questions(assessment, kind, slot, answers)]


def next_address_question(assessment: Assessment, review: ReviewState, state: AddressState) -> Question | None:
    answers = state.answers if state.source_signature == _signature(assessment, review) else {}
    return next((q for q in eligible_address_questions(assessment, review, state) if q.id not in answers), None)


def save_address_answer(assessment: Assessment, review: ReviewState, state: AddressState,
                        question_id: str, choice: str, explanation: str = "") -> None:
    sync_address(assessment, review, state)
    eligible = {q.id: q for q in eligible_address_questions(assessment, review, state)}
    if question_id not in eligible or choice not in eligible[question_id].options:
        raise ValueError("Choose an available answer to a currently relevant Address question.")
    answer = Answer(choice, explanation.strip())
    previous = state.answers.get(question_id)
    if answer == previous:
        return
    assessment.revision += 1
    if previous:
        prefix = question_id.rsplit(":", 1)[0] + ":"
        ids = {question_id}
        if previous.choice != choice:
            ordered = [q.id for q in eligible.values() if q.id.startswith(prefix)]
            ids.update(ordered[ordered.index(question_id) + 1:])
        _archive(assessment, state, ids, "An earlier action answer changed.")
    state.answers[question_id] = answer
    state.prompts[question_id] = eligible[question_id].prompt
    current_ids = {q.id for q in eligible_address_questions(assessment, review, state)}
    _archive(assessment, state, set(state.answers) - current_ids, "This action question is no longer applicable.")


def add_supporting_action(assessment: Assessment, review: ReviewState, state: AddressState,
                          kind: str, action: str) -> None:
    sync_address(assessment, review, state)
    kinds = {f.kind for f in evaluate(assessment, _current_review(assessment, review).answers).findings}
    if not address_ready(assessment, review) or kind not in kinds or action not in ACTION_OPTIONS.get(kind, ())[:7]:
        raise ValueError("Select a concrete action for a currently relevant threat.")
    if f"{kind}:0:action" not in state.answers:
        raise ValueError("Record the initial response to this threat before adding another action.")
    slot = state.next_slot
    state.next_slot += 1
    state.extra_slots.append((kind, slot))
    assessment.revision += 1
    id = f"{kind}:{slot}:action"
    state.answers[id] = Answer(action)
    state.prompts[id] = f"Additional action for the potential {kind.lower()} threat"


def _unique(values):
    return tuple(dict.fromkeys(values))


def assess_address(assessment: Assessment, review: ReviewState, state: AddressState) -> AddressAssessment:
    """Recompute residual reasoning; stale action records never support reduction."""
    evaluation = evaluate(assessment, _current_review(assessment, review).answers)
    current = state.source_signature == _signature(assessment, review)
    ready = address_ready(assessment, review)
    answers = state.answers if current and ready else {}
    working = state if current and ready else AddressState()
    # A previous unsupported assurance remains a caution, not a permanent factual
    # gap once separate implementation/outcome evidence is later recorded.
    outcomes, global_gaps, steps = [], [
        gap for gap in evaluation.unknowns
        if not gap.startswith("The recorded basis for treating threats as addressed")
    ], []
    if not ready:
        global_gaps.append("Earlier clarification or evaluation questions still need answers.")
    if not current and state.answers:
        global_gaps.append("Earlier action records relate to a changed account and must be reconfirmed.")
    for finding in evaluation.findings:
        summaries, supported, ended, failed, persistent = [], False, False, False, False
        gaps = list(finding.unknowns)
        action_gaps, action_steps = [], []
        reasons = ["The Phase 2 finding remains potential and conditional on the recorded account, not proof of misconduct."]
        for kind, slot in _slots(assessment, review, working):
            if kind != finding.kind:
                continue
            prefix = f"{kind}:{slot}:"
            questions = _questions(assessment, kind, slot, answers)
            applicable = {q.id: q for q in questions}
            get = lambda name: answers.get(prefix + name, Answer("")).choice if prefix + name in applicable else ""
            action, implementation = get("action"), get("implementation")
            if not action:
                continue
            details = tuple(
                (q.prompt, answers[q.id].choice + (f" — User explanation: {answers[q.id].explanation}" if answers[q.id].explanation else ""))
                for q in questions if q.id in answers and q.id != prefix + "action"
            )
            evidence = get("evidence")
            evidence_status = (
                "User reports an external independent check; not verified by the application"
                if evidence == CHECKED else "User-reported account; no independent verification by the application"
            )
            stage = implementation or "No implementation established"
            summaries.append(ActionSummary(action, stage, evidence_status, details))
            if action not in ACTION_OPTIONS[kind][:7]:
                action_gaps.append(f"No concrete response is established for {kind.lower()}.")
                action_steps.append(f"Identify a concrete response to the potential {kind.lower()} threat before relying on an acceptable-level conclusion.")
                continue
            if implementation != IMPLEMENTED:
                if implementation == "Attempted but unsuccessful":
                    failed = True
                    reasons.append(f"{action} was reported unsuccessful; it does not support reducing the threat.")
                    action_steps.append(f"Replace or improve the unsuccessful response '{action.lower()}' and establish its actual outcome.")
                else:
                    action_gaps.append(f"{action}: completed implementation is not established.")
                    action_steps.append(f"Confirm completed implementation of '{action.lower()}' before relying on it; a proposal or request is insufficient.")
                continue
            if action in {ESCALATE, DISCLOSE, DOCUMENT}:
                reasons.append(f"{action} may support an accountable response but does not itself establish elimination or reduction of the threat. Record any resulting concrete measure separately.")
                action_steps.append(f"Record and evaluate the concrete measure resulting from '{action.lower()}'; communication or documentation alone does not establish reduction.")
                if get("recipient") in {"A person affected by the same interest or pressure", "A person without authority"}:
                    reasons.append("The reported recipient is affected by the same influences or lacks authority; this route does not establish effective independent escalation.")
                    action_steps.append("Seek an appropriate recipient independent of the relevant influences and with authority to require a response.")
                if get("response") == "No response":
                    failed = True
                    reasons.append("No response to the reported concern is recorded; escalation has not demonstrated a change to the circumstances.")
                    action_steps.append("Follow up the unanswered concern through an appropriate independent escalation route.")
                continue
            missing = [q.prompt for q in questions if q.id not in answers or answers[q.id].choice in UNKNOWN]
            if missing:
                action_gaps.extend(f"Unresolved: {prompt}" for prompt in missing)
                action_steps.append(f"Clarify the response to: {missing[0]}")
            positive_choices = {
                "independence": "Reviewer is independent of the relevant influences",
                "competence": "Relevant competence is established",
                "authority": "Reassignment is authorised" if action == REMOVAL else "Can require changes before the decision is final",
                "replacement": "A competent person independent of this threat",
                "timing": "Before the decision or affected work was relied upon",
                "prior_work": "Affected work independently reconsidered and corrected where necessary",
                "effect": "No continuing influence identified in the outcome check",
                "obligations": "An appropriate responsible person reviewed these obligations",
            }
            failed_fields = [name for name, value in positive_choices.items() if prefix + name in applicable and get(name) and get(name) not in UNKNOWN and get(name) != value]
            scope_good = {
                REVIEW: "All relevant aspects of this threat were reviewed",
                REMOVAL: "I have no remaining direct or indirect influence",
                DECLINE: "The activity ended and I have no continuing decision influence",
                ELIMINATE[kind]: {
                    "Familiarity": "The relevant tie or obligation and its influence have ended",
                    "Intimidation": "The pressure source and its ability to affect this decision have been removed",
                    "Self-interest": "All relevant commercial and personal incentives have been removed",
                }[kind],
            }.get(action)
            if get("scope") and get("scope") not in UNKNOWN and get("scope") != scope_good:
                failed_fields.append("scope")
            continuing = get("effect") == "Continuing influence remains" or get("scope") in {
                "I retain some influence", "The tie or its influence remains", "The pressure or its influence remains",
                "An incentive remains or only part was removed", "Responsibilities or influence continue",
            }
            persistent |= continuing
            failed |= bool(failed_fields)
            if failed_fields:
                reasons.append(f"{action}: the recorded answers do not establish effective coverage, independence, authority or timely implementation.")
                blocker = failed_fields[0]
                action_steps.append({
                    "independence": "Arrange a reviewer independent of the relevant relationship, financial interests and pressure.",
                    "competence": "Establish that the reviewer has the competence needed for this professional judgment.",
                    "authority": "Obtain effective authority for the reassignment or for the reviewer to require further work and changes before finalisation.",
                    "replacement": "Transfer responsibility to a competent person independent of the identified influences.",
                    "timing": "Obtain appropriate advice on the late measure and reconsider decisions or work already relied upon.",
                    "prior_work": "Arrange independent reconsideration of work changed under pressure and corrections where necessary.",
                    "effect": "Investigate the reported continuing influence and replace or strengthen the ineffective response.",
                    "obligations": "Resolve outstanding withdrawal and handover obligations with an appropriate responsible professional.",
                    "scope": f"Address the remaining source or scope of the {kind.lower()} influence; the recorded partial response is insufficient.",
                }[blocker])
            if evidence != CHECKED:
                action_gaps.append(f"{action}: an external independent check of implementation and outcome is not established.")
                if not failed_fields and not missing:
                    action_steps.append(f"Obtain an appropriate external independent check of the records supporting '{action.lower()}' and its outcome.")
            # A stopped negative branch must never be mistaken for a shorter successful path.
            completed = prefix + "evidence" in applicable and get("evidence") == CHECKED and get("effect") == positive_choices["effect"]
            if completed and not failed_fields and not missing:
                if action == DECLINE:
                    ended = True
                else:
                    supported = True
        if not summaries:
            gaps.append(f"A response to the potential {finding.kind.lower()} threat has not been recorded.")
            action_steps.append(f"Record a specific response to the potential {finding.kind.lower()} threat.")
        if persistent:
            supported, ended = False, False
            gaps.append("Continuing influence is explicitly reported; reconcile any apparently successful measures with that account.")
        # Existing critical gaps are preserved; an action assertion does not resolve them.
        if finding.unknowns:
            supported, ended = False, False
            action_steps.insert(0, f"Clarify the unresolved significance information before relying on the {finding.kind.lower()} response: {finding.unknowns[0]}")
        # An unimplemented or ineffective additional measure need not be relied
        # upon when a separate complete response is supported. Keep its record
        # and its limitations in reasoning without inventing a residual gap.
        if not supported and not ended:
            gaps.extend(action_gaps)
        if supported:
            status = SUPPORTED
            reasons.append("Reported timely implementation, threat-specific coverage, effectiveness and an external independent check provide conditional support for reduction. This app has not verified that account or established compliance.")
        elif ended:
            status = ENDED
            reasons.append("The activity is reported ended with an externally checked outcome. This does not certify withdrawal obligations or repair earlier judgments automatically.")
        elif failed or persistent:
            status = REMAINS
        else:
            status = NOT_ESTABLISHED
        if status not in {SUPPORTED, ENDED}:
            steps.extend(action_steps)
        outcomes.append(ResidualThreat(finding.kind, status, _unique(reasons), _unique(gaps), tuple(summaries)))
        global_gaps.extend(gaps)
    all_supported = bool(outcomes) and all(outcome.status in {SUPPORTED, ENDED} for outcome in outcomes)
    if not evaluation.findings:
        conclusion = "No potential threat is established within the current structured information; this is not an assurance that threats are absent or a declaration of compliance."
    elif all_supported and not global_gaps:
        conclusion = "The recorded account provides conditional support for the stated responses, subject to professional judgment and confirmation of all relevant circumstances. This is not automatic clearance to proceed or a certified ethical opinion."
    else:
        conclusion = "The recorded evidence does not yet establish that all relevant Objectivity threats have been reduced to an acceptable level. Resolve the remaining threats and uncertainties before relying on a conclusion that proceeding is appropriate."
    if not ready:
        steps.insert(0, "Complete or revisit the earlier clarification and significance evaluation.")
    if global_gaps and not steps:
        steps.append("Clarify the missing or conflicting information and obtain appropriate evidence; do not treat uncertainty as an acceptable-level finding.")
    if any(outcome.status == REMAINS for outcome in outcomes):
        steps.append("Escalate ineffective responses to an appropriate independent responsible person; if threats cannot be addressed, consider declining or ending the activity subject to professional and legal obligations.")
    if all_supported:
        steps.append("Confirm the reported checks with the responsible professional and reassess if circumstances or implementation change.")
    if not evaluation.findings:
        residual_reasoning = (
            "No potential threat is established by the current structured information; this is not assurance that threats are absent or a conclusion that compliance is established. "
            if not global_gaps else "The recorded uncertainties prevent a justified conclusion that all relevant threats have been identified or that proceeding is appropriate. "
        )
    else:
        residual_reasoning = (
            "If the reported facts and checks are accurate, they provide conditional support for the responses; human judgment remains necessary. "
            if all_supported and not global_gaps else "The missing information or remaining influence prevents a justified conclusion that all threats are at an acceptable level. "
        )
    third_party = (
        "A reasonable and informed third party would weigh the actual implementation, relevant coverage, "
        "independence, authority, timing and outcome evidence, together with the combined threats. "
        + residual_reasoning
        + "No actual independent third party has reviewed this assessment, and the application has not independently verified any action."
    )
    return AddressAssessment(tuple(outcomes), conclusion, third_party, _unique(steps), _unique(global_gaps), current)
