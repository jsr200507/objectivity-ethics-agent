"""Strict JSON-compatible source records for scenario-driven assessments.

This codec accepts no findings, report text or effectiveness verdicts. Review
flags remain user-account acknowledgements, never independent verification.
"""
from copy import deepcopy
from dataclasses import asdict, fields
import json
import re

from .case_model import (
    ACTION_KINDS, ACTION_STAGES, FACT_STATUSES, PREDICATES, SOURCES,
    CaseAction, CaseActor, CaseAnswer, CaseFact, CaseHistory, CaseState,
)

CASE_RULES_VERSION = "objectivity-case-v1"
MAX_CASE_RECORDS = 2_000
MAX_CASE_TEXT = 100_000
MAX_CASE_BYTES = 2 * 1024 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SIGNATURE = re.compile(r"^(?:[0-9a-f]{64})?$")
_ACTOR_KINDS = {"person", "organisation", "organization", "professional", "unknown"}


class CaseCodecError(ValueError):
    """An unsupported case source document was rejected without partial restore."""


def _object(value, cls_or_keys, label):
    keys = {item.name for item in fields(cls_or_keys)} if isinstance(cls_or_keys, type) else set(cls_or_keys)
    if type(value) is not dict or set(value) != keys:
        raise CaseCodecError(f"{label} contains missing or unsupported fields.")
    return value


def _text(value, label, limit=MAX_CASE_TEXT):
    if type(value) is not str or len(value) > limit:
        raise CaseCodecError(f"{label} must be text within the supported limit.")
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError as error:
        raise CaseCodecError(f"{label} contains invalid Unicode text.") from error
    return value


def _id(value, label, *, optional=False):
    value = _text(value, label, 200)
    if value == "" and optional:
        return value
    if not _IDENTIFIER.fullmatch(value):
        raise CaseCodecError(f"{label} has an unsupported identifier.")
    return value


def _list(value, label, maximum=MAX_CASE_RECORDS):
    if type(value) is not list or len(value) > maximum:
        raise CaseCodecError(f"{label} has an unsupported structure or size.")
    return value


def _bool(value, label):
    if type(value) is not bool:
        raise CaseCodecError(f"{label} must be true or false.")
    return value


def _revision(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise CaseCodecError("A case revision has an unsupported value.")
    return value


def _ids(value, label):
    result = tuple(_id(item, label) for item in _list(value, label))
    if len(set(result)) != len(result):
        raise CaseCodecError(f"{label} contains duplicate identifiers.")
    return result


def _signature(value):
    value = _text(value, 'A source binding', 64)
    if not _SIGNATURE.fullmatch(value):
        raise CaseCodecError('A source binding has an unsupported format.')
    return value


def _actor(value):
    value = _object(value, CaseActor, 'An actor')
    result = CaseActor(
        _id(value['id'], 'An actor'), _text(value['label'], 'An actor label'),
        _text(value['role'], 'An actor role'), _text(value['kind'], 'An actor kind', 40),
    )
    if not result.label.strip() or result.kind not in _ACTOR_KINDS:
        raise CaseCodecError('An actor requires a label and supported kind.')
    return result


def _fact(value, scenario, actors, *, historical=False):
    value = _object(value, CaseFact, 'A fact')
    result = CaseFact(
        id=_id(value['id'], 'A fact'), subject=_id(value['subject'], 'A fact subject'),
        predicate=_text(value['predicate'], 'A fact type', 80), value=_text(value['value'], 'A fact value'),
        object_id=_id(value['object_id'], 'A fact object', optional=True),
        decision_id=_id(value['decision_id'], 'A decision', optional=True),
        source=_text(value['source'], 'A fact source', 40), excerpt=_text(value['excerpt'], 'A source excerpt'),
        status=_text(value['status'], 'A fact status', 40), reviewed=_bool(value['reviewed'], 'Fact review'),
        attribution=_text(value['attribution'], 'A fact attribution'),
        depends_on=_ids(value['depends_on'], 'Fact dependencies'), revision=_revision(value['revision']),
    )
    if result.predicate not in PREDICATES or result.status not in FACT_STATUSES or result.source not in SOURCES:
        raise CaseCodecError('A fact contains an unsupported type, source or evidence status.')
    if not historical and result.status != 'withdrawn':
        if result.subject not in actors or result.object_id and result.object_id not in actors:
            raise CaseCodecError('A current fact refers to an unknown actor.')
        if result.source == 'scenario' and (not result.excerpt or result.excerpt not in scenario):
            raise CaseCodecError('A scenario fact must cite literal wording from the current account.')
    return result


def _checks(value, *, historical=False):
    if type(value) is not dict or len(value) > 30:
        raise CaseCodecError('Action evidence checks have an unsupported structure.')
    if not value:
        return {}
    from .case_actions import ACTION_CHECK_OPTIONS
    result = {}
    for key, item in value.items():
        key = _text(key, 'An action evidence check', 80)
        item = _text(item, 'An action evidence answer', 1_000)
        if not historical and (key not in ACTION_CHECK_OPTIONS or item not in ACTION_CHECK_OPTIONS[key]):
            raise CaseCodecError('An action evidence check has an unsupported question or answer.')
        result[key] = item
    return result


def _action(value, scenario, actors, *, historical=False):
    value = _object(value, CaseAction, 'An action')
    result = CaseAction(
        id=_id(value['id'], 'An action'), description=_text(value['description'], 'An action description'),
        kind=_text(value['kind'], 'An action type', 80), stage=_text(value['stage'], 'An action stage', 80),
        actor_id=_id(value['actor_id'], 'An action actor'),
        threat_ids=_ids(value['threat_ids'], 'Action coverage'), source=_text(value['source'], 'An action source', 40),
        excerpt=_text(value['excerpt'], 'An action excerpt'), checks=_checks(value['checks'], historical=historical),
        reviewed=_bool(value['reviewed'], 'Action review'), basis_signature=_signature(value['basis_signature']),
        revision=_revision(value['revision']), evidence_detail=_text(value['evidence_detail'], 'Action evidence description'),
    )
    if result.kind not in ACTION_KINDS or result.stage not in ACTION_STAGES or result.source not in SOURCES:
        raise CaseCodecError('An action contains an unsupported type, source or stage. Effectiveness is derived, not imported.')
    if not historical:
        if result.actor_id not in actors:
            raise CaseCodecError('An action refers to an unknown actor.')
        if result.source == 'scenario' and (not result.excerpt or result.excerpt not in scenario):
            raise CaseCodecError('A scenario action must cite literal wording from the current account.')
    return result


def _answer(value):
    value = _object(value, CaseAnswer, 'A case clarification answer')
    return CaseAnswer(
        question_id=_id(value['question_id'], 'A clarification question'),
        choice=_text(value['choice'], 'A clarification answer', 1_000),
        explanation=_text(value['explanation'], 'A clarification explanation'),
        fact_id=_id(value['fact_id'], 'A clarification fact'),
        depends_on=_ids(value['depends_on'], 'Clarification dependencies'),
        basis_signature=_signature(value['basis_signature']),
        prompt=_text(value['prompt'], 'A clarification label'),
    )


def _history(value):
    value = _object(value, CaseHistory, 'Case history')
    return CaseHistory(
        _text(value['label'], 'A history label'), _text(value['value'], 'A historical answer'),
        _text(value['detail'], 'Historical details'), _revision(value['revision']),
        _text(value['reason'], 'A history explanation'),
    )


def _unique(records, label):
    ids = [record.id for record in records]
    if len(set(ids)) != len(ids):
        raise CaseCodecError(f'{label} contains duplicate identifiers.')


def _case_from_dict(document):
    if document is None:
        return None
    document = _object(document, {'rules_version', 'state'}, 'The scenario assessment')
    if document['rules_version'] != CASE_RULES_VERSION:
        raise CaseCodecError('The scenario assessment requires a different reasoning rules version.')
    value = _object(document['state'], CaseState, 'The scenario assessment source state')
    scenario = _text(value['scenario'], 'The case scenario')
    actors = [_actor(item) for item in _list(value['actors'], 'Case actors')]
    _unique(actors, 'Case actors')
    actor_ids = {actor.id for actor in actors}
    facts = [_fact(item, scenario, actor_ids) for item in _list(value['facts'], 'Case facts')]
    _unique(facts, 'Case facts')
    facts_by_id = {fact.id: fact for fact in facts}
    for fact in facts:
        if fact.status != 'withdrawn' and any(id not in facts_by_id for id in fact.depends_on):
            raise CaseCodecError('A current fact refers to a missing source fact.')
    actions = [_action(item, scenario, actor_ids) for item in _list(value['actions'], 'Case actions')]
    _unique(actions, 'Case actions')
    if type(value['answers']) is not dict or len(value['answers']) > MAX_CASE_RECORDS:
        raise CaseCodecError('Case clarification answers have an unsupported structure or size.')
    answers = {}
    for id, item in value['answers'].items():
        id = _id(id, 'A case clarification')
        answer = _answer(item)
        if id != answer.question_id:
            raise CaseCodecError('A case answer does not match its question identifier.')
        if answer.fact_id not in facts_by_id or any(dep not in facts_by_id for dep in answer.depends_on):
            raise CaseCodecError('A case answer refers to missing source information.')
        answer_fact = facts_by_id[answer.fact_id]
        if answer_fact.source != 'user' or answer_fact.value != answer.choice or answer_fact.depends_on != answer.depends_on:
            raise CaseCodecError('A case answer contradicts its recorded source fact.')
        answers[id] = answer
    case = CaseState(
        scenario=scenario, actors=actors, facts=facts, actions=actions, answers=answers,
        history=[_history(item) for item in _list(value['history'], 'Case answer history')],
        fact_history=[_fact(item, scenario, actor_ids, historical=True) for item in _list(value['fact_history'], 'Case fact history')],
        action_history=[_action(item, scenario, actor_ids, historical=True) for item in _list(value['action_history'], 'Case action history')],
        revision=_revision(value['revision']), reviewed=_bool(value['reviewed'], 'Case review'),
        actions_reviewed=_bool(value['actions_reviewed'], 'Existing actions review'),
        limitations=[_text(item, 'A case limitation') for item in _list(value['limitations'], 'Case limitations')],
        legacy_records=[_history(item) for item in _list(value['legacy_records'], 'Legacy case records')],
    )
    # Source updates invalidate dependent replies. This operation does not
    # create a finding or assert that the underlying account has been verified.
    from .case_workflow import sync_case
    sync_case(case)
    return case


def case_from_dict(document):
    """Read an already safely parsed JSON value without executable loading."""
    try:
        return _case_from_dict(document)
    except CaseCodecError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError, OverflowError) as error:
        raise CaseCodecError('The scenario assessment source records are invalid or incompatible.') from error


def case_to_dict(case):
    """Copy and validate source records, excluding all derived ethical results."""
    if case is None:
        return None
    if not isinstance(case, CaseState):
        raise CaseCodecError('The scenario assessment must use the supported source model.')
    try:
        value = {'rules_version': CASE_RULES_VERSION, 'state': asdict(deepcopy(case))}
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > MAX_CASE_BYTES:
            raise CaseCodecError('The scenario assessment exceeds the supported progress size.')
        validated = case_from_dict(json.loads(encoded))
        return json.loads(json.dumps({'rules_version': CASE_RULES_VERSION, 'state': asdict(validated)}, ensure_ascii=False, allow_nan=False))
    except CaseCodecError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, UnicodeError, RecursionError, OverflowError) as error:
        raise CaseCodecError('The scenario assessment cannot be exported as supported source JSON.') from error
