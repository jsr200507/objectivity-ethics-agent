"""Evidence-linked Objectivity identification and material-gap evaluation.

These authored rules reason over provider-neutral facts, not an unrestricted
narrative. Reported facts support provisional findings before user review. They
never establish misconduct, independent verification or safeguard effectiveness.
"""

import hashlib
import json

from .case_model import (
    CaseFact, CaseState, MaterialQuestion, ReasoningSnapshot, ThreatEvaluation,
    ThreatInstance,
)

ACTION_REQUIRED = "Action needed before proceeding"
NOT_ESTABLISHED = "Acceptability not established"
NARROWED = "No direct influence established on the recorded account"
YES_NO = ("Yes", "No", "Unknown")
RESPONSIBILITY = (
    "I make or recommend the decision", "I supervise or review the work",
    "I have no involvement in this decision", "I prepare or assess the work", "Unknown",
)
DEPENDENCE = (
    "A major source of income or business", "One of several sources",
    "No known financial dependence", "Unknown",
)
_INVOLVED = set(RESPONSIBILITY[:2]) | {"I prepare or assess the work", "Yes"}
_NO_INVOLVEMENT = {RESPONSIBILITY[2], "I have no involvement", "No"}
_NEGATIVE = {"no", "none", "no known interest", "no reported pressure", "not applicable", "not involved"}
_UNKNOWN = {"unknown", "other", "not known", "not established", "uncertain", ""}
_SCOPE = "decision"


def facts_signature(case: CaseState, ids) -> str:
    """Content-only dependency token; review clicks are not new circumstances."""
    wanted = tuple(sorted(set(ids)))
    by_id = {fact.id: fact for fact in case.facts}
    payload = []
    for id in wanted:
        fact = by_id.get(id)
        if fact is None:
            payload.append({"id": id, "missing": True})
        else:
            payload.append({
                "id": fact.id, "subject": fact.subject, "predicate": fact.predicate,
                "value": fact.value, "object_id": fact.object_id,
                "decision_id": fact.decision_id, "source": fact.source,
                "excerpt": fact.excerpt, "status": fact.status,
                "attribution": fact.attribution, "depends_on": fact.depends_on,
            })
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _live(case):
    return [fact for fact in case.facts if fact.status not in {"withdrawn", "denied"}]


def _affirmed(fact):
    return fact.status == "reported" and fact.value.strip().casefold() not in _NEGATIVE | _UNKNOWN


def _unique(items):
    return tuple(dict.fromkeys(items))


def _lookup(facts, predicate, subject="user", object_id="", decision_id=_SCOPE):
    """Resolve an exact fact scope; an unrelated actor never supplies an answer."""
    found = [fact for fact in facts if fact.predicate == predicate and fact.subject == subject
             and fact.decision_id == decision_id and fact.object_id == object_id]
    if not found and object_id:
        found = [fact for fact in facts if fact.predicate == predicate and fact.subject == subject
                 and fact.decision_id == decision_id and not fact.object_id]
    if not found:
        return None
    # A later explicit structured account can supersede an older source suggestion;
    # the source ledger/history still records the distinction.
    return sorted(found, key=lambda f: (f.revision, f.source == "user"))[-1]


def _unknown(fact):
    return fact is None or fact.status in {"unknown", "disputed"} or fact.value.strip().casefold() in _UNKNOWN


def _is_yes(fact):
    return fact is not None and fact.status == "reported" and fact.value in {"Yes", "Participated", "Involved"}


def _is_no(fact):
    return fact is not None and fact.status == "reported" and fact.value in {"No", "Not involved", "No involvement"}


def _label(case, actor_id):
    actor = next((actor for actor in case.actors if actor.id == actor_id), None)
    if actor:
        return actor.label
    return "you" if actor_id == "user" else "the relevant party"


def _possessive(case, actor_id):
    label = _label(case, actor_id)
    if label.startswith('Your '):
        label = 'your ' + label[5:]
    return "your" if actor_id == "user" else label + ("'" if label.endswith("s") else "'s")


def _decision(facts, decision_id):
    fact = next((f for f in facts if f.predicate == "decision" and f.decision_id == decision_id and _affirmed(f)), None)
    return fact.value.split(";", 1)[0].strip() if fact else "the professional decision"


def _threat_id(kind, fact):
    # Stable if a fact's recorded value is corrected; its source identity remains.
    return "threat-" + hashlib.sha256((kind + "|" + fact.id).encode()).hexdigest()[:16]


def _question_id(predicate, subject, object_id, decision_id):
    scope = "|".join((predicate, subject, object_id, decision_id))
    return "question-" + hashlib.sha256(scope.encode()).hexdigest()[:16]


def reason_case(case: CaseState) -> ReasoningSnapshot:
    """Identify supported sources now; ask only unresolved material questions.

    The case and its source records are never mutated. Explicit Unknown facts
    close their scoped question while remaining an evaluation limitation.
    """
    facts = _live(case)
    threats = []
    evaluations = []
    questions = {}
    limitations = list(case.limitations)
    missing_decision = _lookup(facts, "decision")
    if missing_decision is None:
        q = MaterialQuestion(
            _question_id("decision", "user", "", _SCOPE),
            "What professional decision or activity could be affected in this situation?", (),
            "The professional judgment at issue is not established by the recorded facts.",
            "The answer determines which reported circumstances can affect Objectivity; no threat is inferred from a vague concern alone.",
            "decision", priority=0,
        )
        questions[q.id] = q
    elif _unknown(missing_decision):
        limitations.append("The professional decision is explicitly unknown; the scope of a case-specific assessment remains limited.")

    def actor(actor_id):
        return _label(case, actor_id)

    def known(predicate, subject="user", object_id="", decision_id=_SCOPE):
        return _lookup(facts, predicate, subject, object_id, decision_id)

    def add_question(threat, predicate, subject, object_id, prompt, why, impact, *, options=YES_NO, priority=2):
        if known(predicate, subject, object_id, threat.decision_id) is not None:
            return
        responsibility = known('decision_responsibility', 'user', '', threat.decision_id)
        if predicate in {'participation','relationship_active','interest_connection'} and responsibility is not None and responsibility.status == 'reported' and responsibility.value in _NO_INVOLVEMENT:
            return  # No current involvement makes this depth immaterial; limits remain explicit.
        qid = _question_id(predicate, subject, object_id, threat.decision_id)
        dependency_ids = (
            [f.id for f in facts if f.predicate == "role" and f.subject == "user"]
            if predicate == "decision_responsibility" else list(threat.evidence_ids)
        )
        dependency_ids.extend(f.id for f in facts if f.predicate == "decision" and f.decision_id == threat.decision_id)
        if qid in questions:
            old = questions[qid]
            questions[qid] = MaterialQuestion(
                old.id, old.prompt, old.options, old.why, old.impact, old.predicate,
                old.subject, old.object_id, old.decision_id,
                _unique((*old.depends_on, *dependency_ids)),
                _unique((*old.threat_ids, threat.id)), min(old.priority, priority),
            )
        else:
            questions[qid] = MaterialQuestion(
                qid, prompt, options, why, impact, predicate, subject, object_id,
                threat.decision_id, _unique(dependency_ids), (threat.id,), priority,
            )

    def append(kind, source, mechanism, extras=(), uncertainty=(), subject=None):
        ids = _unique((source.id, *(fact.id for fact in extras if fact is not None)))
        threat = ThreatInstance(_threat_id(kind, source), kind, subject or source.subject,
                                source.decision_id, mechanism, ids, tuple(uncertainty))
        threats.append(threat)
        return threat

    # Distinct financial sources remain distinct, including within one category.
    for fact in facts:
        if fact.predicate != "interest" or not _affirmed(fact):
            continue
        link = known("interest_connection", fact.subject, fact.object_id, fact.decision_id)
        if _is_no(link):
            limitations.append(f"The recorded interest of {actor(fact.subject)} was stated not to connect to this decision; it is not treated as an established Objectivity threat here.")
            continue
        if fact.subject == "user":
            mechanism = f"{_possessive(case, fact.subject).capitalize()} reported {fact.value} could favour an outcome of {_decision(facts, fact.decision_id)} that benefits you financially."
        else:
            relation = next((r for r in facts if r.predicate in {"family_relationship", "close_relationship"} and r.object_id == fact.subject and _affirmed(r)), None)
            if relation:
                mechanism = f"The reported {fact.value} belongs to {actor(fact.subject)}. That connection could create loyalty or economic influence over {_decision(facts, fact.decision_id)}; it does not establish your ownership or a personal financial benefit."
            else:
                mechanism = f"The reported {fact.value} belongs to {actor(fact.subject)} and could create an incentive to steer {_decision(facts, fact.decision_id)}. This is that party's interest, not an assumed financial benefit for you."
        relation = next((r for r in facts if r.predicate in {"family_relationship", "close_relationship"} and r.object_id == fact.subject and _affirmed(r)), None)
        append("Self-interest", fact, mechanism, (link, relation), ("The incentive's effect on the decision requires evaluation.",) if _unknown(link) else ())

    # A relationship and the relative's employment are different facts. Neither
    # employment nor family status proves participation in the professional work.
    for fact in facts:
        if fact.predicate not in {"family_relationship", "close_relationship"} or not _affirmed(fact):
            continue
        related = fact.object_id
        activity = known("relationship_active", fact.subject, related, fact.decision_id)
        if _is_no(activity):
            limitations.append(f"No continuing relevant tie with {actor(related)} is reported; a historical relationship is not treated as an active familiarity source.")
            continue
        employment = next((e for e in facts if e.predicate == "employment" and e.subject == related and e.decision_id == fact.decision_id and _affirmed(e)), None)
        if employment:
            org = actor(employment.object_id)
            participation = known("participation", related, employment.object_id, fact.decision_id)
            mechanism = (
                f"The family/personal connection with {actor(related)}, who is reported to work for {org}, "
                f"could affect how critically you consider {_decision(facts, fact.decision_id)}. "
                f"Employment does not establish that {actor(related)} prepared or influenced the relevant work."
            )
            uncertain = (f"Whether {actor(related)} participated in or could influence that work is not established.",) if _unknown(participation) else ()
            append("Familiarity", fact, mechanism, (employment, participation, activity), uncertain, subject=related)
        else:
            label = "close personal relationship" if fact.predicate == "close_relationship" else "family or personal relationship"
            mechanism = f"The reported {label} with {actor(related)} could make it harder to challenge their interests or work when exercising judgment about {_decision(facts, fact.decision_id)}. It does not prove bias or establish personal closeness beyond what was reported."
            append("Familiarity", fact, mechanism, (activity,), subject=related)

    for fact in facts:
        if fact.predicate == "pressure" and _affirmed(fact):
            append("Intimidation", fact,
                f"The reported influence from {actor(fact.subject)}—{fact.value}—could deter an objective judgment about {_decision(facts, fact.decision_id)}. A reported request or consequence is not proof of coercion, intent or a completed change to work.")
        elif fact.predicate == "self_review" and _affirmed(fact):
            append("Self-review", fact,
                f"The recorded connection to earlier work ({fact.value}) could make {actor(fact.subject)} less willing to identify deficiencies when considering {_decision(facts, fact.decision_id)}. Preparing work does not by itself prove that the later review is biased.")
        elif fact.predicate == "advocacy" and _affirmed(fact):
            append("Advocacy", fact,
                f"The reported promotion or representation of a position ({fact.value}) could make it harder for {actor(fact.subject)} to assess that position objectively in {_decision(facts, fact.decision_id)}. Routine communication is not automatically advocacy.")

    for threat in threats:
        source = next(f for f in facts if f.id == threat.evidence_ids[0])
        decision = _decision(facts, threat.decision_id)
        responsibility = known("decision_responsibility", "user", "", threat.decision_id)
        # Explicit self-review/advocacy facts already describe the current role.
        implied_involvement = threat.kind in {"Self-review", "Advocacy"} and source.subject == "user"
        involved = responsibility is not None and responsibility.status == "reported" and responsibility.value in _INVOLVED or implied_involvement
        no_involvement = responsibility is not None and responsibility.status == "reported" and responsibility.value in _NO_INVOLVEMENT
        gaps = []
        reasons = [threat.mechanism]
        outcome = NOT_ESTABLISHED
        if responsibility is None and not implied_involvement:
            add_question(threat, "decision_responsibility", "user", "",
                f"What involvement do you have in {decision}?",
                "Your responsibility for this decision has not been recorded explicitly.",
                "Making, recommending or reviewing the decision can make the reported influence material; no involvement can narrow its relevance.",
                options=RESPONSIBILITY, priority=0)
        if not involved and not no_involvement:
            gaps.append("Your decision-making or review responsibility is not established.")
        elif no_involvement:
            reasons.append("You report no involvement in this decision; that narrows the current effect on your own professional judgment but does not validate the work or settle other obligations.")
            outcome = NARROWED
        else:
            reasons.append("The recorded professional involvement connects this source of influence to your judgment.")

        if threat.kind == "Familiarity":
            relative = source.object_id
            employment = next((f for f in facts if f.id in threat.evidence_ids and f.predicate == "employment"), None)
            if employment:
                participation = known("participation", relative, employment.object_id, threat.decision_id)
                add_question(threat, "participation", relative, employment.object_id,
                    f"Did {actor(relative)} participate in, supervise or have authority to influence the relevant work from {actor(employment.object_id)}?",
                    "The reported employment link does not establish participation in this particular work.",
                    "Participation or authority strengthens the decision link; no participation narrows it. Unknown leaves a material limit without assuming involvement.",priority=1)
                if _unknown(participation):
                    gaps.append(f"{actor(relative)}'s participation or ability to influence the work remains unknown.")
                elif _is_yes(participation):
                    reasons.append(f"{actor(relative)} is reported to have participated in or influenced the relevant work; this makes the family/employment connection directly relevant.")
                    if involved: outcome = ACTION_REQUIRED
                elif _is_no(participation):
                    reasons.append(f"{actor(relative)} is reported not to have participated in or controlled this work. Employment alone is not treated as evidence that they did.")
            else:
                activity = known("relationship_active", source.subject, relative, threat.decision_id)
                if source.predicate == "family_relationship" and activity is None:
                    add_question(threat, "relationship_active", source.subject, relative,
                        f"Are there current personal ties or obligations with {actor(relative)} that could affect this decision?",
                        "A family description alone does not establish the current nature of the relationship.",
                        "Current ties or obligations can strengthen the influence mechanism; no relevant current tie narrows it.",priority=2)
                if source.predicate == "family_relationship" and _unknown(activity):
                    gaps.append(f"The current relevance of personal ties with {actor(relative)} remains uncertain.")
                elif _is_yes(activity) or source.predicate == "close_relationship":
                    reasons.append("An active or explicitly close personal connection is reported; actual bias is not inferred.")
                    if involved: outcome = ACTION_REQUIRED
        elif threat.kind == "Self-interest":
            connection = known("interest_connection", source.subject, source.object_id, threat.decision_id)
            add_question(threat, "interest_connection", source.subject, source.object_id,
                f"Could this decision affect {_possessive(case, source.subject)} reported {source.value[:1].lower() + source.value[1:]}?",
                "The beneficiary is recorded, but the effect of this decision on that interest is not yet established.",
                "A connection supports the incentive mechanism; an explicitly unrelated interest should not be treated as a threat from this decision.",priority=1)
            if _unknown(connection):
                gaps.append(f"The connection between the decision and {actor(source.subject)}'s interest remains unresolved.")
            elif _is_yes(connection):
                reasons.append(f"The recorded outcome link connects {actor(source.subject)}'s interest to this decision, without changing who receives the benefit.")
                if involved: outcome = ACTION_REQUIRED
            party = next((actor for actor in case.actors if actor.id == source.subject), None)
            commercial_kind = source.value in {"Firm contract renewal/client retention", "Firm contract renewal or client retention", "Contract renewal or client retention", "Fees or profitability", "Firm fee income", "Organisational fee income"}
            if party is not None and party.kind == "organisation" and commercial_kind and not no_involvement:
                dependence = known("commercial_dependence", source.subject, source.object_id, threat.decision_id)
                response_pending = any(a.stage == "Implemented" and a.kind in {"eliminate", "remove_from_decision", "decline"} and threat.id in a.threat_ids for a in case.actions)
                if not response_pending:
                    add_question(threat, "commercial_dependence", source.subject, source.object_id,
                        f"What is known about {actor(source.subject)}'s dependence on this income or relationship?",
                        "The scale of commercial dependence is not recorded and could affect the response needed.",
                        "Material dependence may make ordinary review insufficient; limited or unknown dependence changes the qualification, not the existence of the reported incentive.",options=DEPENDENCE,priority=2)
                    if _unknown(dependence): gaps.append("The commercial dependence affecting the appropriate response is not established.")
        elif threat.kind == "Intimidation":
            changed = known("work_changed", "user", source.subject, threat.decision_id)
            add_question(threat, "work_changed", "user", source.subject,
                f"Has any work or recommendation already changed in response to the reported influence from {actor(source.subject)}?",
                "The scenario records influence, but does not establish whether professional work has already been affected.",
                "A reported change may require correction of prior work as well as protection against future influence; No does not remove possible future influence.",priority=1)
            if _unknown(changed): gaps.append("Whether work has already changed in response to this influence is unresolved.")
            elif _is_yes(changed):
                reasons.append("A change to work is reported. The affected judgment and any correction need attention; this does not establish technical error or misconduct.")
                outcome = ACTION_REQUIRED
                if no_involvement:
                    gaps.append("The report of changed work conflicts with the reported absence of decision involvement; clarify the account before relying on it.")
            elif _is_no(changed):
                reasons.append("No change to work is reported; possible future influence remains distinct from an actual change.")
            if involved: outcome = ACTION_REQUIRED
        elif threat.kind in {"Self-review", "Advocacy"}:
            reasons.append("The specific prior-work or promoted-position connection, rather than a generic professional role, supports this potential threat.")
            if involved: outcome = ACTION_REQUIRED

        if not case.reviewed:
            reasons.append("These source facts have not yet been reviewed as the user's account; the identification remains provisional.")
        if any(f.status == "disputed" for f in facts if f.id in threat.evidence_ids):
            gaps.append("Material source information is disputed.")
        subject_phrase = "your recorded connection" if threat.subject == "user" else actor(threat.subject) + "'s recorded connection"
        concern = f"A reasonable and informed third party would consider {subject_phrase} to {decision}: {threat.mechanism} "
        if outcome == ACTION_REQUIRED:
            concern += "On this account, proceeding requires a response addressing that specific influence; actual bias need not be proved. "
        elif outcome == NARROWED:
            concern += "The recorded lack of involvement narrows the effect on your current judgment; it is not a general assurance of Objectivity. "
        else:
            concern += "The recorded facts do not yet justify concluding that Objectivity is appropriately protected. "
        if gaps:
            concern += "The material limits are: " + "; ".join(gaps)
        else:
            concern += "Any protective response is evaluated separately against its implementation and outcome evidence."
        evaluations.append(ThreatEvaluation(threat.id, outcome, _unique(reasons), _unique(gaps), concern))

    kinds = {threat.kind for threat in threats}
    interactions = []
    if len(threats) > 1:
        actors = _unique(actor(threat.subject) for threat in threats)
        interactions.append("The distinct sources involving " + ", ".join(actors) + " must be considered together. One response does not automatically address every source, and a shared statement is not independent corroboration.")
    if {"Self-interest", "Intimidation"} <= kinds:
        interactions.append("An incentive can make reported pressure harder to resist. The beneficiary and the person applying influence remain separately attributed.")
    if {"Familiarity", "Intimidation"} <= kinds:
        interactions.append("A relationship may make an instruction harder to challenge only where the relevant actors are linked; their identities are not assumed to be the same.")
    if not threats:
        limitations.append("No specific Objectivity threat is established by the currently recorded facts. Missing or unrecognised information is not evidence that threats are absent.")
    limitations.extend((
        "This assessment concerns Objectivity only and does not certify compliance, establish misconduct or independently verify the account.",
        "For audit work, separate audit-independence and other applicable professional requirements need their own assessment.",
    ))
    ordered = tuple(sorted(questions.values(), key=lambda q: (q.priority, q.predicate != "decision", q.id)))
    return ReasoningSnapshot(tuple(threats), tuple(evaluations), ordered, _unique(interactions), _unique(limitations))
