"""Identify → Evaluate → Address over a shared, evidence-linked case ledger."""
import streamlit as st

from .case_model import ACTION_KINDS, ACTION_STAGES, PREDICATES, CaseHistory
from .case_reasoning import reason_case
from .case_workflow import (
    add_case_actor, add_case_fact, answer_action_question, answer_case_question,
    edit_case_fact, review_case, save_case_action, sync_case,
)

_LABELS = {
    'role':'Professional role', 'decision':'Professional decision', 'family_relationship':'Family relationship',
    'close_relationship':'Close personal relationship', 'professional_relationship':'Professional relationship',
    'employment':'Employment connection', 'interest':'Financial or other interest', 'pressure':'Reported influence or pressure',
    'self_review':'Earlier work now being reviewed', 'advocacy':'Position promoted and now assessed',
    'participation':'Participation in the relevant work', 'decision_responsibility':'Decision responsibility',
    'relationship_active':'Current relationship connection', 'interest_connection':'Interest connected to the outcome',
    'commercial_dependence':'Commercial dependence', 'work_changed':'Reported change to work',
    'prior_work_affected':'Earlier work affected', 'claim':'Reported claim, not established truth',
    'assurance':'Reported assurance or belief', 'context':'Additional reported context',
}
_ACTION_LABELS = {
    'independent_review':'Independent review', 'eliminate':'Eliminate the relevant circumstances',
    'remove_from_decision':'Removal from the decision', 'escalate':'Escalation', 'disclose':'Disclosure',
    'document':'Documentation', 'decline':'Decline or end the activity', 'none':'No action taken', 'other':'Other action',
}
_STATUS_LABELS = {'reported':'Reported account', 'unknown':'Unknown', 'disputed':'Disputed', 'denied':'Explicitly denied', 'withdrawn':'Withdraw this assertion'}


def _key(name):
    return f'{st.session_state.widget_generation}:case:{name}'


def _actor(case, actor_id):
    return next((a.label for a in case.actors if a.id == actor_id), 'Party not established')


def _facts(case, navigate):
    with st.expander('Review or correct reported information'):
        st.caption('Reported account; not independently verified. User review does not authenticate these statements.')
        active = [f for f in case.facts if f.status != 'withdrawn']
        for fact in active:
            st.write(f"**{_LABELS.get(fact.predicate, 'Reported information')} — {_actor(case, fact.subject)}**")
            st.text(fact.value)
            if fact.object_id:
                st.caption(f'Related party: {_actor(case, fact.object_id)}')
            st.caption(f'{_STATUS_LABELS[fact.status]} · ' + ('Reviewed by you' if fact.reviewed else 'Awaiting your review'))
            if fact.excerpt:
                st.text(f'Source account: {fact.excerpt}')
        if not active:
            st.info('No sufficiently clear facts were extracted. You can add the decision or answer the focused clarification.')
        with st.form(_key('review')):
            accepted = st.checkbox('These records reflect my account, including uncertainties.', key=_key('review_ack'))
            submitted = st.form_submit_button('Confirm recorded account')
        if submitted:
            if not accepted:
                st.warning('Review the reported records and acknowledge the uncertainties first.')
            else:
                review_case(case)
                navigate(st.session_state.view)
        if active:
            selected = st.selectbox('Choose reported information to correct', [f.id for f in active],
                format_func=lambda id: next(f'{_LABELS.get(f.predicate,"Reported information")} — {_actor(case,f.subject)}: {f.value[:75]}' for f in active if f.id == id),
                key=_key('edit_fact'))
            fact = next(f for f in active if f.id == selected)
            with st.form(_key('correct_fact')):
                value = st.text_area('Corrected detail', value=fact.value, max_chars=100_000)
                status = st.selectbox('Evidence status', list(_STATUS_LABELS), index=list(_STATUS_LABELS).index(fact.status), format_func=_STATUS_LABELS.get)
                subject = st.selectbox('Who does this information concern?', [a.id for a in case.actors],
                    index=[a.id for a in case.actors].index(fact.subject), format_func=lambda id:_actor(case,id))
                targets = ['']+[a.id for a in case.actors]
                related = st.selectbox('Related party (if any)', targets, index=targets.index(fact.object_id),
                                       format_func=lambda id:_actor(case,id) if id else 'No related party specified')
                save = st.form_submit_button('Save correction and reassess')
            if save:
                try:
                    edit_case_fact(case, fact.id, 'Unknown' if status=='unknown' else value, status, subject=subject, object_id=related)
                except ValueError as error: st.warning(str(error))
                else: navigate('identify')
        with st.expander('Add a missing party'):
            with st.form(_key('new_actor')):
                label = st.text_input('Party name or description')
                role = st.text_input('Their role (if known)')
                kind = st.selectbox('Party type', ('person','organisation'))
                add = st.form_submit_button('Add party')
            if add:
                try: add_case_actor(case,label,role,kind)
                except ValueError as error: st.warning(str(error))
                else: navigate('identify')
        with st.expander('Add structured reported information'):
            st.caption('Choose the meaning and actual parties explicitly. Free text is not automatically interpreted.')
            with st.form(_key('new_fact')):
                subject = st.selectbox('Information concerns', [a.id for a in case.actors], format_func=lambda id:_actor(case,id))
                predicate = st.selectbox('Type of information', PREDICATES, format_func=_LABELS.get)
                detail = st.text_area('Reported detail', max_chars=100_000)
                related = st.selectbox('Connected party', ['']+[a.id for a in case.actors], format_func=lambda id:_actor(case,id) if id else 'No connected party specified')
                unknown = st.checkbox('This detail is not known')
                add = st.form_submit_button('Add information and reassess')
            if add:
                try: add_case_fact(case,subject,predicate,'Unknown' if unknown else detail,related,'unknown' if unknown else 'reported')
                except ValueError as error: st.warning(str(error))
                else: navigate('identify')
        if case.history or case.fact_history or case.legacy_records:
            with st.expander('Earlier source records and imported history'):
                for record in (*case.legacy_records,*case.history):
                    st.write(f'**{record.label}**'); st.text(record.value)
                    if record.detail: st.text(record.detail)
                    if record.reason: st.caption(record.reason)
                for fact in case.fact_history:
                    st.write(_LABELS.get(fact.predicate,'Earlier reported information')); st.text(fact.value)


def _findings(case, snapshot):
    for threat in snapshot.threats:
        st.subheader(f'Potential {threat.kind} threat')
        st.write(threat.mechanism)
        st.caption('Provisional: a possible influence on Objectivity, not proven bias, misconduct or a violation.')
        with st.expander('Supporting scenario evidence and uncertainty'):
            for fid in threat.evidence_ids:
                fact = next((f for f in case.facts if f.id==fid),None)
                if fact:
                    st.text(f'{_actor(case,fact.subject)}: {fact.value}')
                    if fact.excerpt: st.text(f'Source: {fact.excerpt}')
            for gap in threat.uncertainty: st.write(gap)
    if not snapshot.threats:
        st.info('No particular Objectivity threat is established from the information recognised so far. This is not assurance that threats are absent. Clarify the professional decision or add missing information where relevant.')
    for interaction in snapshot.interactions: st.write(interaction)


def _material_question(case,snapshot,navigate):
    if not snapshot.questions:
        st.caption('No further material clarification is currently selected. Remaining uncertainties may still limit the conclusion.')
        return
    q=snapshot.questions[0]
    st.subheader('One point that could change the assessment')
    with st.expander('Why this matters'):
        st.write(q.why); st.write(q.impact)
    st.caption(f'{len(snapshot.questions)} currently relevant clarification(s); answers may change the next step.')
    with st.form(_key('material_question')):
        if q.options:
            choice=st.radio(q.prompt,q.options,index=None,key=_key('material_choice'))
        else:
            choice=st.text_input(q.prompt,max_chars=100_000)
        explanation=st.text_area('Additional reported explanation (optional)',max_chars=45_000)
        submit=st.form_submit_button('Record answer and reassess')
        unknown=st.form_submit_button('Unknown') if not q.options else False
    if submit or unknown:
        try: answer_case_question(case,q.id,'Unknown' if unknown else choice or '',explanation)
        except ValueError as error: st.warning(str(error))
        else: navigate(st.session_state.view)


def _action_editor(case,snapshot,navigate):
    from .case_actions import ACTION_CHECK_OPTIONS
    with st.expander('Record or correct an existing or planned action'):
        ids=['']+[a.id for a in case.actions]
        selected=st.selectbox('Action record',ids,format_func=lambda id:next(a.description for a in case.actions if a.id==id) if id else 'Add another action',key=_key('select_action'))
        old=next((a for a in case.actions if a.id==selected),None)
        with st.form(_key('action_record')):
            description=st.text_area('What has been done or proposed?',value=old.description if old else '',max_chars=100_000)
            kind=st.selectbox('Type of response',ACTION_KINDS,index=ACTION_KINDS.index(old.kind) if old else 0,format_func=_ACTION_LABELS.get)
            stage=st.selectbox('Reported action status',ACTION_STAGES,index=ACTION_STAGES.index(old.stage) if old else 0)
            actor=st.selectbox('Who took or proposed it?',[a.id for a in case.actors],index=[a.id for a in case.actors].index(old.actor_id) if old else 0,format_func=lambda id:_actor(case,id))
            tids=[t.id for t in snapshot.threats]
            links=st.multiselect('Threats this action addresses',tids,default=[id for id in old.threat_ids if id in tids] if old else [],format_func=lambda id:next(f'{t.kind}: {t.mechanism[:100]}' for t in snapshot.threats if t.id==id))
            evidence=st.text_area('Records or outcome evidence (reported, not authenticated)',value=old.evidence_detail if old else '',max_chars=100_000)
            accepted=st.checkbox('These action details reflect my reported account.')
            save=st.form_submit_button('Save action record')
        if save:
            if not accepted: st.warning('Review the action details before recording them.')
            else:
                try: save_case_action(case,description,kind,stage,links,old.checks if old else {},selected or None,actor,evidence)
                except ValueError as error: st.warning(str(error))
                else: navigate('case_address')


        if old:
            with st.expander('Correct previously recorded action evidence'):
                criterion = st.selectbox('Action evidence to revise', list(ACTION_CHECK_OPTIONS),
                    format_func=lambda key: key.replace('_',' ').capitalize(), key=_key('revise_criterion'))
                values = ACTION_CHECK_OPTIONS[criterion]
                current = old.checks.get(criterion)
                with st.form(_key('revise_action_evidence')):
                    updated = st.selectbox('Revised evidence answer', values,
                        index=values.index(current) if current in values else len(values)-1)
                    records = st.text_area('Revised supporting record description',value=old.evidence_detail,max_chars=100_000)
                    checked = st.checkbox('I have reviewed this action and its coverage against the current account.')
                    apply = st.form_submit_button('Correct action evidence and reassess')
                if apply:
                    if not checked:
                        st.warning('Review the current action and coverage before revising its evidence.')
                    else:
                        checks = dict(old.checks)
                        checks[criterion] = updated
                        new_stage = updated if criterion == 'stage' else old.stage
                        try:
                            save_case_action(case,old.description,old.kind,new_stage,old.threat_ids,checks,old.id,old.actor_id,records)
                        except ValueError as error: st.warning(str(error))
                        else: navigate('case_address')


def _address(case,snapshot,navigate):
    from .case_actions import assess_actions, action_questions
    st.subheader('Existing actions and safeguard assessment')
    st.write('First review what has already been done or proposed. Completion alone does not establish effectiveness, and reporting a concern is not automatically a safeguard.')
    for action in case.actions:
        st.write(f'**{action.description}**'); st.caption(f'Reported status: {action.stage} · {_ACTION_LABELS.get(action.kind,"Other action")}')
        if action.excerpt: st.text(f'Source account: {action.excerpt}')
        if not action.reviewed: st.caption('Review the reported status and which circumstances this action covers.')
    if not case.actions_reviewed:
        st.info('Have you already taken or planned a relevant action? Use the action editor to record or review it. An omitted action is not treated as “Not Taken”.')
        if st.button('No relevant action has been taken'):
            save_case_action(case,'No relevant action has been taken','none','Not Taken',[t.id for t in snapshot.threats])
            navigate('case_address')
        if st.button('Existing actions are not known'):
            case.actions_reviewed=True; case.revision+=1
            case.history.append(CaseHistory('Existing actions','Unknown',revision=case.revision))
            navigate('case_address')
    _action_editor(case,snapshot,navigate)
    questions=action_questions(case,snapshot)
    if questions:
        q=questions[0]
        st.subheader('Evidence that could change the residual assessment')
        with st.expander('Why this action question?'): st.write(q.why)
        with st.form(_key('action_question')):
            choice=st.radio(q.prompt,q.options,index=None) if q.options else st.text_input(q.prompt,max_chars=100_000)
            submit=st.form_submit_button('Record action evidence')
            unknown=st.form_submit_button('Unknown') if not q.options else False
        if submit or unknown:
            try: answer_action_question(case,q.id,'Unknown' if unknown else choice or '')
            except ValueError as error: st.warning(str(error))
            else: navigate('case_address')
    result=assess_actions(case,snapshot)
    for outcome in result.outcomes:
        st.write(f'**{outcome.kind}: {outcome.status}**')
        for text in outcome.reasoning: st.write(text)
        for gap in outcome.unknowns: st.caption(gap)
    st.write(result.conclusion)
    for step in result.next_steps: st.write(f'• {step}')
    if st.button('Generate Objectivity report'): navigate('case_report')
    if st.button('Return to evaluation'): navigate('case_evaluate')


def render_case(assessment,navigate):
    case=assessment.case_state
    if case is None:
        st.warning('No current scenario-driven assessment is available.'); return
    sync_case(case)
    snapshot=reason_case(case)
    stage=st.session_state.view
    st.caption('Identify → Evaluate → Address · Reported evidence and professional judgment')
    if stage=='case_report':
        from .case_report import build_case_report
        st.markdown(build_case_report(case))
        st.download_button('Download Objectivity report (Markdown)',build_case_report(case),file_name='objectivity-ethical-assessment.md',mime='text/markdown')
        if st.button('Revisit actions and residual threats'): navigate('case_address')
        _facts(case,navigate)
        return
    if stage=='identify':
        st.header('Provisional Objectivity Threat Assessment')
        st.write('These initial findings use the reported account. Review the supporting evidence and correct missing or inaccurate information; a potential threat is not proven impairment of Objectivity.')
        _findings(case,snapshot)
        _facts(case,navigate)
        _material_question(case,snapshot,navigate)
        if st.button('Evaluate threats'): navigate('case_evaluate')
    elif stage=='case_evaluate':
        st.header('Evaluate Objectivity threats')
        for evaluation in snapshot.evaluations:
            threat=next(t for t in snapshot.threats if t.id==evaluation.threat_id)
            st.subheader(f'{threat.kind}: {evaluation.outcome}')
            st.write(threat.mechanism)
            for text in evaluation.reasoning: st.write(text)
            st.write(evaluation.third_party)
            for gap in evaluation.material_gaps: st.caption(gap)
        if not snapshot.evaluations: st.info('There is not enough supported information for a threat-specific evaluation, or no particular threat has been identified within these rules. This is not clearance to proceed.')
        _facts(case,navigate)
        _material_question(case,snapshot,navigate)
        if st.button('Review existing actions'): navigate('case_address')
        if st.button('Return to provisional findings'): navigate('identify')
    else:
        _address(case,snapshot,navigate)
        _facts(case,navigate)
    for limitation in snapshot.limitations: st.caption(limitation)
    st.caption('Objectivity only · No generative AI · No independent fact verification · This supports professional judgment, not a certified ethical opinion. Separate audit-independence requirements may need consideration.')
