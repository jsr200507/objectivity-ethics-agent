"""Evidence-aware Address reasoning for distinct Objectivity threat instances.

Implementation and effectiveness are separate. All source records remain user
accounts: even supported effectiveness is conditional, not app verification.
"""
from dataclasses import dataclass
import hashlib
import json

from .case_model import CaseAction, CaseState, ReasoningSnapshot, ThreatInstance
from .case_reasoning import ACCEPTABLE, ACTION_REQUIRED

SUPPORTED = "Threat adequately addressed — conditional on the recorded evidence"
POTENTIALLY_REDUCED = "Potentially reduced; effectiveness not established"
UNACCEPTABLE = "Threat remains; action required before proceeding"
INSUFFICIENT = "Insufficient information to establish acceptability"
EFFECTIVE = "Effectiveness Established"

ACTION_CHECK_OPTIONS = {
    "stage": ("Unknown", "Not Taken", "Planned", "Implemented"),
    "independence": ("Yes", "No", "Unknown"),
    "competence": ("Yes", "No", "Unknown"),
    "authority": ("Yes", "No", "Unknown"),
    "eliminated": ("Yes", "No", "Unknown"),
    "coverage": ("All linked circumstances", "Partial", "None", "Unknown"),
    "timing": ("Before reliance", "After reliance", "Unknown"),
    "outcome": ("No continuing influence identified", "Continuing influence remains", "Not examined", "Unknown"),
    "evidence": ("Records described", "Assertion only", "None", "Unknown"),
    "prior_work": ("No prior work was affected", "Affected work was reassessed", "Affected work remains unresolved", "Unknown"),
    "replacement": ("Independent replacement with decision authority", "Replacement subject to same influence", "No replacement", "Unknown"),
    "obligations": ("Completed relevant obligations", "Outstanding obligations", "Unknown"),
    "result": ("A separate protective measure was completed", "No concrete measure yet", "Unknown"),
}
_GOOD = {
    "independence": {"Yes"}, "competence": {"Yes"}, "authority": {"Yes"}, "eliminated": {"Yes"},
    "coverage": {"All linked circumstances"}, "timing": {"Before reliance"},
    "outcome": {"No continuing influence identified"}, "evidence": {"Records described"},
    "prior_work": {"No prior work was affected", "Affected work was reassessed"},
    "replacement": {"Independent replacement with decision authority"},
    "obligations": {"Completed relevant obligations"},
}
_NEGATIVE = {
    "independence": {"No"}, "competence": {"No"}, "authority": {"No"}, "eliminated": {"No"},
    "coverage": {"None"}, "outcome": {"Continuing influence remains"},
    "prior_work": {"Affected work remains unresolved"},
    "replacement": {"Replacement subject to same influence", "No replacement"},
    "obligations": {"Outstanding obligations"},
}
_LABELS = {
    "independence": "reviewer independence from the recorded influences",
    "competence": "competence for the particular professional decision",
    "authority": "authority to require changes",
    "eliminated": "removal of the actual circumstances creating the threat",
    "coverage": "coverage of every linked source of influence",
    "timing": "completion before the affected work or decision was relied upon",
    "outcome": "the outcome and any continuing influence",
    "evidence": "records supporting implementation and outcome",
    "prior_work": "the treatment of any earlier affected work",
    "replacement": "an independent replacement with decision authority",
    "obligations": "relevant responsibilities when declining or ending the activity",
}

@dataclass(frozen=True)
class ActionQuestion:
    id: str
    action_id: str
    key: str
    prompt: str
    options: tuple[str, ...]
    why: str

@dataclass(frozen=True)
class ActionEvaluation:
    action_id: str
    description: str
    kind: str
    claimed_stage: str
    status: str
    covered_threats: tuple[str, ...]
    reasoning: tuple[str, ...]
    gaps: tuple[str, ...]
    effective: bool = False
    failed: bool = False

@dataclass(frozen=True)
class ResidualFinding:
    threat_id: str
    kind: str
    status: str
    reasoning: tuple[str, ...]
    unknowns: tuple[str, ...]
    action_ids: tuple[str, ...]
    third_party: str

@dataclass(frozen=True)
class ActionAssessment:
    outcomes: tuple[ResidualFinding, ...]
    actions: tuple[ActionEvaluation, ...]
    conclusion: str
    third_party: str
    next_steps: tuple[str, ...]
    unknowns: tuple[str, ...]


def _unique(values):
    return tuple(dict.fromkeys(values))


def _reason(case, snapshot):
    if snapshot is not None:
        return snapshot
    from .case_reasoning import reason_case
    return reason_case(case)


def _acceptable_conditions(case, evaluation):
    """Acceptability can rest on existing circumstances, not a required action."""
    return bool(case.reviewed and evaluation is not None
                and evaluation.outcome == ACCEPTABLE and not evaluation.material_gaps)


def _continuing_influence(case, threat_ids):
    return any(set(action.threat_ids) & set(threat_ids) and (
        action.checks.get('outcome') == 'Continuing influence remains'
        or action.checks.get('prior_work') == 'Affected work remains unresolved'
    ) for action in case.actions)


def _active(case):
    return [fact for fact in case.facts if fact.status not in {"withdrawn", "denied"}]


def _actor(case, actor_id):
    return next((actor.label for actor in case.actors if actor.id == actor_id), "a person whose role is unresolved")


def _decision(case, decision_id):
    return next((fact.value.split(";", 1)[0].strip() for fact in _active(case) if fact.predicate == "decision" and fact.decision_id == decision_id and fact.status == "reported"), "the professional decision")


def _target(case, threat):
    return f"the {threat.kind.lower()} concern involving {_actor(case, threat.subject)} in {_decision(case, threat.decision_id)}"


def _has_decision(case, threat):
    return any(f.predicate == "decision" and f.decision_id == threat.decision_id and f.status == "reported" and f.value.strip() not in {"", "Unknown"} for f in case.facts)


def action_basis_signature(case: CaseState, action: CaseAction, snapshot: ReasoningSnapshot | None = None) -> str:
    """Bind coverage to relevant current source facts, not a cached verdict."""
    snapshot = _reason(case, snapshot)
    linked = [threat for threat in snapshot.threats if threat.id in action.threat_ids]
    ids = {id for threat in linked for id in threat.evidence_ids}
    decisions = {threat.decision_id for threat in linked}
    subjects = {threat.subject for threat in linked} | {"user"}
    for fact in _active(case):
        if fact.decision_id in decisions and fact.predicate in {
            "role", "decision", "decision_responsibility", "work_changed", "prior_work_affected",
        }:
            ids.add(fact.id)
        if fact.decision_id in decisions and fact.subject in subjects and fact.predicate in {
            "participation", "relationship_active", "interest_connection",
        }:
            ids.add(fact.id)
    from .case_reasoning import facts_signature
    payload = {
        "source": facts_signature(case, tuple(sorted(ids))),
        "threats": sorted(action.threat_ids),
        "active": sorted(threat.id for threat in linked),
        "actors": sorted((actor.id, actor.label, actor.role) for actor in case.actors if actor.id in subjects),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _prior_work_required(case, action, linked):
    decisions = {threat.decision_id for threat in linked}
    parties = {threat.subject for threat in linked}
    facts = [f for f in _active(case) if f.predicate in {"work_changed", "prior_work_affected"}
             and f.decision_id in decisions and (not f.object_id or f.object_id in parties)]
    if any(f.value == "Yes" and f.status == "reported" for f in facts):
        return True
    # Leaving the decision does not repair earlier work. Review of the complete
    # judgment before reliance can, in contrast, make the historical cause of a
    # change immaterial to its present protection.
    if action.kind in {"remove_from_decision", "decline"} and any(t.kind in {"Intimidation", "Self-review"} for t in linked):
        if any(t.kind == "Self-review" for t in linked):
            return not any(f.predicate == "prior_work_affected" and f.value == "No" and f.status == "reported" for f in facts)
        return not any(f.value == "No" and f.status == "reported" for f in facts)
    return False


def _requirements(case, action, linked):
    requirements = {
        "independent_review": ("independence", "competence", "authority", "coverage", "timing", "outcome", "evidence"),
        "eliminate": ("eliminated", "coverage", "timing", "outcome", "evidence"),
        "remove_from_decision": ("replacement", "coverage", "timing", "outcome", "evidence"),
        "decline": ("coverage", "timing", "obligations", "evidence"),
    }.get(action.kind, ())
    if requirements and _prior_work_required(case, action, linked):
        requirements += ("prior_work",)
    return requirements


def _action_evaluation(case, action, snapshot):
    linked = [threat for threat in snapshot.threats if threat.id in action.threat_ids]
    reasons, gaps = [], []
    covered = tuple(threat.id for threat in linked)
    targets = "; ".join(_target(case, threat) for threat in linked)
    if not linked:
        gaps.append("The action has not been linked to a current threat instance; its coverage is not established.")
    if any(id not in {threat.id for threat in linked} for id in action.threat_ids):
        gaps.append("Part of the action's recorded coverage refers to earlier circumstances and needs reassessment.")
    if action.stage == "Not Taken":
        reasons.append("No relevant action is reported as taken for this record; this is not an implemented safeguard.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Not Taken", covered, tuple(reasons), tuple(gaps))
    if action.kind == "none":
        gaps.append("The record does not establish whether a relevant action was taken; absence is not inferred.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Unknown", covered, tuple(reasons), tuple(gaps))
    if action.stage == "Planned":
        reasons.append(f"{action.description} is planned, requested or in progress; completed implementation is not established.")
        if targets:
            reasons.append("Its intended coverage is " + targets + ".")
        gaps.append("Completion and its effect on the linked sources of influence remain unestablished.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Planned", covered, tuple(reasons), tuple(gaps))
    if action.stage != "Implemented":
        gaps.append("Whether this action was completed is not known from the current account.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Unknown", covered, tuple(reasons), tuple(gaps))
    reasons.append(f"Completion of {action.description} is reported; implementation alone does not establish effectiveness.")
    if action.kind in {"escalate", "disclose", "document"}:
        reasons.append("Communication or documentation can support a response, but does not itself remove the recorded influence on judgment. Any resulting protective measure must be assessed separately.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Implemented", covered, tuple(reasons), tuple(gaps) + ("The concrete resulting protective measure and its outcome need to be established.",))
    if action.kind == "other":
        gaps.append("The mechanism by which this action addresses the linked threat is not established by these rules.")
        return ActionEvaluation(action.id, action.description, action.kind, action.stage, "Implemented", covered, tuple(reasons), tuple(gaps))
    if not case.reviewed:
        gaps.append("Material source details have not yet been reviewed by the user.")
    if not action.reviewed:
        gaps.append("The action's description, stage and coverage have not yet been reviewed by the user.")
    current_signature = action_basis_signature(case, action, snapshot)
    if not action.basis_signature or action.basis_signature != current_signature:
        gaps.append("The action's coverage needs confirmation against the current source facts; earlier coverage is not silently reused.")
    if any(not _has_decision(case, threat) for threat in linked):
        gaps.append("The affected professional decision needs clarification before coverage can be established.")
    failed = False
    for key in _requirements(case, action, linked):
        value = action.checks.get(key)
        if value not in _GOOD[key]:
            if value in _NEGATIVE.get(key, set()):
                failed = True
                reasons.append(f"The account does not support {_LABELS[key]}: {value}.")
            else:
                gaps.append(f"Evidence for {_LABELS[key]} is insufficient" + (f" ({value})." if value else "."))
    # A continuing influence or known unrepaired work contradicts a positive
    # outcome even if an inconsistent collection of other checks is positive.
    if action.checks.get("outcome") == "Continuing influence remains":
        failed = True
        reasons.append("Continuing influence is reported; the action cannot establish protection merely because it was completed.")
    if action.checks.get("evidence") == "Records described" and action.evidence_detail.strip().casefold() in {"", "unknown", "not known", "i don't know"}:
        gaps.append("The supporting records and what they demonstrate have not been described; selecting records alone is not evidence of effectiveness.")
    if action.checks.get("prior_work") == "Affected work remains unresolved":
        failed = True
        reasons.append("Earlier affected work remains unresolved; a future change does not repair that work automatically.")
    if failed:
        gaps.append("The recorded weakness must be resolved or a different effective response is needed.")
    effective = bool(linked) and not gaps and not failed
    if effective:
        reasons.append("The recorded implementation, explicit coverage and action-specific outcome evidence support effectiveness conditionally. This is not independent verification by the application.")
    return ActionEvaluation(action.id, action.description, action.kind, action.stage, EFFECTIVE if effective else "Implemented", covered, _unique(reasons), _unique(gaps), effective, failed)


def action_questions(case: CaseState, snapshot: ReasoningSnapshot | None = None) -> tuple[ActionQuestion, ...]:
    """Ask only the first material missing criterion for each implemented action.

    Explicit Unknown or a known weakness stops that branch rather than eliciting
    a redundant full review checklist. Source records already supply answers.
    """
    snapshot = _reason(case, snapshot)
    result = []
    by_id = {threat.id: threat for threat in snapshot.threats}
    evaluations = {item.threat_id: item for item in snapshot.evaluations}
    if not snapshot.threats:
        return ()  # No safeguard's effectiveness is relied upon for a finding.
    for action in case.actions:
        if action.kind == "none" or action.stage in {"Not Taken", "Planned"}:
            continue
        linked = [by_id[id] for id in action.threat_ids if id in by_id]
        if not linked:
            # Review the action's actual scope before asking how it was done.
            # An unlinked source action cannot yet support a current finding.
            continue
        if linked and all(_acceptable_conditions(case, evaluations.get(threat.id)) for threat in linked) and not _continuing_influence(case, [threat.id for threat in linked]):
            # The ethical conclusion does not rely on this optional measure;
            # asking a full implementation checklist would not change it.
            continue
        if action.stage == "Unknown":
            if "stage" not in action.checks:
                result.append(ActionQuestion(f"{action.id}:stage", action.id, "stage", f"What has actually happened to: {action.description}?", ("Not Taken", "Planned", "Implemented", "Unknown"), "Completion changes which evidence is needed. A request or intention is not completed implementation."))
            continue
        if action.kind in {"escalate", "disclose", "document"}:
            if "result" not in action.checks:
                result.append(ActionQuestion(f"{action.id}:result", action.id, "result", f"Did {action.description} result in a concrete protective measure?", ACTION_CHECK_OPTIONS["result"], "Reporting a concern does not demonstrate that its source has been addressed. Record the resulting measure separately if one exists."))
            continue
        if action.kind == "other":
            continue
        for key in _requirements(case, action, linked):
            if key not in action.checks:
                result.append(ActionQuestion(f"{action.id}:{key}", action.id, key, f"For {action.description}, what is established about {_LABELS[key]}?", ACTION_CHECK_OPTIONS[key], "This fact could change whether the action is effective for " + "; ".join(_target(case, threat) for threat in linked) + ". No external checking or effectiveness is assumed."))
                break
            if action.checks[key] not in _GOOD[key]:
                break
        else:
            if action.checks.get("evidence") == "Records described" and not action.evidence_detail.strip():
                result.append(ActionQuestion(f"{action.id}:evidence_detail", action.id, "evidence_detail", f"Which records support the implementation and outcome of {action.description}, and what do they show?", (), "A bare selection that records exist is not a description of evidence. Describe the relevant records and their connection to the measure; the application does not authenticate them."))
    return tuple(result)


def _recommendation(case, threat, actions):
    """Propose bounded, contextual options without recording or clearing actions."""
    from .case_reasoning import _is_no, _is_yes, _lookup, _unknown
    from .understanding import _authority_kind

    target = _target(case, threat)
    decision = _decision(case, threat.decision_id)
    facts = _active(case)

    def known(predicate, subject="user", object_id=""):
        fact = _lookup(facts, predicate, subject, object_id, threat.decision_id)
        return fact if fact is not None and fact.status == "reported" and not _unknown(fact) else None

    source = next((fact for fact in facts if fact.id in threat.evidence_ids[:1]), None)
    name = _actor(case, threat.subject)
    party = next((actor for actor in case.actors if actor.id == threat.subject), None)
    role = known("role")
    responsibility = known("decision_responsibility")
    authority = {_authority_kind(fact.value) for fact in facts
                 if fact.predicate == "context" and fact.subject == "user"
                 and fact.decision_id == threat.decision_id and fact.status == "reported"}
    remit = f"Your recorded role is {role.value}. " if role else ""
    if ("Final approval authority", True) in authority and ("Final approval authority", False) not in authority:
        remit += "Submit findings and unresolved exceptions to an authorised decision-maker; your reported lack of final approval authority does not remove your professional responsibilities. "
    elif ("Recommendation authority", False) in authority:
        remit += "Submit an evidence-based recommendation; final approval authority is not assumed. "
    elif responsibility and responsibility.value == "I prepare or assess the work":
        remit += "Prepare the analysis for an authorised decision-maker rather than assuming power to change approval arrangements. "

    valuation = "valuation" in decision.casefold()
    review_scope = ("the valuation's assumptions, methods and supporting evidence" if valuation
                    else f"the assumptions and supporting evidence for {decision}")
    alternative = "If suitable internal separation is unavailable, ask an authorised person to arrange competent external review, if accessible; its availability is not assumed."
    supporting = "Document professional disagreements, unresolved exceptions and their resolution before reliance; documentation supports the response but is not sufficient on its own."
    focus = ""
    if threat.kind == "Self-review":
        primary = f"Obtain a fresh assessment of {review_scope} by someone who did not prepare the earlier work and can require changes; this challenges the previous judgment rather than relying on it as its own validation."
        alternative = "Ask an authorised person to reassign the current assessment to someone outside the earlier work. " + alternative
        supporting = "Retain the original analysis and record how material assumptions and any required corrections were independently challenged."
    elif threat.kind == "Advocacy":
        primary = f"Separate the recorded promotional or representative role from {decision}; have someone independent of the position promoted make or review the judgment."
        alternative = "Withdraw from representing that position or ask an authorised person to reassign the objective assessment. " + alternative
        supporting = "Provide the assessor with the underlying evidence, including evidence inconsistent with the position promoted, and record unresolved differences."
    elif threat.kind == "Intimidation":
        influence = known("pressure_authority", threat.subject, "user")
        safety = known("challenge_safety", "user", threat.subject)
        changed = known("work_changed", "user", threat.subject)
        primary = f"Arrange independent challenge of {review_scope} outside the reported pressure from {name}, with someone authorised to require reconsideration; this protects the judgment from the request."
        if safety and safety.value == "I can challenge or escalate without adverse consequences":
            alternative = "Use the reported safe challenge or escalation route to put the evidence and disagreement to an appropriate independent decision-maker; safe access is not an implemented safeguard."
        else:
            alternative = "Identify an appropriate independent channel outside the reported influence; if none is available internally, consider permitted confidential professional advice externally."
            if safety and safety.value == "No practicable route is known":
                focus = "No practicable route is reported as known; this does not establish retaliation or that no route exists. "
            elif safety and safety.value == "Adverse consequences have been reported":
                focus = "Reported adverse consequences make protection from the same source of influence particularly important; they remain unverified. "
            elif safety and safety.value == "I am concerned but no consequence has been stated":
                focus = "Concern is reported without a stated adverse consequence; retaliation is not assumed. "
        if influence and influence.value in {"Directs or can override my work", "Influences performance assessment or career progression", "Both work and career influence"}:
            focus += f"Reported work or career influence makes a route controlled by {name} unsuitable as the sole protection. "
        elif influence and influence.value == "No such authority or influence":
            focus += "No work or career authority is reported; focus on protecting the judgment from the request, including possible future pressure. "
        if _is_yes(changed):
            aspect = known("work_change_details", "user", threat.subject)
            supporting = "Independently reassess the reported affected work" + (f" ({aspect.value})" if aspect else "") + " before reliance, recording corrections and unresolved exceptions; a reported change is not proof of technical error."
        elif _is_no(changed):
            focus += "No work change is reported; protect subsequent work without assuming past impairment. "
    elif threat.kind == "Familiarity":
        primary = f"Arrange review of {review_scope} by someone outside the recorded relationship with {name}; independent challenge reduces loyalty-based influence on this judgment."
        alternative = "Ask an authorised person to reassign the affected work outside that relationship if independent review is impracticable. " + alternative
        supporting = f"Disclose the relevant relationship with {name} to the person arranging the response and document its coverage; disclosure alone does not protect the judgment."
    else:  # The engine has already identified the specific Self-interest source.
        benefit = source.value if source else "the recorded incentive"
        organisation = party and party.kind in {"organisation", "organization"}
        if organisation and benefit == "Organisational financing or loan covenant interest":
            primary = f"Arrange independent review of {review_scope} and separate the professional review and recommendation from financing or covenant negotiations; this limits how {name}'s financing incentive can steer the judgment."
            consequence = known("financing_consequences", source.subject, source.object_id)
            if consequence and consequence.value == "No financing consequence identified":
                focus = "No financing consequence is identified; keep the response proportionate while retaining the recorded organisational interest. "
            elif consequence:
                focus = f"The reported possibility ({consequence.value}) calls for separate assessment of the contractual position; it must not determine the professional judgment or be treated as a verified outcome. "
        elif organisation:
            primary = f"Separate {decision} from decisions about {name}'s reported {benefit}; use a reviewer outside that incentive so commercial considerations do not determine the professional judgment."
            dependence = known("commercial_dependence", source.subject, source.object_id) if source else None
            if dependence and dependence.value == "A major source of income or business":
                focus = "Reported major commercial dependence makes a reviewer exposed to the same income pressure a weak alternative. "
        else:
            owner = "your" if threat.subject == "user" else f"{name}'s"
            primary = f"Ask an authorised person whether {owner} reported incentive ({benefit}) can be removed or decoupled from {decision}; this removes the stake from the judgment rather than merely disclosing it."
            alternative = "If changing the incentive is not feasible, reassign the affected judgment or obtain challenge by someone outside the benefit. " + alternative
            if threat.subject != "user":
                focus = f"The recorded benefit belongs to {name}; your ownership or ability to dispose of it is not assumed. "

    planned = next((action for action in actions if action.status == "Planned"), None)
    if planned:
        if planned.kind == "independent_review":
            focus = f"Obtain completion of {planned.description}; establish the reviewer's independence, competence and authority, its scope, resolution of findings and supporting records. " + focus
        else:
            focus = f"Establish completion and outcome of {planned.description}, with records of which source was controlled and when. " + focus
    elif any(action.failed for action in actions):
        focus = "Resolve the recorded unsuccessful or inadequate response with a different measure and explicit coverage and outcome evidence before relying on the judgment. " + focus
    return f"For {target}. {remit}Primary: {primary} {focus}Alternative: {alternative} Supporting: {supporting}"


def assess_actions(case: CaseState, snapshot: ReasoningSnapshot | None = None) -> ActionAssessment:
    """Recompute action effectiveness and residuals without trusting assertions."""
    snapshot = _reason(case, snapshot)
    action_results = tuple(_action_evaluation(case, action, snapshot) for action in case.actions)
    outcomes, steps, all_gaps = [], [], []
    evaluations = {evaluation.threat_id: evaluation for evaluation in snapshot.evaluations}
    needs_action_history = any(not _acceptable_conditions(case, evaluations.get(threat.id)) for threat in snapshot.threats)
    if not case.actions_reviewed and needs_action_history:
        all_gaps.append("Existing actions have not yet been reviewed; their absence from the account is not evidence that none were taken.")
        steps.append("Establish what has already been done or planned, by whom and for which recorded sources of influence, before choosing additional responses.")
    for threat in snapshot.threats:
        evaluation = evaluations.get(threat.id)
        linked = [action for action in action_results if threat.id in action.covered_threats]
        effective = [action for action in linked if action.effective]
        failed = any(action.failed for action in linked)
        source_actions = [action for action in case.actions if action.id in {item.action_id for item in linked}]
        persistent = any(action.checks.get("outcome") == "Continuing influence remains" or action.checks.get("prior_work") == "Affected work remains unresolved" for action in source_actions)
        reasons, gaps = [], []
        if _acceptable_conditions(case, evaluation) and not persistent:
            status = ACCEPTABLE
            reasons.extend(reason for reason in evaluation.reasoning if reason != threat.mechanism)
            reasons.append(f"No additional safeguard is indicated for {_target(case, threat)} on these recorded circumstances. This finding does not rely on a proposed or unevidenced action.")
            if linked:
                reasons.append("The status and effectiveness of any recorded optional action remain distinct from the existing circumstances supporting this finding.")
            third_party = evaluation.third_party
            steps.append(f"For {_target(case, threat)}, retain the recorded conditions supporting acceptability and reassess if the decision link or circumstances change; no additional safeguard is currently indicated.")
        elif effective and not persistent:
            status = SUPPORTED
            descriptions = "; ".join(action.description for action in effective)
            reasons.append(f"For {_target(case, threat)}, effectiveness is supported by the recorded evidence for {descriptions}.")
            if failed:
                reasons.append("An earlier or additional measure was inadequate; this conditional finding relies on the separately supported effective response, not the inadequate measure.")
            if evaluation and evaluation.material_gaps:
                reasons.append("Earlier uncertainty remains part of the history. The action-specific coverage and outcome evidence address this current source of influence without assuming the missing historical fact.")
            third_party = f"If the account is accurate, a reasonable and informed third party could rely on the described coverage and outcome checks for {_target(case, threat)}; this is conditional and is not an actual independent third-party opinion."
        else:
            action_needed = evaluation is not None and evaluation.outcome == ACTION_REQUIRED
            primary_implemented = any(action.claimed_stage == "Implemented" and action.kind in {"independent_review", "eliminate", "remove_from_decision", "decline"} for action in linked)
            if failed or action_needed and not primary_implemented:
                status = UNACCEPTABLE if action_needed or failed else INSUFFICIENT
            elif primary_implemented:
                status = POTENTIALLY_REDUCED
            else:
                status = INSUFFICIENT
            if not linked:
                gaps.append("No action has established coverage of this particular source of influence.")
            for action in linked:
                gaps.extend(action.gaps)
                reasons.extend(action.reasoning)
            if evaluation:
                gaps.extend(evaluation.material_gaps)
            if persistent and evaluation is not None and evaluation.outcome == ACCEPTABLE:
                gaps.append("Reported continuing influence or unresolved earlier work conflicts with the circumstances supporting the initial acceptable-level finding; reconcile that account before relying on it.")
            if not reasons:
                reasons.append(f"The current account does not establish that {_target(case, threat)} has been addressed.")
            if failed:
                reasons.append("A reported unsuccessful measure or continuing influence is not overridden by another positive assertion.")
            third_party = f"A reasonable and informed third party would still need the missing implementation, coverage or outcome evidence for {_target(case, threat)} before concluding that Objectivity is appropriately protected."
            steps.append(_recommendation(case, threat, linked))
        outcomes.append(ResidualFinding(threat.id, threat.kind, status, _unique(reasons), _unique(gaps), tuple(action.action_id for action in linked), third_party))
        all_gaps.extend(gaps)
    if not snapshot.threats:
        conclusion = "No potential threat is established from the available structured account within these rules. This is not assurance that threats are absent or that Objectivity is protected."
        if snapshot.questions:
            all_gaps.append("Material professional context remains to be clarified.")
            steps.append("Clarify the material professional decision and circumstances selected by the current question, or retain the limitation explicitly.")
    elif all(outcome.status in {SUPPORTED, ACCEPTABLE} for outcome in outcomes) and not all_gaps:
        if all(outcome.status == ACCEPTABLE for outcome in outcomes):
            conclusion = "The recorded circumstances conditionally support that the considered Objectivity threats are at an acceptable level. No additional safeguards are indicated on this account. Reassess if material facts change; this is not independent verification, automatic compliance or a certified ethical opinion."
        else:
            conclusion = "The recorded evidence conditionally supports that the identified Objectivity threats are adequately addressed, through the stated existing circumstances or supported actions. Professional judgment remains required; this is not independent verification, automatic compliance or a certified ethical opinion."
    elif any(outcome.status == UNACCEPTABLE for outcome in outcomes):
        conclusion = "At least one recorded Objectivity threat still requires action before proceeding. Positive measures for other sources do not resolve that remaining concern; consider declining or ending the activity if no effective response is available, subject to relevant obligations."
    else:
        conclusion = "The available evidence does not yet establish that all identified Objectivity threats are at an acceptable level. Resolve the remaining material uncertainties and incomplete responses before relying on a positive conclusion."
    third_party = " ".join(outcome.third_party for outcome in outcomes) if outcomes else "There is not enough case-specific evidence for this application to provide assurance of Objectivity through the reasonable and informed third party test."
    return ActionAssessment(tuple(outcomes), action_results, conclusion, third_party, _unique(steps), _unique(all_gaps))
