"""Local, source-linked scenario understanding with no network/model dependency.

The provider proposes attributed records, not ethical findings. Exact excerpts
and conservative grammars make proposals inspectable; unfamiliar wording remains
available for user correction rather than being invented or silently verified.
"""
from copy import deepcopy
import hashlib
import re

from .case_model import (
    ACTION_KINDS, ACTION_STAGES, PREDICATES, CaseActor, CaseAction, CaseFact,
    UnderstandingResult,
)
from .extraction import MAX_SCENARIO_LENGTH, extract_context
from .extraction_entities import ROLE_PATTERN
from .extraction_signals import extract_signals

_FAMILY = r"(?:sister|brother|spouse|wife|husband|mother|father|parent|daughter|son|child|cousin)"
_TITLE = re.compile(rf"\b{ROLE_PATTERN}s?\b", re.I)
_RECIPIENT_GROUP = re.compile(r'\b(?:audit\s+committee|ethics\s+committee|board\s+of\s+directors|board|regulators?|trustees)\b', re.I)
_RELATIVE = re.compile(rf"\b(?:my|your|our)\s+(?P<relation>{_FAMILY})\b", re.I)
_NAME = r"[A-Z][A-Za-z0-9&’'-]*(?:\s+[A-Z][A-Za-z0-9&’'-]*){0,4}"
_ORG = re.compile(rf"\b{_NAME}\s+(?:Valuations?|Valuers?|Surveyors?|Advisory|Supplies|Engineering|Components|Bank|Ltd|Limited|PLC|Inc|Foundation|Charity|Mutual|Tools)\b")
_GENERIC_ORG = re.compile(r"\b(?:external\s+valuation\s+firm|independent\s+valuation\s+firm|valuation\s+firm|manufacturing\s+company|listed\s+client|our\s+firm|your\s+firm|my\s+firm|the\s+firm|our\s+company|your\s+company|my\s+company|the\s+company)\b", re.I)
_EMPLOYMENT = re.compile(rf"(?i:\b(?:my|your|our)\s+(?P<relation>{_FAMILY})\b[^.!?;]{{0,55}}\b(?:works?\s+(?:for|at|in)|is\s+employed\s+by|is\s+employed\s+at|is\s+an?\s+employee\s+of)\s+)(?P<org>{_NAME}|(?i:(?:an?\s+|the\s+)?(?:external\s+|independent\s+)?valuation\s+firm))\b")
_BENEFITS = re.compile(r"\b(?:bonus(?:es)?|commissions?|consulting\s+fee|advisory\s+fee|contingent\s+fee|success\s+fee|retainer|shareholdings?|shares?|equity|stock\s+options?|financial\s+(?:benefit|incentive)|cash\s+reward|pay\s+rise|salary\s+increase)\b", re.I)
_LINK = re.compile(r"\b(?:depend(?:s|ent)?|tied|linked|conditional|contingent|in\s+return|provided\s+that|only\s+if|on\s+each\s+(?:sale|approval)|based\s+on)\b", re.I)
_FIRM_INCENTIVE = re.compile(r"\b(?:contract\s+renewal|client\s+retention|retain\s+(?:the\s+)?client|profit\s+targets?|firm[’']?s?\s+fees?|firm\b[^.!?;]{0,45}\b(?:earns?|receives?)\s+(?:a\s+)?(?:fee|income|retainer))\b", re.I)
_HYPOTHETICAL = re.compile(r"^\s*(?:suppose|supposing|imagine|hypothetically|perhaps|maybe)\b", re.I)
_HISTORICAL = re.compile(r"^\s*(?:previously|historically|last\s+year|in\s+an?\s+(?:old|unrelated)\s+case)\b", re.I)


def _id(prefix, *parts):
    return prefix + '_' + hashlib.sha256('\x1f'.join(parts).casefold().encode()).hexdigest()[:14]


def _units(text):
    return [m.group().strip() for m in re.finditer(r"(?:\.(?=\d)|[^.!?\n])+(?:[.!?]|$)", text) if m.group().strip()]


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


def _stage(unit):
    if re.search(r"\b(?:not\s+(?:yet\s+)?(?:completed|implemented|carried\s+out)|still\s+(?:planned|pending)|proposed|plan(?:ned)?\s+to|intend\s+to|requested|asked\s+for|will\s+(?:arrange|request|review)|in\s+progress)\b", unit, re.I):
        return 'Planned'
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
        actors={'user':CaseActor('user','You',role='' if old.context.role=='Unknown' else old.context.role,kind='professional')}
        facts={}
        actions={}
        units=_units(scenario)
        org_names={}
        family_ids={}
        employment={}

        def actor(label,role='',kind='person'):
            label=' '.join(label.strip(' ,:').split())
            low=label.casefold()
            if low in {'i','me','you','yourself','myself','user'}:return 'user'
            if low in {'my firm','your firm','our firm','the firm','firm'}: key='firm';label='Your firm';kind='organisation'
            elif low in {'my company','your company','our company','the company','company','manufacturing company'}: key='company';label='Manufacturing company' if 'manufacturing company' in scenario.lower() else 'Your organisation';kind='organisation'
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
                if key in {'firm','company','client'}:candidates+= {'firm':['firm'],'company':['company'],'client':['client']}[key]
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
                if any(excerpt in unit and unit.find(excerpt)<=m.start()<unit.find(excerpt)+len(excerpt) for excerpt in old.evidence['role']):continue
                if re.match(r"[’']s\s+assistant\b",unit[m.end():],re.I):continue
                actor(m.group(),role=m.group())
            for m in _RECIPIENT_GROUP.finditer(unit):
                if not _absent_actor(unit, m.start()):
                    actor(m.group(), role=m.group(), kind='organisation')
            for m in re.finditer(r'\b(?:independent\s+(?:partner|reviewer)|(?:competent|qualified)\s+reviewer)\b', unit, re.I):
                if not _negated(unit, m.start()):
                    actor(m.group(), role=m.group())
            for m in _EMPLOYMENT.finditer(unit):
                org=m['org'].strip()
                org=re.sub(r'^(?:an?|the)\s+','',org,flags=re.I)
                relative=family_ids.get(m['relation'].lower())
                if relative and not _negated(unit,m.start()):
                    orgid=actor(org,kind='organisation')
                    employment[relative]=orgid
                    fact(relative,'employment','Employment at external organisation',unit,orgid)
        if old.context.role!='Unknown':
            excerpt=next(iter(old.evidence['role']), '')
            if excerpt:fact('user','role',old.context.role,excerpt)
        if old.context.decision!='Unknown':
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
                fact('user','professional_relationship','Reviewing or relying on provider work',unit,org)
            close=re.search(r'\b(?:close\s+(?:personal\s+)?friend(?:s)?|long[-\s]standing\s+friend)\b',unit,re.I)
            if close and not _negated(unit,close.start()):
                third_party=re.search(r"\b(?:of\s+the\s+(?:CEO|CFO)|(?:CEO|manager|director)[’']s\s+close\s+friend)\b",unit,re.I)
                linked=bool(re.search(r'\b(?:my|your|our)\s+close\b|\b(?:I\s+am|you\s+are|we\s+are)\s+close\s+friends?\s+with\b',unit,re.I)) or bool(re.search(r'\b(?:CFO|chief\s+financial\s+officer|director|partner)\s*,\s*a\s+close\s+(?:personal\s+)?friend',unit,re.I) and old.context.role!='Unknown')
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
                if _LINK.search(connection_clause):
                    fact(owner,'interest_connection','Yes',unit,org)
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
            signal=extract_signals(unit,user_role=old.context.role)
            linked_career=re.search(r'\b(?:says?|told|warns?|warned)\b[^.!?;]{0,90}\b(?:my|your)\s+(?:promotion|job|career)\b[^.!?;]{0,65}\b(?:depends?|conditional|unless)\b[^.!?;]{0,90}\b(?:favour|favor|recommend|approv|accept|sign)\w*\b',unit,re.I)
            if signal.pressure=='Reported pressure or threatened consequences' or linked_career:
                speaker=next((key for key in personal_mentions if not key.startswith('family_')), '')
                if not speaker:speaker=actor('Reported source of influence',kind='unknown')
                fact(speaker,'pressure',unit.rstrip('.!?'),unit,'user',attribution=actors[speaker].label)
            # A statement about a future valuation is a reported claim, never a prediction/fact of recovery.
            if re.search(r'\b(?:says?|said|claims?|claimed|believes?)\b',unit,re.I) and re.search(r'\b(?:may|might|could|will)\b[^.!?;]{0,65}\b(?:recover|improve|rise|increase)\b',unit,re.I):
                speaker=personal_mentions[0] if personal_mentions else actor('Reported claimant',kind='unknown')
                fact(speaker,'claim',unit.rstrip('.!?'),unit,attribution=actors[speaker].label)
            # Self-review and advocacy require their own supported mechanisms, not an audit-role keyword.
            selfreview=re.search(r'\b(?:review(?:ing)?|audit(?:ing)?|assess(?:ing)?)\b[^.!?;]{0,75}\b(?:my\s+own|our\s+own|your\s+own|I\s+(?:previously\s+)?prepared|you\s+(?:previously\s+)?prepared)\b|\b(?:I|you)\s+(?:prepared|developed|calculated)\b[^.!?]{0,120}\b(?:now|then)\b[^.!?]{0,55}\b(?:review|audit|assess)\s+(?:it|the\s+same|that|this)\b',unit,re.I)
            if selfreview and not _negated(unit,selfreview.start()):fact('user','self_review','Reviewing or relying on own earlier work',unit)
            advocacy=re.search(r'\b(?:I|you|we)\b[^.!?]{0,45}\b(?:promot(?:e|ed|ing)|advocat(?:e|ed|ing)|campaign(?:ed|ing)?\s+for|represented)\b[^.!?]{0,130}\b(?:now|then|also)\b[^.!?]{0,65}\b(?:objective|independent|assess|evaluat|review)\w*\b',unit,re.I)
            if advocacy and re.search(r'\b(?:assess|evaluat|review)\w*\b[^.!?]{0,25}\b(?:it|that|same|this)\b',unit,re.I) and not _negated(unit,advocacy.start()):fact('user','advocacy','Promoting a position while expected to assess it objectively',unit)
            # Explicit structured equivalents can be reused instead of being asked again.
            if re.search(r'\b(?:I|you|we)\s+(?:make|recommend|approve|select|decide)\b|\b(?:I|you)\s+(?:am|are)\s+responsible\s+for\s+(?:approv|decid|select)',unit,re.I):
                fact('user','decision_responsibility','I make or recommend the decision',unit)
            elif re.search(r'\b(?:I|you|we)\s+(?:review|supervise|am\s+reviewing|are\s+reviewing)\b|\byou\s+are\s+[^.!?]{0,55}\breviewing\b',unit,re.I):
                fact('user','decision_responsibility','I supervise or review the work',unit)
            elif re.search(r'\b(?:I|you|we)\s+(?:compare|prepare|assess|evaluate)\b|\b(?:I\s+am|you\s+are|we\s+are)\s+[^.!?;]{0,80}\b(?:preparing|assessing|evaluating|comparing)\b',unit,re.I):
                if not re.search(r'\b(?:not|never|do\s+not|do[ne][’\']t)\b', unit, re.I):
                    fact('user','decision_responsibility','I prepare or assess the work',unit)
            if re.search(r'\b(?:I|you)\s+(?:have|has)\s+no\s+(?:involvement|responsibility)\b',unit,re.I):fact('user','decision_responsibility','I have no involvement in this decision',unit)
            for relative,employer in employment.items():
                relname=actors[relative].label.split()[-1]
                subject_present=bool(re.search(r'\b'+re.escape(relname)+r'\b',unit,re.I)) or bool(len(employment)==1 and re.search(r'\b(?:she|he|they)\b',unit,re.I))
                if subject_present and re.search(r'\b(?:participat|involv|prepared\s+the\s+valuation|worked\s+on\s+(?:this|the)\s+valuation)',unit,re.I):
                    if re.search(r'\b(?:do\s+not\s+know|don[’\']t\s+know|unknown|unclear|not\s+known|unsure)\b',unit,re.I):value='Unknown';status='unknown'
                    elif re.search(r'\b(?:not|never|did\s+not|was\s+not)\b[^.!?;]{0,35}\b(?:participat|involv|work)|\bno\s+involvement\b',unit,re.I):value='No';status='reported'
                    else:value='Yes';status='reported'
                    fact(relative,'participation',value,unit,employer,status=status)
            if re.search(r'\b(?:I|you)\s+(?:have\s+not|did\s+not|have\s+never)\s+changed\s+(?:any\s+)?(?:work|recommendation|judg(?:e)?ment)',unit,re.I):fact('user','work_changed','No',unit)
            elif re.search(r'\b(?:I|you)\s+(?:have\s+|already\s+)?changed\s+(?:my|your|the)\s+(?:work|recommendation|judg(?:e)?ment)\b[^.!?]{0,80}\b(?:pressure|request|instruction)',unit,re.I):fact('user','work_changed','Yes',unit)

            # Existing actions are records of proposals or implementation, never proof of effectiveness.
            if re.search(r'\b(?:no\s+(?:relevant\s+)?action\s+(?:has\s+been|was)\s+taken|I\s+have\s+taken\s+no\s+action)\b',unit,re.I):
                action=CaseAction(_id('action','none',unit),'No relevant action reported as taken','none','Not Taken',source='scenario',excerpt=unit)
                actions[action.id]=action
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
        item=deepcopy(candidate);item.reviewed=False;item.basis_signature='';item.threat_ids=();item.revision=0
        # A provider cannot claim unsupported implementation or effective checks.
        literal_stage=_stage(item.excerpt)
        item.stage='Not Taken' if item.kind=='none' and re.search(r'\bno\s+(?:relevant\s+)?action\b',item.excerpt,re.I) else literal_stage
        item.checks=_action_checks(item.excerpt)
        item.evidence_detail=item.excerpt if item.checks.get('evidence')=='Records described' else ''
        actions.append(item);ids.add(item.id)
    if len(facts)!=len(result.facts) or len(actions)!=len(result.actions):warnings.append('Unsupported or unanchored provider proposals were excluded; review the scenario and add any missing facts.')
    return UnderstandingResult(tuple(actors),tuple(facts),tuple(actions),tuple(dict.fromkeys(warnings)))
