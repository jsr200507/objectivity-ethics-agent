"""Local, source-linked scenario understanding with no network/model dependency.

The provider proposes attributed records, not ethical findings. Exact excerpts
and conservative grammars make proposals inspectable; unfamiliar wording remains
available for user correction rather than being invented or silently verified.
"""
from copy import deepcopy
import hashlib
import re

from .case_model import (
    ACTION_KINDS, ACTION_STAGES, PREDICATES,
    CAREER_CONDITION, CAREER_EXPECTATION, CAREER_FACTOR,
    NO_WORK_CONTACT, ROUTINE_CONTACT, SUBSTANTIVE_CONTACT, CaseActor, CaseAction, CaseFact,
    UnderstandingResult,
)
from .extraction import MAX_SCENARIO_LENGTH, extract_context
from .extraction_entities import ROLE_PATTERN
from .extraction_signals import extract_signals

_FAMILY = r"(?:sister|brother|spouse|wife|husband|mother|father|parent|daughter|son|child|cousin)"
_TITLE = re.compile(rf"\b(?:(?:investment|treasury|funding|fundraising|grants|development|commercial|strategy)\s+(?:director|manager|officer)|{ROLE_PATTERN})s?\b", re.I)
_RECIPIENT_GROUP = re.compile(r'\b(?:audit\s+committee|ethics\s+committee|board\s+of\s+directors|board|regulators?|trustees)\b', re.I)
_RELATIVE = re.compile(rf"\b(?:my|your|our)\s+(?P<relation>{_FAMILY})\b", re.I)
_NAME = r"[A-Z][A-Za-z0-9&’'-]*(?:\s+[A-Z][A-Za-z0-9&’'-]*){0,4}"
_ORG = re.compile(rf"\b{_NAME}\s+(?:Valuations?|Valuers?|Surveyors?|Advisory|Supplies|Engineering|Components|Bank|Ltd|Limited|PLC|Inc|Foundation|Charity|Mutual|Tools)\b")
_GENERIC_ORG = re.compile(r"\b(?:external\s+valuation\s+firm|independent\s+valuation\s+firm|valuation\s+firm|manufacturing\s+company|listed\s+client|(?:our|your|my|the)\s+(?:firm|company|organisation|organization))\b", re.I)
_EMPLOYMENT = re.compile(rf"(?i:\b(?:my|your|our)\s+(?P<relation>{_FAMILY})\b[^.!?;]{{0,55}}\b(?:works?\s+(?:for|at|in)|is\s+employed\s+by|is\s+employed\s+at|is\s+an?\s+employee\s+of)\s+)(?P<org>{_NAME}|(?i:(?:an?\s+|the\s+)?(?:external\s+|independent\s+)?valuation\s+firm))\b")
_BENEFITS = re.compile(r"\b(?:bonus(?:es)?|commissions?|consulting\s+fee|advisory\s+fee|contingent\s+fee|success\s+fee|retainer|shareholdings?|shares?|equity|stock\s+options?|financial\s+(?:benefit|incentive)|cash\s+reward|pay\s+rise|salary\s+increase)\b", re.I)
_LINK = re.compile(r"\b(?:depend(?:s|ent)?|tied|linked|conditional|contingent|in\s+return|provided\s+that|only\s+if|on\s+each\s+(?:sale|approval)|based\s+on)\b", re.I)
_FINANCING_EFFECT = re.compile(r'\baffect(?:s|ed|ing)?\b', re.I)
_FIRM_INCENTIVE = re.compile(r"\b(?:contract\s+renewal|client\s+retention|retain\s+(?:the\s+)?client|profit\s+targets?|firm[’']?s?\s+fees?|firm\b[^.!?;]{0,45}\b(?:earns?|receives?)\s+(?:a\s+)?(?:fee|income|retainer))\b", re.I)
_CAREER = re.compile(r'\b(?:promotion|career\s+advancement|job\s+security|continued\s+employment)\b', re.I)
_ORG_FINANCE = re.compile(r'\b(?:refinancing|financing|borrowing|(?:loan|debt|lending)\s+covenants?|credit\s+(?:facility|line)|funding\s+(?:renewal|agreement|conditions)|capital\s+raise)\b', re.I)
_HYPOTHETICAL = re.compile(r"^\s*(?:suppose|supposing|imagine|hypothetically|perhaps|maybe)\b", re.I)
_HISTORICAL = re.compile(r"^\s*(?:previously|historically|last\s+year|in\s+an?\s+(?:old|unrelated)\s+case)\b", re.I)
_CONTEXT_FIELD = re.compile(r'^\s*(?:[-*]\s+)?(?:your\s+)?(?:professional\s+)?(?P<field>role|decision|activity)\s*:\s*(?P<value>.+)$', re.I)
_WORK = (
    ('I make or recommend the decision', r'(?:mak(?:e|ing)|recommend(?:ing)?|approv(?:e|ing)|select(?:ing)?|decid(?:e|ing))'),
    ('I supervise or review the work', r'(?:review(?:ing)?|supervis(?:e|ing)|oversee(?:ing)?|check(?:ing)?|examin(?:e|ing)|audit(?:ing)?)'),
    ('I prepare or assess the work', r'(?:prepar(?:e|ing)|assess(?:ing)?|evaluat(?:e|ing)|compar(?:e|ing))'),
)
_COMPOUND_SELF_ROLE = re.compile(
    r"^\s*(?:I\s+(?:(?:now|currently)\s+)?(?:am|work\s+as|serve\s+as)|I['’]m|"
    r"you\s+(?:(?:now|currently)\s+)?(?:are|work\s+as|serve\s+as)|you['’]re)\s+"
    r'(?:(?:now|currently)\s+)?(?:(?:a|an|the)\s+)?'
    r'(?P<role>(?:[a-z][a-z-]*\s+){1,3}?and\s+(?:[a-z][a-z-]*\s+){1,3}?'
    r'(?:analyst|accountant|manager|director|officer|coordinator|associate|specialist|consultant|controller))\b',
    re.I,
)


def _compound_role(unit):
    """A bounded, explicit self-description, not another party's title."""
    match = _COMPOUND_SELF_ROLE.match(unit)
    if not match or re.search(
        r'\b(?:not|never|no|without|may|might|could|would|whether|if|who|that|or|to|asked|told|'
        r'considering|interested|reviewing|assessing|preparing|I|you|we|he|she|they|is|are|am)\b',
        match['role'], re.I,
    ):
        return None
    return match['role'][:1].upper() + match['role'][1:], match.group()


def _context_field(unit):
    """Recognise self-described field labels, retaining their literal source."""
    match = _CONTEXT_FIELD.fullmatch(unit)
    if not match:
        return None
    name = 'role' if match['field'].lower() == 'role' else 'decision'
    value = match['value'].strip().rstrip('.!?').strip()
    if re.fullmatch(r'unknown|unclear|not\s+(?:known|specified)|not\s+applicable|n/a', value, re.I):
        return name, 'Unknown', 'unknown'
    return (name, value, 'reported') if value else None


def _authority_kind(text):
    """Classify explicit authority wording for context notes, never evaluation."""
    for label, pattern in (
        ('Final approval authority', r'\b(?:final\s+approval\s+(?:authority|responsibility|rights?)|approval\s+(?:authority|rights?)|(?:authority|responsibility|power)\s+(?:to\s+approve|for\s+(?:the\s+)?final\s+approval)|authori[sz]ed\s+to\s+(?:give\s+final\s+approval|approve)|(?:can|cannot|can[’\']t)\s+(?:give\s+final\s+approval|approve\s+(?:the\s+)?final))\b'),
        ('Recommendation authority', r'\b(?:(?:can|cannot|can[’\']t)\s+(?:only\s+)?recommend|recommendation\s+authority|authority\s+to\s+recommend)\b'),
        ('Reviewing responsibility', r'\b(?:responsible|responsibility)\s+for\s+(?:review(?:ing)?|supervis(?:e|ing)|oversee(?:ing)?|check(?:ing)?)\b'),
    ):
        match = re.search(pattern, text, re.I)
        if match:
            prefix = text[:match.end()]
            absent = bool(re.search(r"\b(?:not|no|never|cannot|can['’]t|don['’]t|doesn['’]t|lack|lacks)\b", prefix, re.I))
            return label, absent
    return None


def _source_aliases(item):
    names = [item.label]
    names += {'company': ['company', 'organisation', 'organization'], 'firm': ['firm'],
              'valuation_firm': ['external valuation firm', 'independent valuation firm', 'valuation firm'],
              'cfo': ['chief financial officer']}.get(item.id, [])
    return tuple(dict.fromkeys(names))


def _authority_context(unit, actors):
    """Yield literal authority statements with their actual recorded speaker."""
    parties = {name.casefold(): item.id for item in actors.values() if item.id != 'user'
               for name in _source_aliases(item)}
    alternatives = '|'.join(re.escape(name) for name in sorted(parties, key=len, reverse=True))
    subject = r'I|you|we' + (rf'|(?:(?:the|my|your|our)\s+)?(?:{alternatives})' if alternatives else '')
    statement = re.compile(
        rf'\b(?P<who>{subject})\s+(?:(?:do|does)\s+not\s+|don[’\']t\s+|doesn[’\']t\s+)?'
        r'(?:(?:have|has|hold|holds|lack|lacks)\s+(?:(?:no|not|any|the|sole|only)\s+)*'
        r'(?:final\s+approval|approval|recommendation|authority|responsibility|power)|'
        r'(?:can|cannot|can[’\']t)\s+(?:only\s+)?(?:recommend|approve|give\s+final\s+approval)|'
        r'(?:am|are|is)\s+(?:not\s+)?(?:responsible|authori[sz]ed))\b[^.!?;\n"”]*', re.I,
    )
    if unit.rstrip().endswith('?'):
        return
    for clause in _scoped_clauses(unit):
        for match in statement.finditer(clause):
            value = match.group().strip().rstrip(' \'"”')
            if not _authority_kind(value):
                continue
            prefix = unit[:unit.find(clause) + match.start()]
            if re.search(r"\b(?:whether|if|unknown|unclear|unsure|denies|denied|asks?|asked|do\s+not\s+know|don['’]t\s+know)\b", prefix, re.I):
                continue
            who = match['who'].casefold()
            if who in {'i', 'you', 'we'}:
                reports = list(re.finditer(r'\b(?:says?|said|told|states?|stated|explains?|explained|claims?|claimed)\b', prefix, re.I))
                if reports:
                    before = prefix[:reports[-1].start()]
                    speakers = [(m.start(), item.id) for item in actors.values() if item.id != 'user'
                                and item.kind != 'organisation' for name in _source_aliases(item)
                                for m in re.finditer(r'\b' + re.escape(name) + r'\b', before, re.I)]
                    if not speakers:
                        continue
                    owner = max(speakers)[1]
                elif prefix.rstrip().endswith(('"', '“', "'")):
                    continue
                else:
                    owner = 'user'
            else:
                owner = parties.get(who) or parties.get(re.sub(r'^(?:the|my|your|our)\s+', '', who))
            if owner:
                yield owner, value


def _valuation_provider_ids(unit, actors):
    """Bind organisations to actual supplied work, not merely owned property."""
    if not re.search(r'\b(?:valuations?|estimates?|reports?|work|assessment)\b', unit, re.I):
        return ()
    result = []
    for item in actors.values():
        if item.kind != 'organisation':
            continue
        for name in _source_aliases(item):
            for mention in re.finditer(r'\b' + re.escape(name) + r'\b', unit, re.I):
                before, after = unit[:mention.start()], unit[mention.end():]
                supplied = re.search(r'\b(?:valuations?|estimates?|reports?|work|assessment)\s+(?:(?:that|which)\s+)?(?:(?:was|is|has\s+been)\s+)?(?:prepared|provided|produced|issued|performed|carried\s+out)\s+by\s+(?:(?:a|an|the|our|my|your)\s+)?$', before, re.I)
                from_work = re.search(r'\b(?:valuation|estimate|report|work|assessment)\s+(?:from|by)\s+(?:(?:a|an|the|our|my|your)\s+)?$', before, re.I)
                preparing = re.match(r'\s+(?:(?:has|have)\s+)?(?:prepared|provided|produced|issued|estimated)\b', after, re.I)
                cue = supplied or from_work
                if (cue and not _negated(before, cue.start())) or (preparing and not _negated(unit, mention.start())):
                    result.append(item.id)
    return tuple(dict.fromkeys(result))


def _valuation_document_actor(label, sentence):
    """An artifact phrase is not an organisation without an explicit name cue."""
    bare = re.fullmatch(r'(?:(?:a|an|the|external|independent|property|commercial|collateral)\s+)*valuation(?:\s+report)?', label, re.I)
    if not bare:
        return False
    named = re.search(r'\b(?:firm|company|organisation|organization|provider)\s+(?:called|named|known\s+as)\s+["“\']?' + re.escape(label) + r'\b', sentence, re.I)
    return not named


def _professional_responsibility(unit, role):
    """Reuse attributed current work, not titles, requests or quoted speakers."""
    field = _context_field(unit)
    if field and field[0] == 'role':
        return None
    title = re.escape(role) if role != 'Unknown' else ROLE_PATTERN
    # The finite title catalogue must not prevent reuse of clearly stated work
    # in "I am a [different profession] reviewing ...". Guard this bounded noun
    # phrase against negation, relative clauses and proposed/uncertain activity.
    title_prefix = rf'(?:(?:(?:a|an|the)\s+)?{title}|(?:a|an|the)\s+[a-z][a-z -]{{1,85}}?)\s+'
    self_cue = (
        r'\b(?:I|you|we)\s+(?:(?:now|currently|also|independently)\s+)?'
        rf'(?:(?:am|are)\s+(?:(?:now|currently)\s+)?(?P<title>{title_prefix})?'
        r'(?:(?:responsible\s+for|tasked\s+with)\s+)?|'
        r'(?:must|need\s+to|have\s+to)\s+)?'
        r'(?:(?:now|currently|also|independently)\s+)?'
    )
    clauses = _scoped_clauses(field[1] if field and field[2] == 'reported' else unit)
    for value, verb in _WORK:
        for clause in clauses:
            if _hypothetical(clause):
                continue
            # A labelled activity has an explicit user scope even without I/you.
            if field and field[2] == 'reported' and re.match(rf'^(?:to\s+)?{verb}\b', clause, re.I):
                return value
            for match in re.finditer(self_cue + rf'(?P<work>{verb})\b', clause, re.I):
                prefix = clause[:match.start()]
                if re.search(r'\b(?:said|says?|told|claims?|claimed|wrote|asked|stated|explained)\b', prefix, re.I):
                    continue
                scope = match['title'] or ''
                if role != 'Unknown' and re.fullmatch(rf'(?:(?:a|an|the)\s+)?{re.escape(role)}\s*', scope, re.I):
                    # These can be nouns/conjunctions inside the recorded title,
                    # rather than a new clause or an intention to perform work.
                    scope = re.sub(r'\b(?:and|planning)\b', '', scope, flags=re.I)
                if re.search(r'\b(?:not|never|no|without|may|might|could|would|perhaps|maybe|whether|if|who|that|and|or|to|asked|told|planning|considering|interested)\b', scope, re.I):
                    continue
                return value
    return None


def _user_provider_work(unit, role):
    """Require the user's own work, not another person's or quoted review."""
    return bool(_professional_responsibility(unit, role) or any(
        re.match(r'\s*(?:I|you|we)\s+(?:am\s+|are\s+)?rely(?:ing)?\s+on\b', clause, re.I)
        for clause in _scoped_clauses(unit) if not _hypothetical(clause)
    ))


def _decision_reference(text, decision):
    """Require an explicit decision reference or a shared substantive topic."""
    if not decision:
        return False
    if re.search(r'\b(?:this|that|the|my|your|our)\s+(?:decision|recommendation|judg(?:e)?ment|outcome)\b', text, re.I):
        return True
    generic = set('this that with from into before after year financial statements company organisation organization external independent current professional decision activity reviewing review assessing assess preparing prepare evaluating evaluate comparing compare recommending recommend approving approve selecting select supervising supervise finalised finalized'.split())
    topics = set(re.findall(r'\b[a-z]{4,}\b', decision.casefold())) - generic
    return bool(topics & set(re.findall(r'\b[a-z]{4,}\b', text.casefold())))


def _familiarity_contact(clause, relative, decision):
    """Reuse direct reports of contact about the current work."""
    party = rf'(?:my|your)\s+{re.escape(relative)}'
    topic = r'(?P<work>[^.!?;]{1,180})'
    for value, pattern in (
        (SUBSTANTIVE_CONTACT, rf'(?:I|you)\s+(?:have\s+)?discussed\s+{topic}\s+with\s+{party}'),
        (ROUTINE_CONTACT, rf'(?:I|you)\s+(?:have\s+)?exchanged\s+only\s+routine\s+updates\s+with\s+{party}\s+about\s+{topic}'),
        (NO_WORK_CONTACT, rf'(?:I|you)\s+(?:have\s+)?had\s+no\s+contact\s+with\s+{party}\s+about\s+{topic}'),
        ('Unknown', rf'(?:I|you)\s+(?:do\s+not|don[’\']t)\s+know\s+whether\s+(?:I|you)\s+had\s+(?:any\s+)?contact\s+with\s+{party}\s+about\s+{topic}'),
    ):
        match = re.fullmatch(pattern, clause.rstrip('.!?'), re.I)
        if match and _decision_reference(match['work'], decision):
            return value
    return None


def _career_incentive_basis(unit, start):
    """Classify only an explicit account of how the career link was established."""
    prefix = unit[:start]
    if re.fullmatch(r'(?:I|you)\s+(?:expect|believe|think)\s+(?:that\s+)?(?:my|your)\s+', prefix, re.I):
        return CAREER_EXPECTATION
    communicated = re.fullmatch(
        r'(?:I\s+was|you\s+were|(?:I|you)\s+have\s+been)\s+'
        r'(?:(?:formally|explicitly)\s+)?(?:told|informed)\s+(?:that\s+)?(?:my|your)\s+', prefix, re.I,
    )
    condition = unit[start:]
    written = re.search(r'\bunder\s+(?:my|your|the)\s+written\s+promotion\s+criteria\b', condition, re.I)
    if communicated or written:
        if re.search(r'\b(?:depends?\s+in\s+part|one\s+factor)\b', condition, re.I):
            return CAREER_FACTOR
        if re.search(r'\b(?:depends?\s+on|conditional\s+on|contingent\s+on|only\s+if)\b', condition, re.I):
            return CAREER_CONDITION
    return None


def _reported_financing_denial(unit, finance):
    """Reported rejection of a link is neither its affirmation nor verification."""
    parts = re.split(r';|\b(?:but|whereas|however)\b|\band\s+(?=(?:says?|said|states?|confirms?)\b)', unit, flags=re.I)
    clause = next((part for part in parts
                   if unit.find(part) <= finance.start() < unit.find(part) + len(part)), unit)
    report = re.search(r'\b(?:denies|denied|deny|says?|said|states?|stated|claims?|claimed|explains?|explained)\b', clause, re.I)
    if not report:
        return False
    proposition = clause[report.end():]
    if report.group().casefold() in {'denies', 'denied', 'deny'}:
        return bool(_LINK.search(proposition) or re.search(r'\b(?:affect|impact|jeopardi[sz]|breach)\w*\b', proposition, re.I))
    return bool(re.search(
        r"\b(?:not|never|cannot|can['’]t|couldn['’]t|wouldn['’]t|doesn['’]t)\s+"
        r'(?:be\s+)?(?:adversely\s+)?(?:affect(?:ed)?|impact(?:ed)?|jeopardi[sz]ed?|breach|depend(?:s|ent)?|linked|tied|conditional)\b|'
        r'\b(?:unrelated|unaffected)\b', proposition, re.I,
    ))


def _financing_connection(unit, finance, decision):
    """A stated possible effect answers 'could affect', not 'has happened'.

    Keep existing explicit dependency/uncertainty handling, but also read the
    causal words before the financing noun. Mere topic co-occurrence is not a
    link, and explicit doubt about the connection still remains Unknown.
    """
    if _reported_financing_denial(unit, finance):
        return None  # Keep the scoped clarification; Unknown would close it.
    clause = next((part for part in _scoped_clauses(unit)
                   if unit.find(part) <= finance.start() < unit.find(part) + len(part)), unit)
    start = finance.start() - unit.find(clause)
    auxiliary = (
        r'(?:(?:could|can|may|might|will|would|does?|did)\s+)?'
        r"(?:(?:not|never|cannot|can['’]t|couldn['’]t|wouldn['’]t|doesn['’]t|didn['’]t)\s+)?"
    )
    forward = re.search(
        rf'(?P<cause>.*?)\b(?P<link>{auxiliary}'
        r'(?:affects?|impacts?|jeopardi[sz]es?|breach(?:es)?)\b[^.!?;]{0,80})$',
        clause[:start], re.I,
    )
    backward = re.match(
        rf'\s+(?P<link>{auxiliary}be\s+'
        r'(?:adversely\s+)?(?:affected|impacted|jeopardi[sz]ed)\s+by)\s+(?P<cause>[^.!?;]+)',
        clause[start + len(finance.group()):], re.I,
    )
    relation = forward or backward
    if not relation or not _decision_reference(relation['cause'], decision):
        existing = _connection_value(clause[start:])
        if existing:
            return existing
        # PR #8's wider context helps when a dependency precedes the financing
        # noun. Keep this behind attribution/denial checks and the explicit
        # local effect parser, and require a reference to the current work.
        if _decision_reference(unit, decision):
            return _connection_value(unit, financing=True)
        return None
    if re.search(r"\b(?:unclear|unknown|uncertain|unsure|whether|do\s+not\s+know|don['’]t\s+know)\b", clause, re.I) or re.search(r'\b(?:may|might)\s+not\b', relation['link'], re.I):
        return 'Unknown'
    return 'No' if re.search(r"\b(?:not|never|cannot|can['’]t|couldn['’]t|wouldn['’]t|doesn['’]t|didn['’]t)\b", relation['link'], re.I) else 'Yes'


def _id(prefix, *parts):
    return prefix + '_' + hashlib.sha256('\x1f'.join(parts).casefold().encode()).hexdigest()[:14]


def _units(text):
    # A structured field is also a source unit when its line has no full stop.
    return [m.group().strip() for m in re.finditer(r"(?:\.(?=\d)|[^.!?\n])+(?:[.!?]|(?=\n|$))", text) if m.group().strip()]


def _scoped_clauses(unit):
    """Keep a later actor/technical assertion outside an earlier uncertainty."""
    return [part.strip() for part in re.split(
        r';|\b(?:but|whereas|while|although|however)\b|\band\s+(?=(?:I|you|we|he|she|they|my|your|our|the)\b)|,\s*(?=(?:I|you|we|he|she|they|my|your|our|the)\b)',
        unit, flags=re.I,
    ) if part.strip()]


def _hypothetical(unit):
    if _HYPOTHETICAL.search(unit) or _HISTORICAL.search(unit):
        return True
    if re.match(r"\s*if\b", unit, re.I):
        _, comma, report = unit.partition(',')
        return not comma or not re.search(r"\b(?:said|says|told|warned|I\s+was\s+told)\b", report, re.I)
    return False


def _negated(unit, start):
    return bool(re.search(r"\b(?:not|never|no|without|denies|denied)\b[^,;]{0,28}$", unit[max(0,start-65):start], re.I))


def _absent_actor(unit, start):
    # 'Do not tell the auditors' establishes a recipient, whereas 'no
    # auditors' does not establish their presence. Do not conflate the two.
    return bool(re.search(r'\b(?:not|no|without)\s+(?:(?:a|an|the|any)\s+)?$', unit[max(0,start-40):start], re.I))


def _financial_type(fragment):
    low = fragment.casefold()
    if any(word in low for word in ('shares', 'shareholding', 'equity', 'stock')): return 'Shareholding or ownership interest'
    if 'commission' in low: return 'Commission'
    if 'fee' in low or 'retainer' in low: return 'Consulting or other contingent fee'
    if 'bonus' in low: return 'Bonus or performance-related pay'
    return 'Reported financial incentive'


def _connection_value(clause, *, financing=False):
    """Reuse only an explicit outcome link, retaining its stated uncertainty."""
    if re.search(r'\b(?:unrelated|unaffected)\b|\bnot\s+(?:depend(?:s|ent)?|linked|tied|conditional)\b', clause, re.I):
        return 'No'
    if not _LINK.search(clause) and not (financing and _FINANCING_EFFECT.search(clause)) and not re.search(r'\b(?:if|unless)\b[^.!?;]{0,75}\b(?:accept|approve|recommend|favour|favor|sign|select)\w*\b', clause, re.I):
        return None
    if re.search(r'\b(?:may|might|could|unclear|unknown|uncertain|unsure|do\s+not\s+know|don[’\']t\s+know)\b[^.!?;]{0,55}\b(?:depend|link|tie|affect|conditional)', clause, re.I):
        return 'Unknown'
    return 'Yes'


def _directed_pressure(unit):
    """Recognise requests to bypass challenge, rather than ordinary review.

    A reported instruction is still not proof of coercion, a technical error
    or changed work. Protective instructions not to bypass review are excluded.
    """
    direction = re.search(r'\b(?:asks?|asked|instructs?|instructed|tells?|told|urges?|urged|demands?|demanded)\b[^.!?;]{0,35}\b(?:me|you|us)\b(?P<instruction>[^.!?;]{0,230})', unit, re.I)
    if not direction:
        return False
    instruction = direction['instruction']
    if re.search(r'\bnot\s+to\s+(?:challenge|question|test|examine|query)\b', instruction, re.I):
        return True
    acceptance = re.search(r'\b(?:accept|approve|sign\s+off|recommend|use)\b', instruction, re.I)
    if acceptance and not _negated(instruction, acceptance.start()):
        return bool(re.search(r'\b(?:without\s+(?:challenging|questioning|testing|examining|checking)|(?:ignore|overlook)\s+(?:the\s+)?(?:contrary|contradictory|conflicting|adverse)\s+evidence)\b', instruction, re.I))
    return False


def _undecided_action_choice(unit):
    """No action inferred from a question listing options still to be decided."""
    return bool(re.match(
        r'\s*(?:I|you|we)\s+(?:(?:still|currently)\s+)?'
        r'(?:need\s+to|have\s+to|must)\s+decide\s+whether\b',
        unit, re.I,
    ))


def _stage(unit):
    if re.search(r"\b(?:not\s+(?:yet\s+)?(?:completed|implemented|carried\s+out)|still\s+(?:planned|pending)|proposed|plan(?:ned)?\s+to|intend\s+to|requested|asked\s+for|will\s+(?:arrange|request|review)|in\s+progress)\b", unit, re.I):
        return 'Planned'
    # Absence or uncertainty about completion must not become an implemented
    # safeguard just because the sentence contains a completion verb.
    if re.search(r"\b(?:never|not)\s+(?:(?:been|actually)\s+)?(?:completed|implemented|carried\s+out)\b|\bno\s+(?:independent\s+)?(?:review|action|measure|safeguard)\s+(?:(?:has|had|have|was|were|been|ever)\s+){0,4}(?:completed|implemented|carried\s+out)\b", unit, re.I):
        return 'Unknown'
    if re.search(r"\b(?:unknown|unclear|unsure|uncertain|do\s+not\s+know|don['’]t\s+know)\b[^.!?;]{0,130}\b(?:completed|implemented|carried\s+out|reviewed|finished)\b", unit, re.I):
        return 'Unknown'
    if re.search(r"\b(?:completed|implemented|carried\s+out|has\s+reviewed|have\s+reviewed|was\s+reviewed|review\s+was\s+finished|removed\s+from|withdrew|withdrawn|ended\s+the|declined\s+the)\b", unit, re.I):
        return 'Implemented'
    return 'Unknown'


def _action_checks(unit):
    checks = {}
    patterns = {
        'independence': (r'\bindependent\s+(?:reviewer|partner|person|review)\b|\breviewer\s+(?:is|was)\s+independent\b', 'Yes'),
        'competence': (r'\b(?:competent|suitably\s+qualified|appropriately\s+qualified)\s+(?:reviewer|partner|person)\b', 'Yes'),
        'authority': (r'\b(?:can|could|has\s+authority\s+to)\s+require\s+changes\b', 'Yes'),
        'coverage': (r'\b(?:all\s+(?:linked|relevant)\s+(?:circumstances|threats|aspects)|entire\s+(?:judg(?:e)?ment|estimate))\b', 'All linked circumstances'),
        'timing': (r'\bbefore\s+(?:the\s+)?(?:decision|sign[-\s]?off|report\s+was\s+issued|work\s+was\s+relied\s+on|reliance)\b', 'Before reliance'),
        'outcome': (r'\bno\s+continuing\s+influence\s+(?:was\s+)?identified\b', 'No continuing influence identified'),
        'evidence': (r'\b(?:review\s+notes|review\s+records|written\s+review|signed\s+review|documented\s+findings|revised\s+conclusion)\b[^.!?]{0,65}\b(?:available|recorded|retained|show|confirm)\b', 'Records described'),
        'prior_work': (r'\b(?:no\s+prior\s+work\s+was\s+affected|no\s+work\s+had\s+been\s+affected)\b', 'No prior work was affected'),
    }
    for key,(pattern,value) in patterns.items():
        match = re.search(pattern,unit,re.I)
        if match and not _negated(unit,match.start()): checks[key]=value
    negative = re.search(r'\b(?:continuing\s+influence\s+(?:remains|was\s+identified)|review\s+failed|review\s+was\s+ineffective)\b',unit,re.I)
    if negative and not _negated(unit, negative.start()): checks['outcome']='Continuing influence remains'
    if re.search(r'\b(?:reviewer\s+(?:is|was)\s+not\s+independent|reviewer\s+has\s+a\s+conflict)\b',unit,re.I): checks['independence']='No'
    return checks


class LocalUnderstandingProvider:
    """Finite English grammars proposing literal, attributed source facts."""

    def understand(self, scenario):
        if not isinstance(scenario,str): raise TypeError('Scenario must be text.')
        if len(scenario)>MAX_SCENARIO_LENGTH:
            return UnderstandingResult((CaseActor('user','You',kind='professional'),),limitations=('Scenario exceeds the supported local text limit; enter focused structured facts.',))
        old=extract_context(scenario)
        units=_units(scenario)
        fields={}
        for unit in units:
            field = _context_field(unit)
            if field:
                name, value, status = field
                fields.setdefault(name, (value, unit, status))
        role = fields['role'][0] if 'role' in fields else old.context.role
        role_sources = (fields['role'][1],) if 'role' in fields else old.evidence['role']
        if 'role' not in fields and role == 'Unknown':
            compound_roles = dict(result for unit in units if (result := _compound_role(unit)))
            if len(compound_roles) == 1:
                role, excerpt = next(iter(compound_roles.items()))
                role_sources = (excerpt,)
        actors={'user':CaseActor('user','You',role='' if role=='Unknown' else role,kind='professional')}
        facts={}
        actions={}
        org_names={}
        family_ids={}
        employment={}

        def actor(label,role='',kind='person'):
            label=' '.join(label.strip(' ,:').split())
            low=label.casefold()
            if low in {'i','me','you','yourself','myself','user'}:return 'user'
            if low in {'my firm','your firm','our firm','the firm','firm'}: key='firm';label='Your firm';kind='organisation'
            elif low in {'company','manufacturing company','organisation','organization'} or re.fullmatch(r'(?:my|your|our|the)\s+(?:company|organisation|organization)',low): key='company';label='Manufacturing company' if 'manufacturing company' in scenario.lower() else 'Your organisation';kind='organisation'
            elif low=='listed client':key='client';label='Listed client';kind='organisation'
            elif low in {'cfo','chief financial officer'}:key='cfo';label='CFO';role=role or 'Chief financial officer'
            elif low in {'ceo','chief executive officer'}:key='ceo';label='CEO';role=role or 'Chief executive officer'
            elif low in {'external valuation firm','independent valuation firm','valuation firm'}:key='valuation_firm';kind='organisation';label=label[:1].upper()+label[1:]
            else:key=_id('actor',low)
            if key not in actors:actors[key]=CaseActor(key,label,role,kind)
            elif role and not actors[key].role:actors[key].role=role
            return key

        def fact(subject,predicate,value,unit,object_id='',status='reported',attribution=''):
            key=_id('fact',subject,predicate,object_id,value)
            if key not in facts:
                facts[key]=CaseFact(key,subject,predicate,value,object_id=object_id,source='scenario',excerpt=unit,status=status,attribution=attribution)
            return key

        def mentions(unit):
            out=[]
            for key,item in actors.items():
                if key=='user':continue
                candidates=[item.label]
                if key in {'firm','company','client'}:candidates+= {'firm':['firm'],'company':['company','organisation','organization'],'client':['client']}[key]
                if key.startswith('family_'):candidates += [key.removeprefix('family_')]
                if key=='cfo':candidates+=['chief financial officer']
                for name in candidates:
                    match=re.search(r'\b'+re.escape(name)+r'\b',unit,re.I)
                    if match:out.append((match.start(),key));break
            return sorted(out)

        def owner_at(unit,pos):
            prefix=unit[:pos]
            # A first-person quotation belongs to its explicitly named speaker.
            quote=re.search(r"\b(?:said|says|stated|explained|added|told\s+(?:me|you|us)|wrote)\s*[,;:]?\s*[\"“'](?P<speech>[^\"”']*)$",prefix,re.I)
            if quote:
                before=prefix[:quote.start()]
                prior=[key for _,key in mentions(before) if actors[key].kind!='organisation']
                if prior:return prior[-1]
                if re.search(r'\b(?:I|you)\s*$',before,re.I):return 'user'
                return actor('Quoted speaker',kind='unknown')
            prior=mentions(prefix)
            if re.search(r'\b(?:my|your|our)\s+(?:(?:annual|performance|personal|financial|year[-\s]end|sales|cash|deferred|individual|quarterly|monthly|related)\s+){0,7}$',prefix,re.I):
                return 'user'
            if re.search(r'\b(?:I|you|we)\s+(?:will\s+|would\s+|may\s+)?(?:receive|earn|own|hold|have|gain|benefit|am\s+paid|are\s+paid)\b[^;.!?]{0,45}$',prefix,re.I):
                return 'user'
            if prior:return prior[-1][1]
            return actor('Unspecified beneficiary',kind='unknown')

        def target_org(unit):
            present=[key for _,key in mentions(unit) if actors[key].kind=='organisation']
            return present[-1] if present else ''

        # Actors are established before attribution; source labels are never verified identities.
        for unit in units:
            if _hypothetical(unit):continue
            for m in _RELATIVE.finditer(unit):
                if _negated(unit,m.start()) or re.match(r"[’']s\s+(?:colleague|manager|friend)",unit[m.end():],re.I):continue
                relation=m['relation'].lower();key='family_'+relation
                actors.setdefault(key,CaseActor(key,'Your '+relation,'Family member'))
                family_ids[relation]=key
                fact('user','family_relationship',relation,unit,key)
            for m in _ORG.finditer(unit):
                label=m.group()
                # Sentence introducers are not part of registered names.
                label=re.sub(r'^(?:The|Your|Our|My|A)\s+','',label)
                org_names[label.casefold()]=actor(label,kind='organisation')
            for m in _GENERIC_ORG.finditer(unit):
                actor(m.group(),kind='organisation')
            for m in _TITLE.finditer(unit):
                if _absent_actor(unit,m.start()):continue
                if any(excerpt in unit and unit.find(excerpt)<=m.start()<unit.find(excerpt)+len(excerpt) for excerpt in role_sources):continue
                if re.match(r"[’']s\s+assistant\b",unit[m.end():],re.I):continue
                actor(m.group(),role=m.group())
            for m in _RECIPIENT_GROUP.finditer(unit):
                if not _absent_actor(unit, m.start()):
                    actor(m.group(), role=m.group(), kind='organisation')
            for m in re.finditer(r'\b(?:independent\s+(?:partner|reviewer)|(?:competent|qualified)\s+reviewer)\b', unit, re.I):
                if not _negated(unit, m.start()):
                    actor(m.group(), role=m.group())
            for clause in _scoped_clauses(unit):
                for m in _EMPLOYMENT.finditer(clause):
                    org=m['org'].strip()
                    org=re.sub(r'^(?:an?|the)\s+','',org,flags=re.I)
                    relative=family_ids.get(m['relation'].lower())
                    if relative and not _negated(clause,m.start()):
                        orgid=actor(org,kind='organisation')
                        employment[relative]=orgid
                        fact(relative,'employment','Employment at external organisation',clause,orgid)
        for name, (value, excerpt, status) in fields.items():
            fact('user',name,value,excerpt,status=status)
        if 'role' not in fields and role!='Unknown':
            excerpt=next(iter(role_sources), '')
            if excerpt:fact('user','role',role,excerpt)
        if 'decision' not in fields and old.context.decision!='Unknown':
            excerpts=old.evidence['decision']
            if excerpts:
                spans = [(scenario.find(text), len(text)) for text in excerpts if text in scenario]
                if spans:
                    start = min(offset for offset, _ in spans)
                    end = max(offset + length for offset, length in spans)
                    fact('user','decision',old.context.decision,scenario[start:end])

        for unit in units:
            if _hypothetical(unit):continue
            personal_mentions=[key for _,key in mentions(unit) if actors[key].kind!='organisation']
            org=target_org(unit)
            # Explicit provider work links make relative-employment cases distinct.
            if re.search(r'\b(?:review(?:ing)?|assess(?:ing)?|rely(?:ing)?\s+on|evaluat(?:e|ing))\b',unit,re.I) and re.search(r'\b(?:valuation|estimate|report|work|assessment)\b',unit,re.I) and org:
                if re.search(r'\bvaluations?\b', unit, re.I):
                    providers = _valuation_provider_ids(unit, actors)
                    if _user_provider_work(unit, role):
                        for provider in providers:
                            fact('user','professional_relationship','Reviewing or relying on provider work',unit,provider)
                else:
                    fact('user','professional_relationship','Reviewing or relying on provider work',unit,org)
            close=re.search(r'\b(?:close\s+(?:personal\s+)?friend(?:s)?|long[-\s]standing\s+friend)\b',unit,re.I)
            if close and not _negated(unit,close.start()):
                third_party=re.search(r"\b(?:of\s+the\s+(?:CEO|CFO)|(?:CEO|manager|director)[’']s\s+close\s+friend)\b",unit,re.I)
                linked=bool(re.search(r'\b(?:my|your|our)\s+close\b|\b(?:I\s+am|you\s+are|we\s+are)\s+close\s+friends?\s+with\b',unit,re.I)) or bool(re.search(r'\b(?:CFO|chief\s+financial\s+officer|director|partner)\s*,\s*a\s+close\s+(?:personal\s+)?friend',unit,re.I) and role!='Unknown')
                if linked and not third_party:
                    counterpart=next((key for key in personal_mentions if not key.startswith('family_')), '')
                    if counterpart:
                        fact('user','close_relationship','Close personal friendship',unit,counterpart)
                        fact('user','relationship_active','Yes',unit,counterpart)
            # Financial owners are located at the benefit mention, not inferred from a single global bucket.
            for benefit in _BENEFITS.finditer(unit):
                if _negated(unit,benefit.start()):continue
                owner=owner_at(unit,benefit.start())
                if owner=='user' and re.search(r'\b(?:bonus|pay|commission)\b[^.!?;]{0,40}\b(?:does\s+not|is\s+not|isn[’\']t|unrelated|unaffected)\b',unit,re.I):continue
                value=_financial_type(benefit.group())
                fid=fact(owner,'interest',value,unit,org,attribution=actors[owner].label)
                connection_clause = re.split(r'\s+and\s+(?:says?|said|warns?|asks?|tells?|my|your|our|the)\b',unit, maxsplit=1, flags=re.I)[0]
                connection = _connection_value(connection_clause)
                if connection:
                    fact(owner,'interest_connection',connection,unit,org,status='unknown' if connection=='Unknown' else 'reported')
            # Career consequences are interests without an invented monetary
            # reward. Require an explicit outcome/condition, rather than merely
            # treating every mention of a promotion as a conflict.
            for career in _CAREER.finditer(unit):
                clause = unit[career.start():]
                if _negated(unit, career.start()) or re.search(r'\b(?:does\s+not|is\s+not|unrelated|unaffected)\b[^.!?;]{0,35}\b(?:depend|link|tie|affect)|\bnot\s+(?:dependent|linked|tied|conditional)\b', clause, re.I):
                    continue
                connection = _connection_value(clause)
                if connection in {None, 'No'}:
                    continue
                owner = owner_at(unit, career.start())
                fact(owner,'interest','Promotion or career-related interest',unit,org,attribution=actors[owner].label)
                fact(owner,'interest_connection',connection,unit,org,status='unknown' if connection=='Unknown' else 'reported')
                if owner == 'user' and connection == 'Yes':
                    basis = _career_incentive_basis(unit, career.start())
                    if basis:
                        fact(owner, 'career_incentive_basis', basis, unit, org, attribution=actors[owner].label)
            # Financing is the organisation's interest when an organisation is
            # explicitly mentioned. It is not assigned to the professional as
            # a personal loan or personal financial reward.
            finance = _ORG_FINANCE.search(unit)
            decision = next((f.value for f in facts.values() if f.predicate == 'decision' and f.status == 'reported'), '')
            connection = _financing_connection(unit, finance, decision) if finance else None
            # A reported denial of the connection does not establish that the
            # organisation has no financing interest; keep its reported source.
            absent_finance = finance and re.search(
                r'\b(?:no|without|not\s+(?:have|hold))\s+(?:(?:a|an|the|any|known|current|existing)\s+){0,3}$',
                unit[:finance.start()], re.I,
            )
            if finance and not absent_finance and (not _negated(unit, finance.start()) or connection in {'No', 'Unknown'} or _reported_financing_denial(unit, finance)):
                prior_orgs = [key for _,key in mentions(unit[:finance.start()]) if actors[key].kind=='organisation']
                owner = prior_orgs[-1] if prior_orgs else org
                if owner:
                    value = 'Organisational financing or loan covenant interest'
                    fact(owner,'interest',value,unit,owner,attribution=actors[owner].label)
                    if connection:
                        fact(owner,'interest_connection',connection,unit,owner,status='unknown' if connection=='Unknown' else 'reported')
            commercial=_FIRM_INCENTIVE.search(unit)
            if commercial and not _negated(unit,commercial.start()):
                if re.search(r'\b(?:firm|practice|contract|client)\b',unit,re.I):
                    owner=actor('Your firm',kind='organisation')
                    target=actor('Listed client',kind='organisation') if 'listed client' in scenario.lower() else org
                    value='Firm contract renewal or client retention' if re.search(r'\b(?:contract|renewal|retention|retain)\b',unit,re.I) else 'Organisational fee income'
                else:
                    owner=actor('Your company',kind='organisation');target=org or owner;value='Organisational profit target'
                fact(owner,'interest',value,unit,target,attribution=actors[owner].label)
                if _LINK.search(unit):fact(owner,'interest_connection','Yes',unit,target)
            signal=extract_signals(unit,user_role=role)
            linked_career=re.search(r'\b(?:says?|told|warns?|warned)\b[^.!?;]{0,90}\b(?:my|your)\s+(?:promotion|job|career)\b[^.!?;]{0,65}\b(?:depends?|conditional|unless)\b[^.!?;]{0,90}\b(?:favour|favor|recommend|approv|accept|sign)\w*\b',unit,re.I)
            if signal.pressure=='Reported pressure or threatened consequences' or linked_career or _directed_pressure(unit):
                speaker=next((key for key in personal_mentions if not key.startswith('family_')), '')
                if not speaker:speaker=actor('Reported source of influence',kind='unknown')
                fact(speaker,'pressure',unit.rstrip('.!?'),unit,'user',attribution=actors[speaker].label)
            # A statement about a future valuation is a reported claim, never a prediction/fact of recovery.
            future_claim = re.search(r'\b(?:says?|said|claims?|claimed|believes?)\b',unit,re.I) and re.search(r'\b(?:may|might|could|will)\b[^.!?;]{0,65}\b(?:recover|improve|rise|increase)\b',unit,re.I)
            technical_verb = re.search(r'\b(?:says?|said|claims?|claimed|states?|stated|explains?|explained|maintains?|maintained|assumes?|assumed|forecasts?|projects?|believes?|estim\w*|notic\w*|observ\w*|identif\w*|found)\b',unit,re.I)
            technical_claim = technical_verb and not _negated(unit, technical_verb.start()) and re.search(r'\b(?:assumptions?|growth|discount\s+rate|yield|forecast|returns?|value|estimate|recovery)\b',unit,re.I)
            if future_claim or technical_claim:
                named = [key for _,key in mentions(unit)]
                speaker=personal_mentions[0] if personal_mentions else named[0] if named else 'user' if re.search(r'\b(?:I|you|we)\s+(?:have\s+)?(?:estimated|noticed|observed|identified|found|assumed|forecast|projected|believe|consider)\b', unit, re.I) or re.match(r'\s*(?:I|you|we)\b', unit, re.I) else actor('Reported claimant',kind='unknown')
                fact(speaker,'claim',unit.rstrip('.!?'),unit,attribution=speaker)
            evidence_gap = re.search(r'\b(?:not\s+yet|have\s+not|haven[’\']t|insufficient|lack\s+of|no)\b[^.!?;]{0,100}\b(?:supporting\s+evidence|evidence|documentation|records|support)\b', unit, re.I)
            if evidence_gap and re.search(r'\b(?:I|you|we)\b', unit, re.I):
                fact('user','claim',unit.rstrip('.!?'),unit,attribution='You')
            # Self-review and advocacy require their own supported mechanisms, not an audit-role keyword.
            selfreview=re.search(r'\b(?:review(?:ing)?|audit(?:ing)?|assess(?:ing)?)\b[^.!?;]{0,75}\b(?:my\s+own|our\s+own|your\s+own|I\s+(?:previously\s+)?prepared|you\s+(?:previously\s+)?prepared)\b|\b(?:I|you)\s+(?:prepared|developed|calculated)\b[^.!?]{0,120}\b(?:now|then)\b[^.!?]{0,55}\b(?:review|audit|assess)\s+(?:it|the\s+same|that|this)\b',unit,re.I)
            if selfreview and not _negated(unit,selfreview.start()):fact('user','self_review','Reviewing or relying on own earlier work',unit)
            advocacy=re.search(r'\b(?:I|you|we)\b[^.!?]{0,45}\b(?:promot(?:e|ed|ing)|advocat(?:e|ed|ing)|campaign(?:ed|ing)?\s+for|represented)\b[^.!?]{0,130}\b(?:now|then|also)\b[^.!?]{0,65}\b(?:objective|independent|assess|evaluat|review)\w*\b',unit,re.I)
            if advocacy and re.search(r'\b(?:assess|evaluat|review)\w*\b[^.!?]{0,25}\b(?:it|that|same|this)\b',unit,re.I) and not _negated(unit,advocacy.start()):fact('user','advocacy','Promoting a position while expected to assess it objectively',unit)
            # Explicit structured equivalents can be reused instead of being asked again.
            responsibility = _professional_responsibility(unit, role)
            if responsibility:
                fact('user','decision_responsibility',responsibility,unit)
            for owner, value in _authority_context(unit, actors):
                fact(owner, 'context', value, unit, attribution=actors[owner].label)
            for clause in _scoped_clauses(unit):
                if re.search(r'\b(?:I|you)\s+(?:have|has)\s+no\s+(?:involvement|responsibility)\b', clause, re.I) and not _authority_kind(clause):
                    fact('user','decision_responsibility','I have no involvement in this decision',unit)
            participation_clauses = _scoped_clauses(unit)
            for relative,employer in employment.items():
                relname=actors[relative].label.split()[-1]
                for clause in participation_clauses:
                    contact = _familiarity_contact(clause, relname, decision)
                    if contact:
                        fact(relative, 'familiarity_contact', contact, clause, 'user',
                             status='unknown' if contact == 'Unknown' else 'reported', attribution='user')
                    person = re.search(r'\b'+re.escape(relname)+r'\b',clause,re.I)
                    if person and re.match(r"[’']s\s+(?!(?:participation|involvement|role)\b)", clause[person.end():], re.I):
                        person = None  # A relative's firm is not the relative.
                    pronoun = len(employment)==1 and re.search(r'\b(?:she|he|they)\b',clause,re.I)
                    involvement = re.search(r'\b(?:participat|involv|prepared\s+the\s+valuation|worked\s+on\s+(?:this|the)\s+valuation)',clause,re.I)
                    if not (person or pronoun) or not involvement:
                        continue
                    if person and re.search(r'\b(?:works?\s+(?:for|at)|employed\s+(?:by|at)|employee\s+of)\b',clause[person.end():involvement.start()],re.I) and not re.search(r'\band\s+(?:also\s+)?(?:participat|involv|prepared|worked)',clause,re.I):
                        continue  # Work performed by an employer does not establish personal participation.
                    if re.search(r'\b(?:do\s+not\s+know|don[’\']t\s+know|unknown|unclear|not\s+known|unsure)\b',clause,re.I):value='Unknown';status='unknown'
                    elif re.search(r'\b(?:not|never|did\s+not|was\s+not)\b[^.!?;]{0,35}\b(?:participat|involv|work)|\bno\s+involvement\b',clause,re.I):value='No';status='reported'
                    else:value='Yes';status='reported'
                    fact(relative,'participation',value,clause.strip(),employer,status=status)
            if re.search(r'\b(?:I|you)\s+(?:have\s+not|did\s+not|have\s+never)\s+changed\s+(?:any\s+)?(?:work|recommendation|judg(?:e)?ment)',unit,re.I):fact('user','work_changed','No',unit)
            elif re.search(r'\b(?:I|you)\s+(?:have\s+|already\s+)?changed\s+(?:my|your|the)\s+(?:work|recommendation|judg(?:e)?ment)\b[^.!?]{0,80}\b(?:pressure|request|instruction)',unit,re.I):fact('user','work_changed','Yes',unit)

            # Existing actions are records of proposals or implementation, never proof of effectiveness.
            if re.search(r'\b(?:no\s+(?:relevant\s+)?action\s+(?:has\s+been|was)\s+taken|I\s+have\s+taken\s+no\s+action)\b',unit,re.I):
                action=CaseAction(_id('action','none',unit),'No relevant action reported as taken','none','Not Taken',source='scenario',excerpt=unit)
                actions[action.id]=action
                continue
            # An undecided choice is not a proposed, requested or implemented action.
            # Do not turn a menu of options into a specific safeguard record.
            if _undecided_action_choice(unit):
                continue
            kind=''
            if re.search(r'\b(?:independent\s+review|review\s+by\s+(?:an?\s+)?independent|independent\s+(?:partner|reviewer)\b[^.!?]{0,50}\b(?:completed|reviewed|review))',unit,re.I):kind='independent_review'
            elif re.search(r'\b(?:removed\s+(?:me|you)\s+from\s+(?:the\s+)?decision|I\s+was\s+removed\s+from|I\s+have\s+withdrawn\s+from\s+the\s+decision)',unit,re.I):kind='remove_from_decision'
            elif re.search(r'\b(?:declined|ended|withdrew\s+from)\s+(?:the\s+)?(?:engagement|activity|assignment)',unit,re.I):kind='decline'
            elif re.search(r'\b(?:I|you)\s+(?:have\s+)?(?:escalated|reported)\b[^.!?]{0,90}\b(?:audit\s+committee|independent\s+partner|board|regulator)',unit,re.I):kind='escalate'
            elif re.search(r'\b(?:I|you)\s+(?:have\s+)?disclosed\s+(?:the\s+)?(?:relationship|interest|conflict|circumstances)',unit,re.I):kind='disclose'
            elif re.search(r'\b(?:I|you)\s+(?:have\s+)?documented\s+(?:the\s+)?(?:concern|conflict|circumstances|issue)',unit,re.I):kind='document'
            elif re.search(r'\b(?:bonus|fee|incentive|financial\s+interest)\b[^.!?]{0,50}\b(?:removed|eliminated|cancelled|ended)\b',unit,re.I):kind='eliminate'
            if kind:
                if re.match(r'\s*(?:I|you|we)\b', unit, re.I):
                    action_actor = 'user'
                else:
                    named = [key for _,key in mentions(unit) if actors[key].kind != 'organisation']
                    action_actor = named[0] if named else actor('Person carrying out the action (not established)',kind='unknown')
                action=CaseAction(_id('action',kind,unit),unit.rstrip('.!?'),kind,_stage(unit),actor_id=action_actor,source='scenario',excerpt=unit,checks=_action_checks(unit))
                if action.checks.get('evidence') == 'Records described':
                    action.evidence_detail=unit
                actions[action.id]=action
        # A clearly stated professional activity is useful even when its job
        # title/topic is outside the older context extractor's vocabulary.
        if not any(item.predicate == 'decision' for item in facts.values()):
            for unit in units:
                if _hypothetical(unit):
                    continue
                activity = re.search(
                    r"\b(?:I|you|we)\s+(?:(?:must|need\s+to|have\s+to|now|independently)\s+){0,2}"
                    r"(?P<work>(?:compare|shortlist|assess|evaluate|recommend|review|approve|prepare|audit|select|estimate|value)\b[^.!?;]{3,200})",
                    unit, re.I,
                )
                if activity and not _negated(unit, activity.start()):
                    fact('user','decision',activity['work'].strip(),activity['work'])
                    break
            if not any(item.predicate == 'decision' for item in facts.values()):
                direct = next((item for item in facts.values() if item.predicate in {'self_review','advocacy'}), None)
                if direct:
                    fact('user','decision',direct.excerpt.rstrip('.!?'),direct.excerpt)
        result=UnderstandingResult(tuple(actors.values()),tuple(facts.values()),tuple(actions.values()),(
            'Local English grammars can miss unfamiliar wording and attribution; review the reported facts and add corrections.',
            'No facts or documents have been independently verified by this application.',
        ))
        return validate_understanding(scenario,result)


def validate_understanding(scenario, result):
    """Constrain any provider to supported, literal, unverified source proposals.

    This is a provider-neutral boundary, not a factual authentication service.
    Imported/user edits use their own validation path; model/provider proposals
    cannot confer user review, verification, effectiveness or assessment status.
    """
    if not isinstance(scenario,str) or not isinstance(result,UnderstandingResult):
        raise TypeError('The understanding provider must return supported source records.')
    actors=[];seen=set();warnings=list(result.limitations)
    for candidate in result.actors[:500]:
        if not isinstance(candidate,CaseActor) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',candidate.id) or not isinstance(candidate.label,str) or not candidate.label.strip() or len(candidate.label)>1000:continue
        if candidate.kind not in {'person','organisation','organization','professional','unknown'} or candidate.id in seen:continue
        actors.append(deepcopy(candidate));seen.add(candidate.id)
    if 'user' not in seen:actors.insert(0,CaseActor('user','You',kind='professional'));seen.add('user')
    facts=[];ids=set()
    for candidate in result.facts[:2000]:
        if not isinstance(candidate,CaseFact) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',candidate.id) or candidate.id in ids:continue
        if candidate.subject not in seen or candidate.object_id and candidate.object_id not in seen:continue
        if candidate.predicate not in PREDICATES or candidate.source!='scenario' or candidate.status not in {'reported','unknown','disputed','denied'}:continue
        if not isinstance(candidate.value,str) or not candidate.value.strip() or len(candidate.value)>100000:continue
        if not isinstance(candidate.excerpt,str) or not candidate.excerpt or candidate.excerpt not in scenario:continue
        item=deepcopy(candidate);item.reviewed=False;item.revision=0;item.depends_on=()
        facts.append(item);ids.add(item.id)
    actions=[];ids=set()
    for candidate in result.actions[:500]:
        if not isinstance(candidate,CaseAction) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',candidate.id) or candidate.id in ids:continue
        if candidate.kind not in ACTION_KINDS or candidate.stage not in ACTION_STAGES or candidate.actor_id not in seen or candidate.source!='scenario':continue
        if not isinstance(candidate.excerpt,str) or not candidate.excerpt or candidate.excerpt not in scenario:continue
        if _undecided_action_choice(candidate.excerpt):continue
        item=deepcopy(candidate);item.reviewed=False;item.basis_signature='';item.threat_ids=();item.revision=0
        # A provider cannot claim unsupported implementation or effective checks.
        literal_stage=_stage(item.excerpt)
        item.stage='Not Taken' if item.kind=='none' and re.search(r'\bno\s+(?:relevant\s+)?action\b',item.excerpt,re.I) else literal_stage
        item.checks=_action_checks(item.excerpt)
        item.evidence_detail=item.excerpt if item.checks.get('evidence')=='Records described' else ''
        actions.append(item);ids.add(item.id)
    if len(facts)!=len(result.facts) or len(actions)!=len(result.actions):warnings.append('Unsupported or unanchored provider proposals were excluded; review the scenario and add any missing facts.')
    return UnderstandingResult(tuple(actors),tuple(facts),tuple(actions),tuple(dict.fromkeys(warnings)))
