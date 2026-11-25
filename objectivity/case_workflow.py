"""Source edits, adaptive answers and explicit migration for scenario reasoning."""
from copy import deepcopy
import hashlib

from .case_model import (
    ACTION_KINDS, ACTION_STAGES, FACT_STATUSES, PREDICATES,
    CaseAction, CaseActor, CaseAnswer, CaseFact, CaseHistory, CaseState,
)

MAX_TEXT = 100_000
_SINGLE_VALUE = frozenset({
    'role', 'decision', 'participation', 'decision_responsibility',
    'relationship_active', 'interest_connection', 'commercial_dependence',
    'work_changed', 'prior_work_affected',
    'financing_consequences', 'pressure_authority', 'challenge_safety', 'work_change_details',
    'familiarity_contact', 'career_incentive_basis',
})


def _text(value: str, label: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT or (required and not value.strip()):
        raise ValueError(f"Enter {label} within the supported text limit.")
    return value.strip()


def _id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


def start_case(scenario: str, provider=None) -> CaseState:
    from .understanding import LocalUnderstandingProvider, validate_understanding
    scenario = _text(scenario, 'a scenario')
    result = validate_understanding(scenario, (provider or LocalUnderstandingProvider()).understand(scenario))
    actors = deepcopy(list(result.actors))
    if not any(actor.id == 'user' for actor in actors):
        actors.insert(0, CaseActor('user', 'You', 'Professional role not established'))
    return CaseState(scenario, actors=actors, facts=deepcopy(list(result.facts)),
                     actions=deepcopy(list(result.actions)), limitations=list(result.limitations))


def sync_case(case: CaseState) -> tuple[str, ...]:
    """Expire dependent answers after material edits; all original sources survive."""
    from .case_reasoning import facts_signature
    removed = []
    while True:
        stale = []
        for key, answer in case.answers.items():
            fact = next((item for item in case.facts if item.id == answer.fact_id and item.status != 'withdrawn'), None)
            if fact is None or answer.basis_signature != facts_signature(case, answer.depends_on):
                stale.append(key)
        if not stale:
            break
        for key in stale:
            answer = case.answers.pop(key)
            case.history.append(CaseHistory(answer.prompt or 'Earlier clarification', answer.choice,
                answer.explanation, case.revision, 'Material supporting information changed; reconsider this answer.'))
            for fact in case.facts:
                if fact.id == answer.fact_id and fact.status != 'withdrawn':
                    case.fact_history.append(deepcopy(fact))
                    fact.status = 'withdrawn'
            removed.append(key)
    if removed:
        case.reviewed = False
    return tuple(removed)


def answer_case_question(case: CaseState, question_id: str, choice: str, explanation: str = '') -> None:
    from .case_reasoning import facts_signature
    from .case_questions import plan_questions
    sync_case(case)
    questions = {q.id: q for q in plan_questions(case).questions}
    if question_id not in questions:
        raise ValueError('Choose the currently relevant clarification.')
    q = questions[question_id]
    choice = _text(choice, 'an answer')
    explanation = _text(explanation, 'an explanation', required=False)
    if q.options and choice not in q.options:
        raise ValueError('Choose an available answer.')
    previous = case.answers.get(q.id)
    if previous and previous.choice == choice and previous.explanation == explanation:
        return
    case.revision += 1
    if previous:
        case.history.append(CaseHistory(previous.prompt, previous.choice, previous.explanation,
                                       case.revision, 'Answer revised.'))
    fid = _id('answer-', q.id)
    existing = next((fact for fact in case.facts if fact.id == fid), None)
    if existing:
        case.fact_history.append(deepcopy(existing))
        case.facts.remove(existing)
    status = 'unknown' if choice == 'Unknown' else 'reported'
    case.facts.append(CaseFact(fid, q.subject, q.predicate, choice, q.object_id, q.decision_id,
        'user', explanation, status, True, 'Structured user answer', q.depends_on, case.revision))
    case.answers[q.id] = CaseAnswer(q.id, choice, explanation, fid, q.depends_on,
                                  facts_signature(case, q.depends_on), q.prompt)


def review_case(case: CaseState) -> None:
    """Accept that the ledger reflects the account, without verifying its content."""
    if not case.reviewed:
        case.revision += 1
    for fact in case.facts:
        if fact.status != 'withdrawn':
            fact.reviewed = True
    case.reviewed = True


def edit_case_fact(case: CaseState, fact_id: str, value: str, status: str = 'reported',
                   *, subject: str | None = None, object_id: str | None = None) -> None:
    value = _text(value, 'the corrected detail')
    if status not in FACT_STATUSES:
        raise ValueError('Choose a supported evidence status.')
    fact = next((fact for fact in case.facts if fact.id == fact_id), None)
    if fact is None:
        raise ValueError('Choose an existing source fact.')
    actors = {actor.id for actor in case.actors}
    if subject is not None and subject not in actors or object_id is not None and object_id and object_id not in actors:
        raise ValueError('Choose the actual parties for this information.')
    if fact.value == value and fact.status == status and subject in {None, fact.subject} and object_id in {None, fact.object_id}:
        return
    case.revision += 1
    case.fact_history.append(deepcopy(fact))
    case.history.append(CaseHistory('Corrected reported information', fact.value, fact.excerpt,
                                   case.revision, 'User correction; earlier account retained.'))
    fact.value, fact.status, fact.source, fact.reviewed = value, status, 'user', True
    fact.attribution = 'User correction of an earlier account'
    if subject is not None:
        fact.subject = subject
    if object_id is not None:
        fact.object_id = object_id
    fact.revision = case.revision
    if fact.predicate == 'role' and fact.subject == 'user':
        next(a for a in case.actors if a.id == 'user').role = value
    case.reviewed = False
    # Correcting a recorded answer must not silently be replaced by its former
    # input record; the edited source remains authoritative for this revision.
    for key in [key for key, answer in case.answers.items() if answer.fact_id == fact_id]:
        answer = case.answers.pop(key)
        case.history.append(CaseHistory(answer.prompt, answer.choice, answer.explanation,
                                       case.revision, 'Source answer corrected directly.'))
    sync_case(case)


def add_case_fact(case: CaseState, subject: str, predicate: str, value: str,
                  object_id: str = '', status: str = 'reported', decision_id: str = 'decision') -> CaseFact:
    value = _text(value, 'the reported information')
    if predicate not in PREDICATES or status not in FACT_STATUSES:
        raise ValueError('Choose a supported fact type and status.')
    actors = {actor.id for actor in case.actors}
    if subject not in actors or object_id and object_id not in actors:
        raise ValueError('Choose the actual parties for this information.')
    decision_id = _text(decision_id, 'the decision reference')
    case.revision += 1
    if predicate in _SINGLE_VALUE:
        # A later scoped clarification replaces the earlier account, including
        # an explicit Unknown. Multiple incentives/pressure sources coexist.
        for earlier in case.facts:
            if (earlier.subject, earlier.predicate, earlier.object_id, earlier.decision_id) == (subject, predicate, object_id, decision_id) and earlier.status != 'withdrawn':
                case.fact_history.append(deepcopy(earlier))
                earlier.status = 'withdrawn'
                for key in [key for key, answer in case.answers.items() if answer.fact_id == earlier.id]:
                    previous = case.answers.pop(key)
                    case.history.append(CaseHistory(previous.prompt, previous.choice,
                        previous.explanation, case.revision, 'Superseded by newer scoped information.'))
    fact = CaseFact(_id('user-', f'{case.revision}:{subject}:{predicate}:{value}'), subject, predicate,
                    value, object_id, decision_id, 'user', '', status, True, 'Structured user information', (), case.revision)
    case.facts.append(fact)
    case.reviewed = False
    if predicate == 'role' and subject == 'user':
        next(a for a in case.actors if a.id == 'user').role = value
    sync_case(case)
    return fact


def add_case_actor(case: CaseState, label: str, role: str = '', kind: str = 'person') -> CaseActor:
    label, role = _text(label, 'a party name or description'), _text(role, 'a role', required=False)
    if kind not in {'person', 'organisation'}:
        raise ValueError('Choose a person or organisation.')
    existing = next((actor for actor in case.actors if actor.label.casefold() == label.casefold()), None)
    if existing:
        return existing
    actor = CaseActor(_id('actor-',label.casefold()), label, role, kind)
    case.actors.append(actor)
    case.revision += 1
    case.reviewed = False
    return actor


def save_case_action(case: CaseState, description: str, kind: str, stage: str,
                     threat_ids=(), checks=None, action_id: str | None = None,
                     actor_id: str = 'user', evidence_detail: str = '') -> CaseAction:
    from .case_actions import ACTION_CHECK_OPTIONS, action_basis_signature
    from .case_reasoning import reason_case
    description = _text(description, 'the actual or proposed action')
    evidence_detail = _text(evidence_detail, 'the supporting record description', required=False)
    if kind not in ACTION_KINDS or stage not in ACTION_STAGES:
        raise ValueError('Choose an action type and reported implementation status.')
    if actor_id not in {a.id for a in case.actors}:
        raise ValueError('Choose who took or proposed the action.')
    selected = tuple(dict.fromkeys(threat_ids))
    supported = {threat.id for threat in reason_case(case).threats}
    if any(tid not in supported for tid in selected):
        raise ValueError('Review which current threats the action addresses.')
    checks = dict(checks or {})
    if any(key not in ACTION_CHECK_OPTIONS or value not in ACTION_CHECK_OPTIONS[key] for key,value in checks.items()):
        raise ValueError('Choose supported implementation/effectiveness evidence.')
    checks['stage'] = stage
    old = next((a for a in case.actions if a.id == action_id), None) if action_id else None
    if action_id and old is None:
        raise ValueError('Choose an existing action.')
    first_source_review = bool(old and old.source == 'scenario' and not old.reviewed and not old.basis_signature
        and (old.description, old.kind, old.stage, old.actor_id) == (description, kind, stage, actor_id))
    if old and not first_source_review and (
        old.basis_signature != action_basis_signature(case, old)
        or (old.description, old.kind, old.stage, old.actor_id, old.threat_ids)
        != (description, kind, stage, actor_id, selected)
    ):
        # Retain implementation as an account, but do not rebind hidden old
        # effectiveness criteria by merely resaving an edited record.
        checks = {'stage': stage}
    case.revision += 1
    if old:
        case.action_history.append(deepcopy(old))
        old.description, old.kind, old.stage = description, kind, stage
        old.threat_ids, old.checks, old.actor_id = selected, checks, actor_id
        old.source, old.reviewed, old.revision = 'user', True, case.revision
        action = old
    else:
        action = CaseAction(_id('action-',f'{case.revision}:{description}'),description,kind,stage,
                            actor_id,selected,'user','',checks,True,'',case.revision)
        case.actions.append(action)
    action.basis_signature = action_basis_signature(case, action)
    action.evidence_detail = evidence_detail
    case.actions_reviewed = True
    return action


def answer_action_question(case: CaseState, question_id: str, choice: str) -> None:
    from .case_actions import action_questions, action_basis_signature
    questions = {q.id:q for q in action_questions(case)}
    if question_id not in questions or (questions[question_id].options and choice not in questions[question_id].options):
        raise ValueError('Choose an available action evidence answer.')
    q = questions[question_id]
    action = next(a for a in case.actions if a.id == q.action_id)
    case.action_history.append(deepcopy(action))
    case.revision += 1
    if action.basis_signature and action.basis_signature != action_basis_signature(case, action):
        # Answering one new criterion must not authenticate all the other
        # criteria collected for materially different circumstances.
        action.checks = {'stage': action.stage}
    if q.key == 'stage':
        action.stage = choice
        action.checks['stage'] = choice
    elif q.key == 'evidence_detail':
        action.evidence_detail = _text(choice, 'the supporting records or an explicit Unknown')
    else:
        action.checks[q.key] = choice
    action.reviewed, action.revision = True, case.revision
    action.basis_signature = action_basis_signature(case, action)


def migrate_legacy_assessment(assessment, review=None, address=None) -> CaseState:
    """Explicitly reassess old progress while leaving every legacy source intact."""
    case = start_case(assessment.scenario)
    fields = vars(assessment.context)
    for name,value in fields.items():
        if value:
            case.legacy_records.append(CaseHistory(name.replace('_',' ').capitalize(), str(value),
                'Previous context; user confirmation did not verify it.', assessment.revision, 'Legacy assessment retained.'))
    for state,label in ((assessment,'Clarification'),(review,'Evaluation'),(address,'Address')):
        if state is None: continue
        for key,answer in state.answers.items():
            case.legacy_records.append(CaseHistory(f'Previous {label} answer',answer.choice,
                answer.explanation,assessment.revision,'Original source preserved; mapping may require review.'))
        for record in state.archive:
            case.legacy_records.append(CaseHistory(f'Superseded {label} answer',record.answer.choice,
                record.answer.explanation,record.revision,record.reason))
    # Latest structured context is authoritative over an older narrative
    # suggestion. Keep the suggestion/history without silently undoing edits.
    values = {'role':fields.get('role',''),'decision':fields.get('decision','')}
    for predicate,value in values.items():
        if value:
            fact = add_case_fact(case, 'user', predicate, value,
                                 status='unknown' if value in {'Unknown','Not applicable'} else 'reported')
            fact.source, fact.reviewed = 'legacy', assessment.confirmed
            fact.attribution = 'Latest previous structured context'
    # Categorical context can also correct a narrative suggestion. Map only
    # its explicit meaning, never interpret the old optional notes as facts.
    def retire(predicates, status='withdrawn'):
        for fact in case.facts:
            if fact.predicate in predicates and fact.status != 'withdrawn':
                case.fact_history.append(deepcopy(fact))
                fact.status = status

    relationship = fields.get('relationship', 'Unknown')
    if relationship in {'No relevant relationship','Professional relationship only','Not applicable'}:
        retire({'family_relationship','close_relationship'})
    elif relationship == 'Close personal relationship' and not any(f.predicate in {'close_relationship','family_relationship'} and f.status=='reported' for f in case.facts):
        party = add_case_actor(case, 'Related person from previous assessment (identity not established)')
        fact = add_case_fact(case, 'user', 'close_relationship', 'Close personal relationship', party.id)
        fact.source, fact.reviewed = 'legacy', assessment.confirmed
    interest = fields.get('interests', 'Unknown')
    if interest in {'No known interest','Not applicable'}:
        retire({'interest'})
    else:
        if interest in {'Personal financial interest','Both commercial and personal interests'} and not any(f.predicate=='interest' and f.subject=='user' and f.status=='reported' for f in case.facts):
            fact = add_case_fact(case, 'user', 'interest', 'Personal financial interest reported in previous structured context')
            fact.source, fact.reviewed = 'legacy', assessment.confirmed
        if interest in {'Commercial interest','Both commercial and personal interests'} and not any(f.predicate=='interest' and f.subject!='user' and f.status=='reported' for f in case.facts):
            party = add_case_actor(case, 'Commercial beneficiary from previous assessment (identity not established)')
            fact = add_case_fact(case, party.id, 'interest', 'Commercial interest reported in previous structured context')
            fact.source, fact.reviewed = 'legacy', assessment.confirmed
    pressure = fields.get('pressure', 'Unknown')
    if pressure in {'No reported pressure','Not applicable'}:
        retire({'pressure'})
    elif pressure == 'Reported pressure or threatened consequences' and not any(f.predicate=='pressure' and f.status=='reported' for f in case.facts):
        party = add_case_actor(case, 'Source of reported pressure from previous assessment (identity not established)')
        fact = add_case_fact(case, party.id, 'pressure', 'Pressure or threatened consequences reported; nature requires clarification', 'user')
        fact.source, fact.reviewed = 'legacy', assessment.confirmed
    if 'Unknown' in {relationship, interest, pressure}:
        case.limitations.append('Some earlier context classifications were Unknown. Any narrative-derived proposals remain provisional and must be reviewed against that incomplete earlier context.')
    mapping = {
        'relationship_influence':'decision_responsibility','pressure_effect':'work_changed',
        'personal_outcome':'interest_connection','commercial_dependence':'commercial_dependence',
    }
    for key,predicate in mapping.items():
        answer = assessment.answers.get(key)
        if answer and not any(f.predicate==predicate and f.subject=='user' for f in case.facts):
            case.facts.append(CaseFact(_id('legacy-',key),'user',predicate,answer.choice,
                source='legacy',status='unknown' if answer.choice=='Unknown' else 'reported',
                reviewed=assessment.confirmed,attribution='Previous structured answer'))
    if review and 'decision_responsibility' in review.answers and not any(f.predicate=='decision_responsibility' for f in case.facts):
        value=review.answers['decision_responsibility'].choice
        case.facts.append(CaseFact(_id('legacy-','responsibility'),'user','decision_responsibility',value,
            source='legacy',status='unknown' if value=='Unknown' else 'reported',reviewed=True,
            attribution='Previous evaluation answer'))
    if address:
        grouped={}
        for key,answer in address.answers.items():
            pieces=key.split(':')
            if len(pieces)==3: grouped.setdefault(tuple(pieces[:2]),{})[pieces[2]]=answer.choice
        for (kind,slot),items in grouped.items():
            description=items.get('action')
            if not description: continue
            action_kind=next((target for text,target in (
                ('review','independent_review'),('Remove me','remove_from_decision'),('Eliminate','eliminate'),
                ('Escalate','escalate'),('Disclose','disclose'),('Document','document'),('Decline','decline'),
                ('No action','none')) if text.lower() in description.lower()),'other')
            old_stage=items.get('implementation','')
            stage='Implemented' if old_stage in {'Implemented according to my account','Attempted but unsuccessful'} else 'Planned' if old_stage in {'Proposed, not yet started','Requested or in progress'} else 'Not Taken' if action_kind=='none' else 'Unknown'
            checks={'outcome':'Continuing influence remains'} if old_stage=='Attempted but unsuccessful' else {}
            case.actions.append(CaseAction(_id('legacy-action-',f'{kind}:{slot}'),description,action_kind,
                stage,source='legacy',checks=checks))
    case.limitations.append('Previous answers and actions are retained. Ambiguous ownership and category-level action coverage require review; no previous ethical verdict was imported.')
    return case
