"""Local mention and activity extraction, with literal source evidence.

These rules propose context, never an ethical finding or an independently
verified fact. They combine title/role grammars, explicit actor cues and generic
professional-action patterns rather than matching a complete example scenario.
"""

from dataclasses import dataclass
import re


_ROLE_BASE = (
    r"(?:chief\s+(?:financial|executive|operating|compliance)\s+officer|"
    r"head\s+of\s+(?:finance|purchasing|procurement|sales|claims|compliance|audit|operations)|"
    r"(?:financial\s+reporting|financial|management|cost|forensic|chartered|tax|group)\s+accountant|"
    r"(?:financial|finance|credit|investment|risk|procurement|compliance|grant|valuation|research|insurance|claims)\s+analyst|"
    r"(?:financial|finance|stock|credit)\s+controller|"
    r"(?:audit|engagement)\s+(?:manager|partner|senior|associate)|"
    r"(?:procurement|purchasing|finance|financial|sales|warehouse|claims|branch|operations|line|compliance|credit|loan|grant|payroll|risk|fund|project|production|hr|human\s+resources)\s+(?:manager|director|officer|supervisor|specialist|lead)|"
    r"(?:internal|external|statutory|lead)\s+auditor|"
    r"(?:property|independent|chartered)\s+(?:valuer|surveyor)|"
    r"(?:insurance|chief)\s+actuary|"
    r"tax\s+(?:advi[sz]er|consultant)|(?:legal|general)\s+counsel|insurance\s+broker|"
    r"(?:chair(?:person)?|member)\s+of\s+(?:the\s+)?(?:selection|recruitment|audit|ethics)\s+(?:panel|committee)|"
    r"(?:hiring|selection|recruitment)\s+panel\s+(?:member|chair)|"
    r"accountant|auditor|actuary|valuer|surveyor|treasurer|bookkeeper|solicitor|lawyer|underwriter|trustee|"
    r"manager|supervisor|director|CFO|CEO|COO)"
)
ROLE_PATTERN = rf"(?:(?:senior|junior|assistant|deputy)\s+)?{_ROLE_BASE}"
_ORG = (
    r"(?:listed\s+(?:client|company)|manufacturing\s+company|audit\s+firm|"
    r"community\s+bank|insurance\s+company|local\s+government|"
    r"company|firm|organisation|organization|bank|charity)"
)
_NAMED_ORG = r"(?-i:[A-Z][A-Za-z0-9&’'-]*(?:\s+[A-Z][A-Za-z0-9&’'-]*){0,4})"
_SUFFIX = rf"(?:\s+(?:of|at|for|within)\s+(?:(?:a|an|the|our)\s+)?(?:{_ORG}|{_NAMED_ORG}))?"
_SELF = re.compile(
    rf"\b(?:I\s+(?:(?:now|currently)\s+)?(?:am|work\s+as|serve\s+as|act\s+as)|I['’]m|"
    rf"you\s+(?:(?:now|currently)\s+)?(?:are|work\s+as|serve\s+as)|you['’]re|"
    rf"(?:my|your)\s+(?:role|position|job)\s+is|I\s+am\s+employed\s+as)\s+"
    rf"(?:(?:now|currently)\s+)?(?:(?:a|an|the)\s+)?(?P<role>(?P<title>{ROLE_PATTERN}){_SUFFIX})\b",
    re.I,
)
_AS = re.compile(rf"\bAs\s+(?:(?:a|an|the)\s+)?(?P<role>(?P<title>{ROLE_PATTERN}){_SUFFIX})\s*,\s*(?:I|you)\b", re.I)
_ALTERNATIVE = re.compile(rf"\s+(?:or|and)\s+(?:(?:a|an|the)\s+)?(?P<title>{ROLE_PATTERN})\b", re.I)
_GROUP = (
    r"(?:audit\s+committee|board\s+of\s+directors|board|"
    r"(?:audit|finance|tax\s+advisory|tax|sales|management|procurement|purchasing|valuation|claims)\s+team|"
    r"senior\s+management|management|"
    rf"{_ORG}|"
    r"heads\s+of\s+(?:finance|purchasing|procurement|sales|claims|compliance|audit|operations)|"
    r"actuaries|"
    r"hiring\s+panel|selection\s+panel|trustees|regulator|"
    r"suppliers?|vendors?|bidders?|clients?|customers?|lenders?|bank|company|firm|employer|charity|candidates?|applicants?)"
)
# A recipient is relevant even when disclosure to them is being discouraged.
# Plural titles retain their literal wording, without assuming an employer or
# qualifying an unqualified "auditors" as external/statutory auditors.
_TITLE = re.compile(rf"\b(?:{ROLE_PATTERN}s?|{_GROUP})\b", re.I)
_RELATIVE = re.compile(r"\b(?:my|your|our)\s+(?:spouse|wife|husband|brother|sister|mother|father|parent|cousin|(?:close\s+)?friend|partner)\b", re.I)
_NAME = r"(?:(?:Dr|Mr|Mrs|Ms|Prof)\.?\s+)?[A-Z][A-Za-z’'-]*(?:\s+[A-Z][A-Za-z’'-]*){0,2}"
_NOT_NAMES = set("The My Your Our I You We A An However Instead Therefore Meanwhile Also Today Yesterday Tomorrow Then But And When If Although Before After Because Management Revenue Finance Asked Said Told Warned Insists North South Either".split())
_ORG_NAME = r"[A-Z][A-Za-z0-9&’'-]*(?:\s+[A-Z][A-Za-z0-9&’'-]*){0,4}"
_ORG_CUES = re.compile(
    rf"\b(?P<cue>(?i:suppliers?|vendors?|bidders?|customers?|clients?|lenders?|companies|banks?))\s+"
    rf"(?P<names>{_ORG_NAME}(?:\s+(?:and|&)\s+{_ORG_NAME})*)|"
    rf"\b(?P<bidcue>(?i:bids?|tenders?|quotations?|loans?|contracts?|applications?))\s+(?i:from|by|for|to)\s+"
    rf"(?P<bidnames>{_ORG_NAME}(?:\s+(?:and|&)\s+{_ORG_NAME})*)"
)
_ORG_AFTER_NAMES = re.compile(
    rf"\b(?P<names>{_ORG_NAME}(?:\s+(?:and|&)\s+{_ORG_NAME})*)\s+"
    rf"(?i:are|is|as)\s+(?i:(?:the|a|an|our|competing|potential|shortlisted|rival|current|existing)\s+)*"
    rf"(?P<party_role>(?i:suppliers?|vendors?|bidders?|customers?|clients?|lenders?|companies|banks?))\b"
)
_APPLICANTS = re.compile(
    rf"\b{_ORG_NAME}(?:\s+(?:and|&)\s+{_ORG_NAME})*\s+(?:have|has)\s+"
    r"(?:applied|bid|tendered|submitted\s+(?:a\s+)?(?:bid|application|proposal))\b"
)
_AFFILIATION = re.compile(
    rf"\b(?i:trustee|director|owner|partner|shareholder|employee)\s+(?i:at|of|in)\s+{_ORG_NAME}\b"
)
_LEGAL_ORG = re.compile(rf"\b{_ORG_NAME}\s+(?:Ltd|Limited|PLC|Inc|Bank|Insurance|Foundation|Council|Supplies|Tools|Mutual)\b")
_BACKGROUND = re.compile(r"\b(?:last\s+year|previously|historically|unrelated|prior\s+case|hypothetical\s+example)\b", re.I)
_START_HYPOTHETICAL = re.compile(r"^\s*(?:if\b|suppos(?:e|ing)\b|imagin(?:e|ing)\b|hypothetically\b|perhaps\b|maybe\b|(?:could|might|would)\s+(?:the|my|your|our)\b)", re.I)
_UNCERTAIN_SELF = re.compile(
    rf"\b(?:I|you|we)\s+(?:might|may|could)\s+(?:(?:be|become|work\s+as|serve\s+as)\s+(?:(?:a|an|the)\s+)?{ROLE_PATTERN}\b|consider\b)",
    re.I,
)
_NEGATIVE_BEFORE = re.compile(r"\b(?:not|no|neither|without|no\s+longer)\s+(?:(?:a|an|the|any)\s+)?$", re.I)
_NOT_INVOLVED = re.compile(r"^\s*,?\s*(?:is|was|are|were|remains?|will\s+be)\s+(?:not|never|no\s+longer)\s+(?:involved|relevant|part\s+of|connected)", re.I)


@dataclass(frozen=True)
class EntityResult:
    role: str
    parties: str
    decision: str
    evidence: dict[str, tuple[str, ...]]
    limitations: tuple[str, ...] = ()


def _clean(value):
    return " ".join(value.split())


def _display(value):
    value = _clean(value)
    return value.upper() if value.lower() in {"cfo", "ceo", "coo"} else value[:1].upper() + value[1:]


def _unique(values):
    result, seen = [], set()
    for value in values:
        key = _clean(value).casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _sentences(text):
    # Each string is an exact slice of source, so matches remain auditable.
    return [m.group() for m in re.finditer(r"(?:\b(?:Dr|Mr|Mrs|Ms|Prof)\.|[^.!?\n])+(?:[.!?]|$)", text) if m.group().strip()]


def _clauses(sentence):
    return [piece for piece in re.split(r";|\bbut\b|\bwhereas\b|\bhowever\b", sentence, flags=re.I) if piece.strip()]


def _hypothetical(clause):
    return bool(_START_HYPOTHETICAL.search(clause) or _UNCERTAIN_SELF.search(clause))


def _self_matches(sentence):
    return sorted((m for pattern in (_SELF, _AS) for m in pattern.finditer(sentence)), key=lambda m: m.start())


def _alternatives(sentence, start):
    while match := _ALTERNATIVE.match(sentence, start):
        # "I am an auditor and the CFO warned me" is a separate actor,
        # not a second claim about the user's own professional role.
        if re.match(r"\s+(?:asked|asks|said|says|warned|warns|insists|insisted|told|wants|has|is)\b", sentence[match.end():], re.I):
            break
        yield match
        start = match.end()


def _role_data(sentences):
    candidates, evidence, spans = [], [], {}
    for number, sentence in enumerate(sentences):
        local = []
        for match in _self_matches(sentence):
            local.append(match.span('title'))
            alternatives = list(_alternatives(sentence, match.end('role')))
            local.extend(m.span('title') for m in alternatives)
            prefix = sentence[:match.start()]
            local_prefix = re.split(r";|\bbut\b|\bwhereas\b|\bhowever\b", prefix, flags=re.I)[-1]
            if (
                _hypothetical(local_prefix + match.group()) or _BACKGROUND.search(local_prefix)
                or re.search(r"\b(?:if|suppose|imagine|said|says|told|claimed|claims|wrote)\b", local_prefix, re.I)
                or re.match(r"['’]s\b", sentence[match.end('role'):])
            ):
                continue
            title = match['title']
            suffix = match['role'][len(title):]
            # Normalise a professional title's case while retaining a named
            # employer verbatim ("at Ridgeway Bank").
            candidates.append(_display(title.lower()) + suffix)
            evidence.append(match.group())
            for alternative in alternatives:
                candidates.append(_display(alternative['title'].lower()))
                evidence.append(alternative.group())
        spans[number] = local
    candidates = _unique(candidates)
    if len(candidates) == 1:
        return candidates[0], _unique(evidence), spans, ()
    limitation = ("More than one professional role is stated; confirm which role applies to this decision.",) if candidates else ()
    return "Unknown", (), spans, limitation


def _good_name(name):
    return bool(name) and not any(part in _NOT_NAMES for part in name.split()) and not re.fullmatch(ROLE_PATTERN, name, re.I)


def _party_phrase(sentence, match):
    start, end = match.span()
    prefix_start = max(0, start - 100)
    prefix = sentence[prefix_start:start]
    distinct = re.search(r"\b(?:another|a\s+second|a\s+different|the\s+other)\s+$", prefix, re.I)
    if distinct:
        return sentence[prefix_start + distinct.start():end], end, None
    # Prefer a title's own following name. In a list such as "sales
    # director Monica Hale, warehouse manager Joel Noor", the preceding
    # person's name belongs to a different role.
    after = re.match(rf"(?:\s*,\s*|\s+)(?P<name>{_NAME})\b", sentence[end:])
    if after and _good_name(after['name']):
        new_end = end + after.end('name')
        return sentence[start:new_end], new_end, after['name']
    before = re.search(rf"\b(?P<name>{_NAME})(?:,\s+|\s+is\s+|['’]s\s+)(?:(?:the|my|your|our)\s+)?$", prefix)
    if before and _good_name(before['name']):
        return sentence[prefix_start + before.start('name'):end], end, before['name']
    # Named legal organisations such as "Ridgeway Bank".
    if re.fullmatch(r"bank|company|firm|charity|foundation|council", match.group(), re.I):
        before = re.search(rf"\b(?P<name>{_NAME})\s+$", prefix)
        if before and _good_name(before['name']):
            return sentence[prefix_start + before.start('name'):end], end, before['name']
    return match.group(), end, None


def _distinct_party_labels(labels):
    """Remove an unqualified organisation alias when one clear referent exists.

    This does not merge two named organisations or a stated "another company".
    Source excerpts are retained separately, including the generic reference.
    """
    unique = _unique(labels)
    aliases = set()
    for generic in ("company", "firm", "bank", "client", "charity", "employer"):
        specific = [
            label for label in unique
            if not label.startswith("You — ")
            and label.casefold() != generic
            and re.search(rf"\b{generic}$", label, re.I)
            and not re.match(r"(?:another|a\s+second|a\s+different|the\s+other)\b", label, re.I)
        ]
        if len(specific) == 1:
            aliases.add(generic)
    return tuple(label for label in unique if label.casefold() not in aliases)


def _org_role(label):
    label = label.casefold()
    return {"companies": "company"}.get(label, label[:-1] if label.endswith('s') else label)


def _org_names(names):
    # The name-list grammar already limits these to proper-name source spans.
    # Keep ampersands within a name; they can belong to a registered name.
    return tuple(piece.strip() for piece in re.split(r"\s+and\s+", names) if piece.strip())


def _parties(sentences, role, role_evidence, spans):
    mentions, excluded, named_actors, replaced_labels = [], set(), {}, set()
    for number, sentence in enumerate(sentences):
        for clause in _clauses(sentence):
            if _hypothetical(clause) or _BACKGROUND.search(clause):
                continue
            offset = sentence.find(clause)
            for match in _TITLE.finditer(clause):
                absolute = offset + match.start()
                if any(start <= absolute < end for start, end in spans[number]):
                    continue
                prefix = clause[:match.start()]
                if _NEGATIVE_BEFORE.search(prefix[-60:]):
                    continue
                fragment, end, name = _party_phrase(clause, match)
                identity = (match.group().casefold(), name.casefold() if name else None)
                if _NOT_INVOLVED.match(clause[end:]):
                    excluded.add(identity)
                    continue
                if re.match(r"\s+(?:could|may|might|would)\s+(?:be|become|discuss|advise|participate)\b", clause[end:], re.I):
                    continue
                mentions.append((identity, fragment, fragment if name else _display(fragment)))
            for match in _RELATIVE.finditer(clause):
                if not _NOT_INVOLVED.match(clause[match.end():]):
                    mentions.append(((match.group().casefold(), None), match.group(), _display(match.group())))
            for pattern in (_ORG_CUES, _ORG_AFTER_NAMES, _LEGAL_ORG, _APPLICANTS, _AFFILIATION):
                for match in pattern.finditer(clause):
                    if _NOT_INVOLVED.match(clause[match.end():]):
                        continue
                    fragment = match.group()
                    groups = match.groupdict()
                    names = groups.get('names') or groups.get('bidnames')
                    explicit_role = groups.get('cue') or groups.get('party_role')
                    if pattern is _LEGAL_ORG:
                        names = fragment
                    if names:
                        # Consolidate grouped cues and individual legal-name
                        # matches by actor. A bid cue is evidence for a named
                        # actor, not another party or an assumed supplier role.
                        replaced_labels.add(_clean(fragment).casefold())
                        for name in _org_names(names):
                            key = name.casefold()
                            actor = named_actors.setdefault(key, {'name': name, 'roles': []})
                            if explicit_role:
                                actor['roles'].append(_org_role(explicit_role))
                            mentions.append(((key, None), fragment, name))
                    else:
                        mentions.append(((fragment.casefold(), None), fragment, _clean(fragment)))
    labels = [f"You — {role}"] if role != "Unknown" else []
    evidence = list(role_evidence)
    represented_roles = {value for actor in named_actors.values() for value in actor['roles']}
    for identity, fragment, label in mentions:
        if identity in excluded:
            continue
        evidence.append(fragment)
        actor = named_actors.get(label.casefold())
        if actor:
            roles = _unique(actor['roles'])
            labels.append(actor['name'] + (" — " + ", ".join(roles) if roles else ""))
        elif label.casefold() not in replaced_labels and _org_role(label) not in represented_roles:
            # The title scanner can also see the first name within a grouped
            # cue ("Suppliers Northstar and Beacon"). It is the same actor,
            # whose complete named-role entry has already been recorded.
            repeated_role = any(
                label.casefold().endswith(" " + key)
                and _org_role(label[:-(len(key) + 1)]) in candidate['roles']
                for key, candidate in named_actors.items()
            )
            if not repeated_role:
                labels.append(label)
    return "; ".join(_distinct_party_labels(labels)) if labels else "Unknown", _unique(evidence)


_TOPICS = (
    ("revenue", re.compile(r"\b(?:aggressive\s+)?revenue\s+recognition(?:\s+(?:judg(?:e)?ment|policy|treatment))?\b|\brecognis(?:e|ing|ation\s+of)\s+(?:the\s+)?revenue\b|\brecogniz(?:e|ing|ation\s+of)\s+(?:the\s+)?revenue\b", re.I)),
    ("inventory", re.compile(r"\b(?:inventory|stock)\s+(?:write[-\s]?downs?|(?:re)?valuation|impairment|provision)\b|\b(?:write|writing|written)\s+down\s+(?:of\s+)?(?:(?:the|our|any)\s+)?(?:(?:obsolete|damaged|excess|unsaleable|unsellable|slow[-\s]moving)\s+)?(?:inventory|stock)\b|\bwrite[-\s]?down\s+of\s+(?:the\s+)?(?:(?:obsolete|damaged|excess)\s+)?(?:inventory|stock)\b|\b(?:valuation|impairment|net\s+realisable\s+value|net\s+realizable\s+value)\s+of\s+(?:the\s+)?(?:inventory|stock)\b", re.I)),
    ("audit_opinion", re.compile(r"\baudit\s+opinion\b|\baudit\s+(?:report|conclusion)\b", re.I)),
    ("supplier", re.compile(r"\b(?:supplier|vendor)\s+(?:approval|selection)\b|\b(?:approve|select)\s+(?:a|the)\s+(?:supplier|vendor)\b|\bapproval\s+of\s+(?:a|the)\s+supplier\b", re.I)),
    ("impairment", re.compile(r"\bgoodwill\s+impairment\b|\bimpairment\s+of\s+goodwill\b", re.I)),
    ("provision", re.compile(r"\b(?:litigation|warranty|legal)\s+provision\b", re.I)),
    ("reserve", re.compile(r"\b(?:insurance|claims?|loss)\s+reserves?\b", re.I)),
    ("loan", re.compile(r"\b(?:loan|credit|mortgage)\s+(?:approval|assessment|application|decision)\b", re.I)),
    ("valuation", re.compile(r"\b(?:property|business|asset|pension)\s+valuation\b", re.I)),
    ("grant", re.compile(r"\bgrant\s+(?:award|approval|assessment|application|allocation)\b", re.I)),
    ("payroll", re.compile(r"\bpayroll\s+(?:approval|adjustment|review)\b", re.I)),
)
_VERBS = (
    r"(?:review|evaluate|assess|approve|select|choose|recommend|estimate|value|"
    r"sign\s+off|certify|prepare|recognis[e]|recogniz[e]|award|authorise|authorize|"
    r"determine|calculate|decide|test|audit|report\s+on|investigate|verify|"
    r"write\s+down|reduce|lower|inflate|understate|overstate|omit|ignore|suppress|backdate|"
    r"delay|defer|postpone|accelerate|bring\s+forward|"
    r"raise|disclose|report|inform|tell|notify|escalate|communicate|discuss|conceal|withhold)"
)
_REQUEST_WORDS = r"(?:ask(?:ed|s)?|tell(?:s)?|told|order(?:ed|s)?|instruct(?:ed|s)?|require(?:d|s)?|pressure(?:d|s)?|urge(?:d|s)?|request(?:ed|s)?)"
_ACTION = re.compile(
    rf"\b(?:I|you|we)\s+(?:(?:must|should|need\s+to|have\s+to|am\s+required\s+to|are\s+required\s+to|will|am\s+to|are\s+to)\s+)?"
    rf"(?P<action>{_VERBS}\b[^.!?;\n]{{0,240}})|"
    rf"\b(?:my|your|our)\s+(?:task|assignment|decision|responsibility)\s+is\s+(?:to\s+)?"
    rf"(?P<task>{_VERBS}\b[^.!?;\n]{{0,240}})|"
    rf"\b{_REQUEST_WORDS}\s+(?:me|you|us)\s+"
    rf"(?P<requested>(?:not\s+)?to\s+{_VERBS}\b[^.!?;\n]{{0,240}})|"
    rf"\b{_REQUEST_WORDS}\s+that\s+(?:I|you|we)\s+"
    rf"(?P<request_clause>(?:(?:do\s+not|not|should\s+not|should)\s+)?{_VERBS}\b[^.!?;\n]{{0,240}})|"
    rf"\b(?:I|you|we)\s+(?:was|were|am|are)\s+(?:asked|told|instructed|required|expected)\s+"
    rf"(?P<passive>(?:not\s+)?to\s+{_VERBS}\b[^.!?;\n]{{0,240}})",
    re.I,
)
_GERUND_ACTION = re.compile(
    rf"\b(?:responsible\s+for|tasked\s+with|(?:I|you|we)\s+(?:am|are)|{ROLE_PATTERN})\s+"
    r"(?P<action>(?:reviewing|evaluating|assessing|approving|selecting|choosing|recommending|estimating|valuing|certifying|preparing|determining|calculating|auditing|investigating|deciding|writing\s+down|signing\s+off|reporting\s+on)\b[^.!?;\n]{0,240})", re.I,
)
_CHANGED_OR_DISCLOSURE_REQUEST = re.compile(
    r"^(?:(?:not|do\s+not|should\s+not)\s+(?:to\s+)?|(?:to\s+)?(?:delay|defer|postpone|accelerate|bring\s+forward|reduce|lower|inflate|understate|overstate|omit|ignore|suppress|backdate|raise|disclose|report|inform|tell|notify|escalate|communicate|discuss|conceal|withhold)\b)",
    re.I,
)


def _absent_topic(clause, match):
    before, after = clause[:match.start()], clause[match.end():]
    return bool(
        re.search(r"\bno\s+(?:professional\s+)?(?:decision|activity|issue|judg(?:e)?ment)\s+(?:about|regarding|on|involving)\s*$", before, re.I)
        or re.search(r"\b(?:issue|decision|activity|question)\s+(?:is\s+not|isn['’]t|was\s+not|wasn['’]t)\s*$", before, re.I)
        or re.match(r"\s+(?:is|was)\s+not\s+(?:involved|relevant|under\s+consideration|the\s+issue|part\s+of)", after, re.I)
        or re.search(r"\bnot\s+about\s*$", before, re.I)
        or (re.search(r"\bno\s*$", before, re.I) and re.match(r"\s+(?:issue|decision|activity)\b", after, re.I))
    )


def _decision(sentences):
    topics, actions, evidence = {}, [], []
    ambiguous = False
    for sentence in sentences:
        for clause in _clauses(sentence):
            if _BACKGROUND.search(clause) or _hypothetical(clause):
                continue
            if re.search(r"\b(?:might|may|could)\s+(?:consider|involve|be\s+about)\b|\beither\b", clause, re.I):
                ambiguous = True
                continue
            if re.search(r"\b(?:could|might|may|would)\s+(?:be\s+involved|discuss|advise)\b", clause, re.I):
                continue
            local_topics = []
            for category, pattern in _TOPICS:
                for match in pattern.finditer(clause):
                    if not _absent_topic(clause, match):
                        topics.setdefault(category, []).append(match.group())
                        local_topics.append(match.group())
                        evidence.append(match.group())
            for pattern in (_ACTION, _GERUND_ACTION):
                for match in pattern.finditer(clause):
                    raw = next(value for value in match.groupdict().values() if value is not None)
                    fragment = re.split(
                        r"\s+(?:because|so\s+that|in\s+order\s+to|to\s+meet|otherwise|unless|but)\b|\s+and\s+(?:my|your|our|the\s+(?:manager|director|CFO))\b",
                        raw, maxsplit=1, flags=re.I,
                    )[0].strip(' ,:')
                    if not fragment or len(fragment.split()) < 2:
                        continue
                    # Known topic wording is clearer than a repeated directive;
                    # retain an explicit change/disclosure request because its
                    # content is additional to the accounting topic itself.
                    requested = any(match.groupdict().get(key) for key in ('requested', 'request_clause', 'passive'))
                    material_request = requested and _CHANGED_OR_DISCLOSURE_REQUEST.search(fragment)
                    if local_topics and not material_request and not re.search(rf"\band\s+{_VERBS}\b", raw, re.I):
                        continue
                    if re.search(r"\b(?:my|your)\s+(?:bonus|salary|job|promotion)\b", fragment, re.I) and not re.search(r"\b(?:payroll|pay|remuneration)\b", fragment, re.I):
                        continue
                    label = _display(fragment)
                    if requested:
                        label = "Requested activity: " + fragment
                    actions.append(label)
                    evidence.append(fragment)
    labels = [_display(values[0]) for values in topics.values()] + list(actions)
    if not labels:
        return "Unknown", (), ("The professional activity needs clarification.",) if ambiguous else ()
    return "; ".join(_unique(labels)), _unique(evidence), ()


def extract_entities(text: str) -> EntityResult:
    """Propose current actors and activities from explicit source wording."""
    if not isinstance(text, str):
        raise TypeError("Entity extraction requires text.")
    if len(text) > 100_000:
        return EntityResult("Unknown", "Unknown", "Unknown", {"role": (), "parties": (), "decision": ()}, ("The scenario exceeds the local extraction length limit.",))
    sentences = _sentences(text)
    role, role_evidence, spans, limitations = _role_data(sentences)
    parties, party_evidence = _parties(sentences, role, role_evidence, spans)
    decision, decision_evidence, decision_limits = _decision(sentences)
    return EntityResult(role, parties, decision, {"role": role_evidence, "parties": party_evidence, "decision": decision_evidence}, (*limitations, *decision_limits))
