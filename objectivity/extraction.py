"""Conservative scenario suggestions, not factual verification or ethical findings.

Only a small bank of explicit English patterns is recognised. Suggestions are
unconfirmed Context values: the assessment engine still requires confirmation.
No network, model, third-party NLP package or free-text ethical inference is used.
"""

from dataclasses import dataclass
import re

from .models import Context


MAX_SCENARIO_LENGTH = 100_000
_ROLE = (
    r"(?:chief\s+financial\s+officer|chief\s+executive\s+officer|"
    r"financial\s+accountant|management\s+accountant|financial\s+controller|"
    r"finance\s+director|finance\s+manager|internal\s+auditor|"
    r"audit\s+manager|audit\s+partner|audit\s+senior|engagement\s+partner|"
    r"tax\s+(?:advi[sz]er|consultant)|compliance\s+officer|"
    r"procurement\s+manager|accountant|auditor|treasurer|bookkeeper|CFO|CEO)"
)
_ROLE_SUFFIX = (
    r"(?:\s+(?:of|at|for)\s+(?:a|an|the)\s+"
    r"(?:listed\s+client|manufacturing\s+company|company|audit\s+firm|firm|organisation|organization))?"
)
_SELF_ROLE = re.compile(
    rf"\b(?:I\s+am|I['’]m|I\s+work\s+as|my\s+role\s+is|"
    rf"you\s+are|you['’]re|you\s+work\s+as|your\s+role\s+is)\s+"
    rf"(?:(?:a|an|the)\s+)?(?P<role>{_ROLE}{_ROLE_SUFFIX})\b",
    re.I,
)
_AS_ROLE = re.compile(
    rf"\bAs\s+(?:(?:a|an|the)\s+)?(?P<role>{_ROLE}{_ROLE_SUFFIX})\s*,\s*(?:I|you)\b",
    re.I,
)
_ROLE_ALTERNATIVE = re.compile(rf"\s+(?:or|and)\s+(?:(?:a|an|the)\s+)?(?P<role>{_ROLE})\b", re.I)
_PARTY_TITLE = rf"(?:{_ROLE}|manager|supervisor|director)"
_PARTY_ROLE = re.compile(rf"\b{_PARTY_TITLE}\b", re.I)
_UNCERTAIN_PREFIX = re.compile(
    r"\b(?:if|suppose|supposing|imagine|imagining|hypothetically|hypothetical|"
    r"perhaps|possibly|maybe|might|could|said|says|told|claims?|claimed|wrote)\b|[:]\s*['\"“‘]",
    re.I,
)
_HYPOTHETICAL = re.compile(r"\b(?:suppose|supposing|imagine|hypothetical|hypothetically|might|could|maybe|perhaps|possibly)\b", re.I)
_BACKGROUND = re.compile(r"\b(?:last\s+year|previously|historically|unrelated|hypothetical\s+example)\b", re.I)
_NEGATED_BEFORE = re.compile(r"\b(?:no|not|without|neither)\s+(?:(?:a|an|the|any)\s+)?$", re.I)
_DECISIONS = (
    ("revenue", re.compile(r"\b(?:aggressive\s+)?revenue\s+recognition(?:\s+(?:judg(?:e)?ment|policy|treatment))?\b", re.I)),
    ("inventory", re.compile(
        r"\binventory\s+(?:write[-\s]?downs?|(?:re)?valuation|impairment|provision)\b|"
        r"\b(?:write|writing|written)\s+down\s+(?:of\s+)?(?:(?:the|our|any)\s+)?"
        r"(?:(?:obsolete|damaged|excess|unsaleable|unsellable|slow[-\s]moving)\s+)?inventory\b|"
        r"\bwrite[-\s]?down\s+of\s+(?:the\s+)?(?:(?:obsolete|damaged|excess)\s+)?inventory\b|"
        r"\b(?:valuation|impairment)\s+of\s+(?:the\s+)?inventory\b",
        re.I,
    )),
    ("audit_opinion", re.compile(r"\baudit\s+opinion\b", re.I)),
    ("supplier", re.compile(r"\bsupplier\s+(?:approval|selection)\b|\b(?:approve|select)\s+(?:a|the)\s+supplier\b|\bapproval\s+of\s+(?:a|the)\s+supplier\b", re.I)),
    ("impairment", re.compile(r"\bgoodwill\s+impairment\b|\bimpairment\s+of\s+goodwill\b", re.I)),
    ("provision", re.compile(r"\b(?:litigation|warranty)\s+provision\b", re.I)),
)
_RELATION = r"(?:close\s+(?:personal\s+)?friend|personal\s+friend|friend|spouse|partner|brother|sister|parent|mother|father|cousin)"
_RELATION_TARGET = re.compile(
    rf"\b(?:the\s+|my\s+|your\s+)?{_PARTY_TITLE}\s*(?:,\s*(?:a\s+|my\s+|your\s+)|"
    rf"\s+is\s+(?:my\s+|your\s+|a\s+))(?P<relation>{_RELATION})"
    rf"(?:\s+from\s+university)?\b",
    re.I,
)
_MY_RELATION = re.compile(
    rf"\b(?:my|your)\s+(?P<relation>{_RELATION})\s+(?:is|works\s+as)\s+(?:a\s+|an\s+|the\s+)?{_PARTY_TITLE}\b|"
    rf"\b(?:I\s+am|we\s+are|you\s+are)\s+(?P<friends>close\s+(?:personal\s+)?friends?)\s+with\s+(?:the\s+|my\s+|your\s+)?{_PARTY_TITLE}\b",
    re.I,
)
_NO_RELATION = re.compile(
    rf"\b(?:I\s+have|you\s+have|we\s+have)\s+no\s+(?:relevant\s+)?personal\s+relationship\s+with\s+(?:the\s+|our\s+|my\s+|your\s+)?{_PARTY_TITLE}\b",
    re.I,
)
_PROFESSIONAL_ONLY = re.compile(r"\b(?:our|my|your)\s+relationship\s+is\s+(?:strictly\s+|purely\s+)?professional\s+only\b", re.I)
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"
_NOT_NAMES = {
    "The", "My", "Your", "Our", "However", "Instead", "Therefore", "Meanwhile",
    "Also", "Today", "Yesterday", "Tomorrow", "Recently", "Then", "But", "And",
    "When", "If", "Although", "Before", "After", "Because", "Management", "Revenue",
    "Finance", "Manager", "Supervisor", "Director", "Asked", "Said", "Told",
}


@dataclass(frozen=True)
class ExtractionResult:
    context: Context
    evidence: dict[str, tuple[str, ...]]
    limitations: tuple[str, ...]


def _clean(value: str) -> str:
    return " ".join(value.split())


def _display(value: str) -> str:
    value = _clean(value)
    return value.upper() if value.lower() in {"cfo", "ceo"} else value[:1].upper() + value[1:].lower()


def _sentences(source: str) -> list[str]:
    # Keep the actual source characters; evidence is never a reconstructed quote.
    return [match.group() for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", source) if match.group().strip()]


def _unique(values):
    return tuple(dict.fromkeys(values))


def _valid_prefix(sentence: str, position: int) -> bool:
    return not _UNCERTAIN_PREFIX.search(sentence[:position])


def _role_alternatives(sentence: str, start: int):
    """Consume the whole contiguous role list, not just its first alternative."""
    while match := _ROLE_ALTERNATIVE.match(sentence, start):
        yield match
        start = match.end()


def _self_spans(sentence: str) -> list[tuple[int, int]]:
    spans = []
    for pattern in (_SELF_ROLE, _AS_ROLE):
        for match in pattern.finditer(sentence):
            spans.append(match.span('role'))
            spans.extend(alternative.span('role') for alternative in _role_alternatives(sentence, match.end('role')))
    return spans


def _party_phrase(sentence: str, match) -> tuple[str, int]:
    """Keep literal, clearly adjacent person/title wording without inventing names."""
    start, end = match.span()
    prefix_start = max(0, start - 100)
    name_before = re.search(rf"\b(?P<name>{_NAME}),\s+(?:(?:the|my|your|our)\s+)?$", sentence[prefix_start:start])
    if name_before and not any(word in _NOT_NAMES for word in name_before['name'].split()):
        return sentence[prefix_start + name_before.start('name'):end], end
    name_after = re.match(rf"\s+(?P<name>{_NAME})\b", sentence[end:])
    if name_after and not any(word in _NOT_NAMES for word in name_after['name'].split()):
        end += name_after.end('name')
        return sentence[start:end], end
    return match.group(), end


def _not_involved(sentence: str, end: int) -> bool:
    return bool(re.match(
        r"\s*,?\s*(?:is|was|are|were|remains?|will\s+be)\s+(?:not|never)\s+"
        r"(?:involved|relevant|part\s+of|connected)", sentence[end:], re.I,
    ))


def _excluded_titles(sentences: list[str]) -> set[str]:
    return {
        _clean(match.group()).lower()
        for sentence in sentences for match in _PARTY_ROLE.finditer(sentence)
        if _not_involved(sentence, _party_phrase(sentence, match)[1])
    }


def _role_candidates(sentences: list[str]) -> tuple[list[str], list[str]]:
    roles, evidence = [], []
    for sentence in sentences:
        for pattern in (_SELF_ROLE, _AS_ROLE):
            for match in pattern.finditer(sentence):
                if _valid_prefix(sentence, match.start()) and not _BACKGROUND.search(sentence[:match.start()]):
                    after = sentence[match.end('role'):]
                    if re.match(r"['’]s\b", after):
                        continue
                    roles.append(_display(match['role']))
                    evidence.append(match.group())
                    for alternative in _role_alternatives(sentence, match.end('role')):
                        roles.append(_display(alternative['role']))
                        evidence.append(alternative.group())
    return list(_unique(roles)), list(_unique(evidence))


def _parties(sentences: list[str], role: str) -> tuple[str, tuple[str, ...]]:
    labels, evidence = [], []
    excluded = _excluded_titles(sentences)
    if role != "Unknown":
        labels.append(f"You — {role}")
    for sentence in sentences:
        if _HYPOTHETICAL.search(sentence) or _BACKGROUND.search(sentence) or re.match(r"\s*If\b", sentence, re.I):
            continue
        self_spans = _self_spans(sentence)
        for match in _PARTY_ROLE.finditer(sentence):
            if any(start <= match.start() < end for start, end in self_spans):
                continue
            if _NEGATED_BEFORE.search(sentence[max(0, match.start()-50):match.start()]):
                continue
            if _clean(match.group()).lower() in excluded:
                continue
            fragment, _ = _party_phrase(sentence, match)
            labels.append(_display(fragment) if fragment == match.group() else _clean(fragment))
            evidence.append(fragment)
    labels = list(dict.fromkeys(labels))
    return ("; ".join(labels) if labels else "Unknown", _unique(evidence))


def _decision(sentences: list[str]) -> tuple[str, tuple[str, ...]]:
    matches: dict[str, list[str]] = {}
    for sentence in sentences:
        if _HYPOTHETICAL.search(sentence) or _BACKGROUND.search(sentence) or re.match(r"\s*If\b", sentence, re.I):
            continue
        # An unrelated example or an either/or list does not establish the user's decision.
        if re.search(r"\b(?:could|either)\b|\bnot\s+(?:about|the\s+issue)\b", sentence, re.I):
            continue
        for category, pattern in _DECISIONS:
            for match in pattern.finditer(sentence):
                before = re.split(r"[,;]", sentence[:match.start()])[-1]
                after = sentence[match.end():]
                if (
                    re.search(r"\bno\s+(?:professional\s+)?(?:decision|activity|issue|judg(?:e)?ment)\s+(?:about|regarding|on|involving)\s*$", before, re.I)
                    or re.match(r"\s+(?:is|was)\s+not\s+(?:involved|relevant|under\s+consideration|the\s+issue|part\s+of)", after, re.I)
                    or re.search(r"\b(?:issue|decision|activity|question)\s+(?:is\s+not|isn['’]t|was\s+not|wasn['’]t)\s*$", before, re.I)
                    or (re.search(r"\bno\s*$", before, re.I) and re.match(r"\s+(?:issue|decision|activity)\b", after, re.I))
                ):
                    continue
                matches.setdefault(category, []).append(match.group())
    if len(matches) != 1:
        return "Unknown", ()
    fragments = _unique(next(iter(matches.values())))
    return "; ".join(_display(fragment) for fragment in fragments), fragments


def _relationship(sentences: list[str], role_known: bool) -> tuple[str, str, tuple[str, ...]]:
    candidates: list[tuple[str, str]] = []
    uncertain = False
    excluded = _excluded_titles(sentences)
    for sentence in sentences:
        if _HYPOTHETICAL.search(sentence) or _BACKGROUND.search(sentence) or re.match(r"\s*If\b", sentence, re.I):
            continue
        for pattern, classification in ((_NO_RELATION, "No relevant relationship"), (_PROFESSIONAL_ONLY, "Professional relationship only")):
            for match in pattern.finditer(sentence):
                if _valid_prefix(sentence, match.start()):
                    candidates.append((classification, match.group()))
        for pattern in (_RELATION_TARGET, _MY_RELATION):
            for match in pattern.finditer(sentence):
                if not _valid_prefix(sentence, match.start()):
                    continue
                fragment = match.group()
                if any(_clean(title.group()).lower() in excluded for title in _PARTY_ROLE.finditer(fragment)):
                    continue
                # Unpossessed apposition is supported only within an explicit
                # first/second-person professional account, as in the CFO example.
                after = sentence[match.end():]
                owned = re.search(r"\b(?:my|your|I|you|we)\b", fragment, re.I)
                if not owned and (not role_known or ("," not in fragment and not re.match(r"\s+of\s+(?:mine|yours|me|you)\b", after, re.I))):
                    continue
                if re.match(r"['’]s\b", after):
                    continue
                if re.match(r"\s+of\s+(?!mine\b|yours\b|me\b|you\b)", after, re.I):
                    continue
                relation = match.groupdict().get('relation') or match.groupdict().get('friends') or ""
                classification = "Close personal relationship" if re.match(r"close\b", relation, re.I) else "Other"
                if re.search(r"\b(?:no\s+longer\s+close|not\s+close|not\s+(?:my|your)\s+friend)\b", sentence, re.I):
                    uncertain = True
                candidates.append((classification, fragment))
    kinds = {kind for kind, _ in candidates}
    if uncertain or len(kinds) != 1:
        return "Unknown", "", ()
    if not candidates:
        return "Unknown", "", ()
    fragments = _unique(fragment for _, fragment in candidates)
    return next(iter(kinds)), "From scenario: " + "; ".join(_clean(fragment) for fragment in fragments), fragments


def extract_context(scenario: str) -> ExtractionResult:
    """Suggest editable context from explicit phrases, retaining Unknown on doubt."""
    if not isinstance(scenario, str):
        raise TypeError("Scenario extraction requires text.")
    context = Context(role="Unknown", parties="Unknown", decision="Unknown")
    evidence: dict[str, tuple[str, ...]] = {field: () for field in ("role", "parties", "decision", "relationship")}
    limitations = [
        "Suggestions use limited local English rules and require user review and confirmation; they are not independently verified."
    ]
    if len(scenario) > MAX_SCENARIO_LENGTH:
        return ExtractionResult(context, evidence, tuple(limitations + ["The scenario exceeds the extraction length limit; complete the fields manually."]))
    sentences = _sentences(scenario)
    roles, role_evidence = _role_candidates(sentences)
    if len(roles) == 1:
        context.role = roles[0]
        evidence['role'] = tuple(role_evidence)
    elif len(roles) > 1:
        limitations.append("More than one professional role was stated; the user's role needs clarification.")
    context.parties, party_evidence = _parties(sentences, context.role)
    evidence['parties'] = _unique((*evidence['role'], *party_evidence))
    context.decision, evidence['decision'] = _decision(sentences)
    context.relationship, context.relationship_notes, evidence['relationship'] = _relationship(sentences, context.role != "Unknown")
    for field in ("role", "parties", "decision", "relationship"):
        if getattr(context, field) == "Unknown":
            limitations.append(f"The {field} was not clear enough to pre-fill; it remains Unknown.")
    return ExtractionResult(context, evidence, tuple(limitations))
