"""Pre-safeguard presentation; internal Address verdicts are never overwritten."""
from dataclasses import dataclass
import re

from .case_model import (
    CAREER_CONDITION, CAREER_EXPECTATION, CAREER_FACTOR,
    NO_WORK_CONTACT, ROUTINE_CONTACT, SUBSTANTIVE_CONTACT,
)
from .case_questions import _personal_career_incentive, plan_questions
from .case_reasoning import ACCEPTABLE, ACTION_REQUIRED, _is_no, _is_yes, _live, _lookup, _unknown

QUESTION_LABELS = {
    'financing_consequences': 'Possible financing or loan covenant consequences',
    'pressure_authority': 'Authority or influence over your work or career',
    'challenge_safety': 'Ability to challenge or escalate without adverse consequences',
    'work_change_details': 'Aspects of work reported as changed',
    'familiarity_contact': 'Contact about the work',
    'career_incentive_basis': 'Basis for the reported career incentive',
}

_FOLLOW_UP_FINDINGS = {
    'familiarity_contact': {
        SUBSTANTIVE_CONTACT: (
            'Potentially heightened familiarity influence',
            'The reported discussion creates a direct way for the relationship to affect scrutiny of the work. The relative’s role in preparing or controlling it still depends on the separate evidence.',
        ),
        ROUTINE_CONTACT: (
            'Work-related contact factor narrowed',
            'Routine updates suggest limited contact on this work. The ongoing relationship and any separate involvement still matter.',
        ),
        NO_WORK_CONTACT: (
            'Work-related contact factor narrowed',
            'The account indicates no work-related contact with this person. Possible influence through the relationship or their role in the work remains a separate consideration.',
        ),
    },
    'career_incentive_basis': {
        CAREER_CONDITION: (
            'Potentially heightened career incentive',
            'A communicated condition can make the career incentive more immediate. The reported condition provides no independent confirmation of a career outcome.',
        ),
        CAREER_FACTOR: (
            'Career incentive reported as one factor',
            'The reported link can influence professional judgment even where several factors determine the career outcome.',
        ),
        CAREER_EXPECTATION: (
            'Career expectation reported',
            'A personal expectation can still incline the professional toward a favourable outcome.',
        ),
    },
}


@dataclass(frozen=True)
class PreliminaryAssessment:
    significance: str
    factors: tuple[str, ...]
    gaps: tuple[str, ...]
    third_party: str


def _preliminary_reason(text):
    # Retain circumstance-based reasoning, leaving all final clearance and
    # additional-safeguard decisions to the existing Address/residual sections.
    return ' '.join(sentence for sentence in re.split(r'(?<=[.!?])\s+', text)
                    if not any(term in sentence.casefold() for term in (
                        'acceptable level', 'no additional safeguard', 'identification remains provisional')))


def _supplemental_attribution(case, fact):
    """Separate the party concerned from the person reporting the answer."""
    labels = {a.id: a.label for a in case.actors}
    subject = 'You' if fact.subject == 'user' else labels.get(fact.subject, 'the relevant party')
    respondent = 'You' if fact.source == 'user' else labels.get(fact.attribution, '')
    if not respondent and fact.attribution in labels.values():
        respondent = fact.attribution
    if fact.predicate == 'pressure_authority':
        return subject + (f' (reported by {respondent})' if respondent and respondent != subject else '')
    if respondent and respondent != subject:
        return f'{respondent} (concerning {subject})'
    return respondent or subject


def _supplemental_significance(case, threat, source, facts, evaluation, gaps, default):
    """Qualify preliminary significance only; never change an Address verdict."""
    if evaluation and evaluation.outcome == ACCEPTABLE:
        return default, ()  # Retain a specifically recorded nonconnection or lack of involvement.
    notes = []
    uncertainty = '; significance remains uncertain' if gaps else ''
    if threat.kind == 'Intimidation':
        authority = _lookup(facts, 'pressure_authority', threat.subject, 'user', threat.decision_id)
        challenge = _lookup(facts, 'challenge_safety', 'user', threat.subject, threat.decision_id)
        changed = _lookup(facts, 'work_changed', 'user', threat.subject, threat.decision_id)
        reported = lambda fact, values: fact is not None and fact.status == 'reported' and fact.value in values
        authority_present = reported(authority, {
            'Directs or can override my work', 'Influences performance assessment or career progression',
            'Both work and career influence',
        })
        authority_absent = reported(authority, {'No such authority or influence'})
        adverse = reported(challenge, {'Adverse consequences have been reported'})
        safe_challenge = reported(challenge, {'I can challenge or escalate without adverse consequences'})
        no_route = reported(challenge, {'No practicable route is known'})
        concern_only = reported(challenge, {'I am concerned but no consequence has been stated'})
        if no_route or concern_only:
            uncertainty = '; significance remains uncertain'
        if authority_present:
            notes.append('Reported authority over work or career may heighten the influence of the request; a job title alone is not evidence of that authority.')
        if adverse:
            notes.append('Reported adverse consequences may heighten the difficulty of challenging the request; they remain an unverified account, not proof of misconduct.')
        if _is_yes(changed):
            notes.append('A reported change to work indicates potentially heightened influence and calls for attention to the affected work; it does not establish technical error or misconduct.')
        if authority_absent:
            if no_route:
                notes.append('No work or career authority is reported, but this does not establish a practicable way to challenge the request.')
            else:
                notes.append('The reported absence of work or career authority narrows that particular influence channel without resolving other possible pressure.')
        if safe_challenge:
            notes.append('A reported ability to challenge safely narrows that influence channel; it is not evidence of an implemented or effective safeguard.')
        if no_route:
            notes.append('No practicable challenge or escalation route is reported as known. This is not evidence of explicit retaliation or coercion, and does not establish that no route exists.')
        if concern_only:
            notes.append('Concern is reported, but no adverse consequence has been stated; concern alone is not evidence of actual retaliation or coercion.')
        if _is_no(changed):
            notes.append('No actual change to work is reported. That account does not exclude possible future pressure.')
        notes.append('Possible future pressure still needs consideration. Narrowing an influence channel does not establish that the threat has been eliminated.')
        if authority_present or adverse or _is_yes(changed):
            return 'Potentially heightened influence' + uncertainty, tuple(notes)
        if no_route:
            return 'Significance remains uncertain', tuple(notes)
        if authority_absent or safe_challenge:
            return 'Influence channels narrowed; future pressure remains' + uncertainty, tuple(notes)
        return 'Significance remains uncertain', tuple(notes)
    party = next((a for a in case.actors if a.id == threat.subject), None)
    if (threat.kind == 'Self-interest' and source and party and party.kind in {'organisation', 'organization'}
            and source.value == 'Organisational financing or loan covenant interest'):
        consequence = _lookup(facts, 'financing_consequences', source.subject, source.object_id, threat.decision_id)
        if consequence is not None and consequence.status == 'reported':
            if consequence.value in {'Possible covenant breach', 'Renegotiation or lender consent',
                                     'Additional security', 'Changes to borrowing terms', 'Several possible consequences'}:
                notes.append('The reported possible financing consequences may heighten the incentive to favour an outcome; they are not verified outcomes or a personal financial benefit.')
                return 'Potentially heightened organisational incentive' + uncertainty, tuple(notes)
            if consequence.value == 'No financing consequence identified':
                notes.append('No financing consequence has been identified in the account. This narrows that factor without establishing the absence of consequences or removing the recorded organisational interest.')
                return 'Financing consequence factor narrowed; organisational interest remains' + uncertainty, tuple(notes)
        return 'Significance remains uncertain', ()
    return default, ()


def preliminary_assessment(case, snapshot, threat, plan=None):
    plan = plan if plan is not None else plan_questions(case, snapshot)
    evaluation = next((e for e in snapshot.evaluations if e.threat_id == threat.id), None)
    significance = 'Significance remains uncertain'
    if evaluation and evaluation.outcome == ACCEPTABLE:
        significance = 'Recorded circumstances narrow this potential threat'
    elif evaluation and evaluation.outcome == ACTION_REQUIRED:
        significance = 'Potentially significant influence'
    factors = [_preliminary_reason(text) for text in evaluation.reasoning if text != threat.mechanism] if evaluation else []
    gaps = list(evaluation.material_gaps) if evaluation else ['A threat-specific evaluation is not established.']
    facts = _live(case)
    actor = next((a.label for a in case.actors if a.id == threat.subject), 'the relevant party')
    source = next((f for f in facts if f.id == threat.evidence_ids[0]), None)
    relevant = []
    if threat.kind == 'Self-interest' and source:
        relevant.append(('financing_consequences', source.subject, source.object_id))
        if _personal_career_incentive(source):
            relevant.append(('career_incentive_basis', source.subject, source.object_id))
    elif threat.kind == 'Familiarity' and source:
        relevant.append(('familiarity_contact', source.object_id, source.subject))
    elif threat.kind == 'Intimidation':
        relevant.extend((('pressure_authority', threat.subject, 'user'),
                         ('challenge_safety', 'user', threat.subject),
                         ('work_change_details', 'user', threat.subject)))
    new_factors = []
    follow_up = None
    has_follow_up = False
    for predicate, subject, obj in relevant:
        fact = _lookup(facts, predicate, subject, obj, threat.decision_id)
        if fact is None:
            continue
        label = QUESTION_LABELS[predicate]
        attribution = _supplemental_attribution(case, fact)
        interpretations = _FOLLOW_UP_FINDINGS.get(predicate)
        if interpretations is not None:
            has_follow_up = True
            if fact.status == 'reported':
                follow_up = interpretations.get(fact.value)
        if fact.excerpt:
            prefix = 'Additional reported explanation' if fact.source == 'user' else 'Reported source excerpt'
            new_factors.append(f'{prefix} — {attribution}, retained without automatic interpretation: ' + fact.excerpt)
        if _unknown(fact):
            gaps.append(f'{label} remains unknown or requires interpretation; no favourable circumstance is assumed.')
            continue
        if interpretations is not None and follow_up is None:
            gaps.append(f'{label} requires clarification before assessing its influence.')
        elif predicate == 'career_incentive_basis' and fact.value == CAREER_EXPECTATION:
            gaps.append('Whether any career condition was communicated and how the decision could affect the outcome remain unresolved.')
        text = f'{label} — {attribution}: {fact.value} (reported, not independently verified).'
        new_factors.append(text)
        if predicate == 'financing_consequences':
            new_factors.append('These are reported possible financing effects, not verified outcomes or evidence of a personal financial benefit.')
        elif predicate == 'challenge_safety':
            new_factors.append('A reported route to challenge is distinct from an implemented or effective safeguard; concern about consequences is distinct from an explicit threat.')
        elif predicate == 'work_change_details':
            new_factors.append('The reported change identifies work needing attention; it does not establish technical error, bias or misconduct.')
    factors = [*new_factors, *factors]
    for q in (*plan.questions, *plan.deferred):
        if not q.threat_ids or threat.id in q.threat_ids:
            prefix = 'Question limit leaves unresolved: ' if q in plan.deferred else 'Unresolved: '
            gaps.append(prefix + q.prompt)
            has_follow_up |= q.predicate in _FOLLOW_UP_FINDINGS
    significance, supplemental_reasons = _supplemental_significance(case, threat, source, facts, evaluation, gaps, significance)
    factors.extend(supplemental_reasons)
    if has_follow_up and (evaluation is None or evaluation.outcome != ACCEPTABLE):
        if follow_up:
            significance = follow_up[0] + (' (material uncertainty remains)' if gaps else '')
            factors.append(follow_up[1])
        else:
            significance = 'Significance remains uncertain'
    decision = _lookup(facts, 'decision', 'user', '', threat.decision_id)
    activity = decision.value.split(';', 1)[0] if decision and not _unknown(decision) else 'the professional judgment under consideration'
    perspective = (
        f'If the recorded account is accurate, a reasonable and informed third party would consider how the reported '
        f'{threat.kind.lower()} source involving {actor} could influence {activity}, alongside the factors and unresolved information above. '
        'This is a provisional, conditional perspective before assessing safeguards; no actual independent third party has reviewed the case.'
    )
    return PreliminaryAssessment(significance, tuple(dict.fromkeys(f for f in factors if f)),
                                 tuple(dict.fromkeys(gaps)), perspective)
