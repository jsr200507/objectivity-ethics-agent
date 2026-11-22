"""Local, evidence-linked suggestions about relationships, incentives and pressure.

These are classifications of reported wording, not findings of bias, coercion,
financial materiality or misconduct. Every suggestion requires user review.
"""

from dataclasses import dataclass
import re


_PERSON_ROLE = (
    r"(?:chief\s+(?:financial|executive)\s+officer|CFO|CEO|"
    r"(?:finance|financial|sales|claims|audit|engagement|purchasing|procurement|warehouse|branch|"
    r"operations|managing|credit|investment)\s+(?:director|manager|partner|officer|analyst|controller)|"
    r"head\s+of\s+(?:finance|sales|purchasing|procurement|claims|operations)|"
    r"department\s+head|team\s+leader|line\s+manager|manager|supervisor|director|partner|colleague|client|supplier)"
)
_TITLE = re.compile(rf"\b{_PERSON_ROLE}\b", re.I)
_FAMILY = r"(?:spouse|husband|wife|partner|brother|sister|parent|mother|father|cousin|child|son|daughter)"
_RELATION = rf"(?:close\s+(?:personal\s+)?friends?|personal\s+friends?|long[-\s]standing\s+friends?|friends?|{_FAMILY})"
_OWN_RELATION = re.compile(rf"\b(?:my|your|our)\s+(?P<relation>{_RELATION})\b", re.I)
_FRIENDS_WITH = re.compile(
    r"\b(?:I|we|you)\s+(?:am|are|have\s+been|have\s+remained)\s+"
    r"(?P<relation>(?:close\s+(?:personal\s+)?|personal\s+)?friends?)\s+with\b", re.I,
)
_APPOSITION = re.compile(
    rf"\b{_PERSON_ROLE}\s*,\s*a\s+(?P<relation>close\s+(?:personal\s+)?friend)"
    r"(?:\s+from\s+university)?\b", re.I,
)
_NO_PERSONAL = re.compile(
    r"\b(?:I|you|we)\s+(?:have|share)\s+no\s+(?:relevant\s+)?personal\s+"
    r"(?:relationship|connection|ties?|association)s?\b|"
    r"\b(?:no|without)\s+(?:any\s+)?personal\s+(?:ties?|connections?|relationship)\b", re.I,
)
_PRO_ONLY = re.compile(
    r"\b(?:our|my|your|the)\s+relationship\s+is\s+(?:(?:strictly|purely|solely)\s+)?professional(?:\s+only)?\b|"
    r"\b(?:we|I|you)\s+(?:have|share)\s+(?:a\s+)?(?:strictly|purely|solely)\s+professional\s+relationship\b", re.I,
)
_PRO_ASSOCIATION = re.compile(
    rf"\b(?:I|you|we)\s+(?:report(?:s)?\s+(?:directly\s+)?to|work\s+(?:with|under)|"
    rf"am\s+supervised\s+by|are\s+supervised\s+by)\b|"
    rf"\b(?:my|your|our)\s+{_PERSON_ROLE}\b|"
    rf"\b{_PERSON_ROLE}\b[^.!?]{{0,100}}\b(?:asked|asks|told|tells|instructed|instructs|"
    r"warned|warns|ordered|orders|pressured|pressures|insists|insisted)\s+(?:that\s+)?(?:me|you|us|I)\b|"
    r"\b(?:we|I|you)\s+have\s+worked\s+(?:together|with)\b", re.I,
)
_NEG_CLOSE = re.compile(
    r"\b(?:not|no\s+longer)\s+(?:(?:my|your|our)\s+)?(?:close(?:\s+personal)?\s+friends?|friends?|close)\b", re.I,
)
_HISTORY = re.compile(r"^\s*(?:previously|historically|last\s+year|in\s+(?:an?|the)\s+(?:old|prior|unrelated)\s+case|unrelated\b)", re.I)
_HYPOTHETICAL = re.compile(r"^\s*(?:suppose|supposing|imagine|imagining|hypothetically|perhaps|maybe)\b", re.I)
_ACTUAL_REPORT = re.compile(r"\b(?:says|said|told\s+me|has\s+warned|warned\s+me|I\s+was\s+told|I\s+have\s+been\s+told)\b", re.I)
_INCENTIVE_MODIFIERS = (
    r"(?:(?:annual|quarterly|monthly|personal|individual|performance(?:[-\s]related)?|"
    r"year[-\s]end|sales|cash|deferred|retention|completion|discretionary|"
    r"profit[-\s](?:related|sharing)|long[-\s]term)\s+){0,5}"
)
_FINANCIAL_BENEFIT = (
    r"(?:bonus(?:es)?|commissions?|remuneration|salary(?:\s+increase)?|pay(?:\s+(?:rise|increase|review))?|"
    r"pension|(?:professional\s+)?fees?|payments?|(?:cash|monetary|financial)\s+(?:rewards?|awards?)|"
    r"financial\s+(?:benefits?|incentives?)|share\s+options?|stock\s+options?|profit[-\s]share)"
)
_OWNERSHIP = re.compile(
    r"\b(?:I|you|we)\s+(?:own|owns|hold|holds|bought|possess|have)\s+(?:an?\s+|the\s+|some\s+|"
    r"(?:an?\s+)?\d+(?:[.,]\d+)*\s*(?:(?:%|per\s*cent|percent)\s+)?){0,2}"
    r"(?:(?:personal|direct|indirect|beneficial|financial)\s+){0,3}"
    r"(?:shares?|stocks?|equity(?:\s+stake)?|stake|investment|financial\s+interest|shareholdings?)\b|"
    r"\b(?:my|your|our)\s+(?:(?:personal|direct|indirect|beneficial|financial)\s+){0,3}"
    r"(?:shareholdings?|shares?|stocks?|equity|stake|investment|financial\s+interest)\b", re.I,
)
_OWN_PAY = re.compile(
    rf"\b(?:my|your|our)\s+{_INCENTIVE_MODIFIERS}{_FINANCIAL_BENEFIT}\b|"
    r"\b(?:I|you|we)\s+(?:receive|earn|am\s+paid|are\s+paid|will\s+receive|would\s+receive|"
    r"am\s+eligible\s+for|are\s+eligible\s+for|have\s+been\s+offered|stand\s+to\s+gain)\b"
    rf"[^.!?]{{0,90}}\b{_FINANCIAL_BENEFIT}\b", re.I,
)
_DIRECT_INCENTIVE = re.compile(
    r"\b(?:bonus(?:es)?|commissions?|(?:cash|monetary|financial)\s+(?:rewards?|awards?)|"
    r"financial\s+(?:benefits?|incentives?)|salary\s+increase|pay\s+(?:rise|increase)|"
    r"share\s+options?|stock\s+options?|profit[-\s]share)\b", re.I,
)
_OWN_FINANCIAL_OUTCOME = re.compile(
    r"\b(?:I|you|we)\s+(?:(?:will|would|could|may|stand\s+to)\s+)?"
    r"(?:gain|benefit|profit)\s+financially\b", re.I,
)
_PAY_LINK = re.compile(
    r"\b(?:depend(?:s|ent)?|tied|linked|based|conditional|contingent|targets?|approval|"
    r"outcome|profit|renewal|sign|award|lower|reduce|meet|risk|lose|loss|receive|earn|paid)\b", re.I,
)
_FAMILY_HOLDING = re.compile(
    rf"\b(?:my|your|our)\s+(?P<family>{_FAMILY})\b[^.!?]{{0,90}}"
    r"\b(?:owns?|holds?|bought|has\s+(?:a\s+)?stake|receives?|earns?)\b[^.!?]{0,70}"
    r"\b(?:shares?|stocks?|equity|stake|investment|bonus|commission|dividends?)\b", re.I,
)
_FINANCIAL_WORDS = re.compile(r"\b(?:bonus|bonuses|commissions?|shareholdings?|shares?|stocks?|equity|stake|financial\s+(?:interest|incentive|benefit)s?|dividends?|pay\s+rise|salary\s+increase|stock\s+options?|share\s+options?)\b", re.I)
_CAREER = re.compile(r"\b(?:my|your|our)\s+(?:promotion|career|appraisal|performance\s+(?:rating|review))\b|\b(?:promoted|promotion)\b", re.I)
_INCOME_RECEIPT = (
    r"(?:(?:also|currently|will|would|may|could|can)\s+){0,3}"
    r"(?:earns?|receives?|collects?|(?:is|are)\s+paid)\s+"
    r"(?:(?:an?|the|annual|substantial|professional)\s+){0,3}"
    r"(?:(?:success|contingent|advisory|consulting)\s+)?"
    r"(?:fees?|income|revenue|retainers?|commissions?)"
)
_ORG_INCOME = re.compile(
    r"\b(?:my|your|our|the)\s+(?:(?:audit|accounting|advisory|consultancy)\s+)?"
    rf"(?:firm|practice|business|company|employer|organisation|organization)\s+{_INCOME_RECEIPT}\b", re.I,
)
_COUNTERPART_INCOME = re.compile(
    rf"\b(?:{_PERSON_ROLE}|another\s+(?:firm|company))"
    rf"(?:[’']s\s+(?:firm|company))?\s+{_INCOME_RECEIPT}\b", re.I,
)
_COMMERCIAL = re.compile(
    r"\b(?:contract\s+renewal|renewal\s+of\s+[^.!?]{0,65}\bcontract|"
    r"(?:retain|retaining|retention|renew|renewing|renewed|withdraw|cancel|cancelling|lose|losing)\b[^.!?]{0,65}\b(?:client|customer|contract|engagement|fees?|business)|"
    r"(?:client|customer|contract|engagement)\b[^.!?]{0,50}\b(?:renewal|retention|renewed)|"
    r"(?:firm|practice|business|company|employer)[’']?s?\s+(?:fees?|profitability|income|revenue)|"
    r"(?:profit|earnings|sales|revenue|performance)\s+targets?|"
    r"(?:bank|loan|debt)\s+covenants?|\bfees?\b[^.!?]{0,35}\b(?:firm|practice|income|client))\b", re.I,
)
_ORG_SCOPE = re.compile(r"\b(?:my|your|our|the)\s+(?:firm|company|employer|practice|business|organisation|organization)\b|\bmanufacturing\s+company\b", re.I)
_NO_FINANCIAL = re.compile(
    r"\b(?:I|you|we)\s+(?:have|hold)\s+no\s+(?:(?:relevant|personal|direct)\s+)?"
    r"(?:financial\s+(?:interest|stake|incentive)s?|(?:financial\s+or\s+)?commercial\s+interests?)\b|"
    r"\b(?:no|without)\s+(?:any\s+)?(?:relevant\s+)?financial\s+(?:interest|stake|incentive)s?\b", re.I,
)
_NEG_PAY_LINK = re.compile(
    r"\b(?:not|never|unaffected|unrelated|independent\s+of)\b[^.!?]{0,30}\b(?:depend|linked|tied|affected|outcome|decision|profit|target)|"
    r"\b(?:bonus|pay|salary|commission)\b[^.!?]{0,35}\b(?:does\s+not|doesn['’]t|is\s+not|isn['’]t|unaffected|unrelated)\b", re.I,
)
_NO_PRESSURE = re.compile(
    r"\b(?:no\s+one|nobody)\s+(?:has\s+|is\s+|was\s+)?(?:ever\s+)?(?:pressur(?:ed|ing)|coerc(?:ed|ing)|intimidat(?:ed|ing)|threatened)\s+(?:me|you|us)\b|"
    r"\b(?:I|you|we)\s+(?:am|are|was|were)\s+(?:not\s+(?:being\s+)?(?:pressured|coerced|intimidated)|(?:not\s+under|under\s+no)\s+pressure)\b|"
    r"\b(?:there\s+is|there\s+was)\s+no\s+(?:reported\s+|undue\s+)?pressure\b|"
    r"\bno\s+pressure\s+(?:has\s+been\s+reported|was\s+reported|is\s+being\s+applied)\b", re.I,
)
_STRONG_PRESSURE = re.compile(
    r"\b(?:pressured|pressuring|coerced|coercing|intimidated|intimidating)\s+(?:me|you|us|to|into)\b|"
    r"\b(?:I|you|we)\s+(?:am|are|was|were|have\s+been)\s+(?:being\s+)?(?:pressured|coerced|intimidated)\b|"
    r"\b(?:under|facing|experiencing|feel)\s+(?:undue\s+)?pressure\b", re.I,
)
_THREAT = re.compile(r"\bthreaten(?:ed|s|ing)\b", re.I)
_FORCE = re.compile(r"\b(?:warned|warns|insists?|insisted|ordered|orders|demanded|demands|hinted|hinting)\b", re.I)
_REQUEST = re.compile(r"\b(?:asked|asks|told|tells|instructed|instructs|urged|urges|requested|requests|wants|wanted)\b", re.I)
_INSTRUCTION_CUE = re.compile(
    r"\b(?:instruction|directive|request)\s+(?:is|was)\b|"
    rf"\b(?:{_PERSON_ROLE}|management)\s+(?:said|says|wrote)\s*[,;:]?\s*[\"“']\s*"
    r"(?:do\s+not|don['’]t|please|delay|defer|postpone|withhold|conceal|hide)\b", re.I,
)
_CONSEQUENCE = re.compile(
    r"\b(?:lose|losing|loss|withdraw|cancel|fired|dismissed|dismissal|demoted|demotion|retaliation|"
    r"promotion|career|bonus|contract|renewal|renewed|pay\s+rise|performance\s+rating|unless)\b", re.I,
)
_STRONG_DIRECTION = re.compile(
    r"\b(?:falsif(?:y|ied)|inflat(?:e|ing)|suppress|suppressed|conceal|hide|hiding|ignore|overlook|"
    r"backdat(?:e|ing)|overstat(?:e|ing)|understat(?:e|ing)|go\s+easy|clean\s+(?:audit\s+)?opinion|"
    r"omit\b[^.!?]{0,35}\b(?:income|revenue|sales|liabilit(?:y|ies)|evidence))\b", re.I,
)
_DIRECTION = re.compile(
    r"\b(?:avoid|delay|postpone|lower|reduce|omit|remove|sign|signing|approve|award|accept|"
    r"soften|smooth|waive|drop|overlook|understate|overstate|make\b[^.!?]{0,55}\b(?:smaller|larger|lower|higher))\b", re.I,
)
_TARGET = re.compile(r"\b(?:profit|earnings|sales|revenue|performance)\s+targets?|\b(?:bonus|contract|renewal|covenant|(?:reported\s+)?profit\s+figures|reported\s+(?:profit|earnings|income)|financial\s+results)\b", re.I)
_ACCOUNTING_TIMING = re.compile(
    r"\b(?:delay|defer|postpone|avoid|hold\s+back)\b[^.!?;]{0,100}"
    r"\b(?:recognis(?:e|ing)|recogniz(?:e|ing)|recognition|record(?:ing)?|book(?:ing)?|"
    r"write[-\s]?down|impairment|provision|liabilit(?:y|ies)|loss(?:es)?|expense|"
    r"depreciation|revenue|accounting\s+(?:entry|adjustment)|audit\s+finding)\b", re.I,
)
_ACCOUNTABILITY_PARTY = (
    r"(?:auditors?|audit\s+(?:committee|partner|team)|board|directors|regulators?|"
    r"independent\s+reviewers?|compliance\s+(?:officer|team)|trustees)"
)
_WITHHOLD_DISCLOSURE = re.compile(
    r"\b(?:not\s+(?:to\s+)?|never\s+(?:to\s+)?)"
    r"(?:raise|report|disclose|mention|tell|inform|notify|alert|discuss|share|escalate|"
    r"send|provide|give|show|bring)\b[^.!?;]{0,130}"
    rf"\b{_ACCOUNTABILITY_PARTY}\b|"
    r"\b(?:withhold|conceal|hide|keep)\b[^.!?;]{0,130}"
    rf"\b(?:from|away\s+from)\s+(?:the\s+|our\s+|your\s+)?{_ACCOUNTABILITY_PARTY}\b|"
    r"\b(?:leave|keep)\b[^.!?;]{0,70}\b(?:out\s+of|off)\s+(?:the\s+)?"
    r"(?:audit\s+(?:file|papers|report)|board\s+(?:papers|report)|regulatory\s+report)\b",
    re.I,
)


@dataclass(frozen=True)
class SignalResult:
    relationship: str
    relationship_notes: str
    interests: str
    interests_notes: str
    pressure: str
    pressure_notes: str
    evidence: dict[str, tuple[str, ...]]
    limitations: tuple[str, ...]


def _unique(values):
    return tuple(dict.fromkeys(values))


def _units(text: str) -> list[str]:
    units = []
    # A decimal point in a percentage/holding does not end the account sentence.
    for sentence in re.findall(r"(?:\.(?=\d)|[^.!?\n])+(?:[.!?]|$)", text):
        units.extend(piece.strip() for piece in re.split(r";|\bbut\b|\bhowever\b|\bwhereas\b", sentence, flags=re.I) if piece.strip())
    return units


def _hypothetical(unit: str) -> bool:
    if _HYPOTHETICAL.search(unit) or _HISTORY.search(unit):
        return True
    if re.match(r"\s*if\b", unit, re.I):
        # "If my manager warned me ..." is an imagined event. A separate,
        # explicit report after the condition ("If I refuse, I was told ...")
        # can describe an actual warning of a conditional consequence.
        _, separator, report = unit.partition(",")
        if not separator or not _ACTUAL_REPORT.search(report):
            return True
    return bool(re.search(r"\b(?:could|might|may|would)\s+(?:be\s+)?(?:involved|relevant|a\s+friend|an?\s+interest|pressure|threaten)\b", unit, re.I))


def _negative_prefix(unit: str, start: int) -> bool:
    prefix = unit[max(0, start - 45):start]
    return bool(re.search(r"\b(?:no|not|never|without|denies|denied|hasn['’]t|haven['’]t|isn['’]t|wasn['’]t)\b[^,;]{0,22}$", prefix, re.I))


def _counterpart_quote(unit: str, start: int) -> bool:
    """A first-person phrase in a clearly attributed quote belongs to its speaker."""
    pattern = re.compile(
        rf"\b(?:{_PERSON_ROLE}|he|she|they)\s+(?:(?:has|had)\s+)?"
        r"(?:said|says|stated|explained|told\s+me|warned\s+me)\s*[,;:]?\s*[\"“']", re.I,
    )
    for match in pattern.finditer(unit):
        if match.end() <= start:
            # Sentence units may end inside a quote. Respect an explicit close
            # when present; otherwise conservatively keep the speaker's scope.
            rest = unit[match.end():]
            close = re.search(r"[\"”'](?=\s|[,.!?;:]|$)", rest)
            if close is None or start < match.end() + close.start():
                return True
    return False


def _positive_match(pattern: re.Pattern, unit: str):
    return next((match for match in pattern.finditer(unit) if not _negative_prefix(unit, match.start())), None)


def _notes(excerpts, qualifier: str = "") -> str:
    fragments = _unique(excerpts)
    if not fragments:
        return ""
    value = "From scenario: " + " | ".join(fragments)
    if qualifier:
        value += " " + qualifier
    # The complete scenario and evidence excerpts remain available for review.
    return value if len(value) <= 95_000 else value[:94_850] + " [Notes abbreviated; review the full scenario and source excerpts.]"


def _excluded_titles(units: list[str]) -> set[str]:
    excluded = set()
    for unit in units:
        for title in _TITLE.finditer(unit):
            if re.match(r"\s+(?:is|was|remains)\s+(?:not|never)\s+(?:involved|relevant|connected)", unit[title.end():], re.I):
                excluded.add(title.group().casefold())
    return excluded


def _relationship(units: list[str], user_role: str):
    close, other, professional, absent, only, negative_close = [], [], [], [], [], []
    excluded = _excluded_titles(units)
    for unit in units:
        if _hypothetical(unit):
            continue
        irrelevant = any(title.group().casefold() in excluded for title in _TITLE.finditer(unit))
        if irrelevant:
            continue
        if _NO_PERSONAL.search(unit): absent.append(unit)
        if _PRO_ONLY.search(unit): only.append(unit)
        if _PRO_ASSOCIATION.search(unit): professional.append(unit)
        if _NEG_CLOSE.search(unit): negative_close.append(unit)
        for pattern in (_OWN_RELATION, _FRIENDS_WITH):
            for match in pattern.finditer(unit):
                if _negative_prefix(unit, match.start()) or _counterpart_quote(unit, match.start()) or re.match(r"['’]s\b", unit[match.end():]):
                    continue
                relation = match['relation']
                (close if re.match(r"close\b", relation, re.I) else other).append(unit)
        if user_role != "Unknown":
            for match in _APPOSITION.finditer(unit):
                if not _negative_prefix(unit, match.start()) and not re.match(r"\s+of\s+(?!mine\b|yours\b)", unit[match.end():], re.I):
                    close.append(unit)
    evidence = _unique((*close, *other, *professional, *absent, *only, *negative_close))
    conflict = bool(close and (absent or only or negative_close))
    if conflict:
        return "Unknown", _notes(evidence, "Relationship statements conflict; clarify the parties and current relationship."), evidence, ["Conflicting relationship descriptions require clarification."]
    if close:
        return "Close personal relationship", _notes(evidence), evidence, []
    if only:
        return "Professional relationship only", _notes(evidence), evidence, []
    if absent:
        return "No relevant relationship", _notes(evidence), evidence, []
    if other or professional:
        qualifier = "Professional association is reported; personal closeness is not established." if professional and not other else "The stated tie does not establish personal closeness."
        return "Other", _notes(evidence, qualifier), evidence, []
    return "Unknown", "", (), []


def _interests(units: list[str], text: str):
    personal, commercial, third_party, career, negative = [], [], [], [], []
    no_personal, no_commercial = [], []
    org_known = bool(_ORG_SCOPE.search(text))
    for unit in units:
        if _hypothetical(unit):
            continue
        no_interest = _NO_FINANCIAL.search(unit)
        if no_interest:
            negative.append(unit)
            # A denial of the user's personal stake is compatible with an
            # explicitly reported firm incentive, and vice versa.
            scope = no_interest.group().lower()
            if "personal" in scope or "direct" in scope:
                no_personal.append(unit)
            elif "commercial" in scope and "financial" not in scope:
                no_commercial.append(unit)
            else:
                no_personal.append(unit)
                no_commercial.append(unit)
        ownership = next((m for m in _OWNERSHIP.finditer(unit) if not _negative_prefix(unit, m.start()) and not _counterpart_quote(unit, m.start())), None)
        own_pay = next((m for m in _OWN_PAY.finditer(unit) if not _negative_prefix(unit, m.start()) and not _counterpart_quote(unit, m.start())), None)
        own_outcome = next((m for m in _OWN_FINANCIAL_OUTCOME.finditer(unit) if not _negative_prefix(unit, m.start()) and not _counterpart_quote(unit, m.start())), None)
        # An explicit personal incentive can be suggested before its decision
        # link is confirmed; routine salary/pension needs a reported connection.
        pay_link = own_pay and (_PAY_LINK.search(unit) or _DIRECT_INCENTIVE.search(own_pay.group())) and not _NEG_PAY_LINK.search(unit)
        if ownership or pay_link or own_outcome:
            personal.append(unit)
        family = next((m for m in _FAMILY_HOLDING.finditer(unit) if not _negative_prefix(unit, m.start()) and not _counterpart_quote(unit, m.start())), None)
        if family and family['family'].lower() in {"spouse", "husband", "wife", "child", "son", "daughter"}:
            personal.append(unit)
        elif family:
            third_party.append(unit)
        financial = next((m for m in _FINANCIAL_WORDS.finditer(unit) if not _negative_prefix(unit, m.start())), None)
        if financial and not (ownership or pay_link or own_outcome or family or no_interest) and not _NEG_PAY_LINK.search(unit):
            third_party.append(unit)
        commercial_match = _COMMERCIAL.search(unit)
        org_income = _ORG_INCOME.search(unit)
        if org_income:
            commercial.append(unit)
        elif commercial_match:
            if org_known or re.search(r"\b(?:firm|company|employer|practice|business|client|contract|engagement|fees?)\b", unit, re.I):
                commercial.append(unit)
            else:
                third_party.append(unit)
        elif _COUNTERPART_INCOME.search(unit):
            third_party.append(unit)
        if _CAREER.search(unit) and not (ownership or pay_link or own_outcome): career.append(unit)
    evidence = _unique((*personal, *commercial, *third_party, *career, *negative))
    if no_personal and personal or no_commercial and commercial:
        return "Unknown", _notes(evidence, "The absence statement conflicts with a recorded incentive; clarify whose interest and which activity are meant."), evidence, ["Conflicting financial-interest statements require clarification."]
    if personal and commercial:
        choice = "Both commercial and personal interests"
    elif personal:
        choice = "Personal financial interest"
    elif commercial:
        choice = "Commercial interest"
    elif third_party or career:
        choice = "Other"
    elif negative:
        choice = "No known interest"
    else:
        return "Unknown", "", (), []
    qualifiers = []
    if third_party: qualifiers.append("Some incentives concern another party or have an unclear recipient; they do not establish a personal benefit for the user.")
    if career: qualifiers.append("A career incentive is reported; a monetary benefit is not assumed.")
    if any(_FAMILY_HOLDING.search(unit) for unit in personal): qualifiers.append("A family holding is reported; the user's own ownership is not asserted.")
    return choice, _notes(evidence, " ".join(qualifiers)), evidence, []


def _pressure(units: list[str]):
    positive, negative = [], []
    for unit in units:
        if _hypothetical(unit):
            continue
        if _NO_PRESSURE.search(unit):
            negative.append(unit)
        strong = _positive_match(_STRONG_PRESSURE, unit)
        if strong and _counterpart_quote(unit, strong.start()):
            strong = None
        threat = _positive_match(_THREAT, unit)
        if threat and not re.search(r"\b(?:me|you|us|my|your|our|audit\s+team|the\s+firm)\b", unit[threat.end():], re.I):
            threat = None
        force = _positive_match(_FORCE, unit)
        request = _positive_match(_REQUEST, unit) or _positive_match(_INSTRUCTION_CUE, unit)
        direction = _positive_match(_DIRECTION, unit)
        strong_direction = _positive_match(_STRONG_DIRECTION, unit)
        timing = _positive_match(_ACCOUNTING_TIMING, unit)
        nondisclosure = _positive_match(_WITHHOLD_DISCLOSURE, unit)
        if strong or threat or force and (_CONSEQUENCE.search(unit) or direction or strong_direction):
            positive.append(unit)
        elif request and (strong_direction or timing or nondisclosure or direction and _TARGET.search(unit)):
            positive.append(unit)
    evidence = _unique((*positive, *negative))
    if positive and negative:
        return "Unknown", _notes(evidence, "Pressure statements conflict; clarify their source, timing and scope."), evidence, ["Conflicting pressure descriptions require clarification."]
    if positive:
        return "Reported pressure or threatened consequences", _notes(evidence, "Reported influence or consequences require confirmation; this does not establish undue pressure, intent or misconduct."), evidence, []
    if negative:
        return "No reported pressure", _notes(evidence), evidence, []
    return "Unknown", "", (), []


def extract_signals(text: str, *, user_role: str = "Unknown") -> SignalResult:
    """Classify explicit reported signals while preserving source ownership and doubt."""
    if not isinstance(text, str):
        raise TypeError("Signal extraction requires text.")
    units = _units(text)
    relationship, relationship_notes, relationship_evidence, r_limits = _relationship(units, user_role)
    interests, interests_notes, interest_evidence, i_limits = _interests(units, text)
    pressure, pressure_notes, pressure_evidence, p_limits = _pressure(units)
    return SignalResult(
        relationship, relationship_notes, interests, interests_notes, pressure, pressure_notes,
        {"relationship": relationship_evidence, "interests": interest_evidence, "pressure": pressure_evidence},
        _unique((*r_limits, *i_limits, *p_limits)),
    )
