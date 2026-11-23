"""Regression cases for source precedence and stale action evidence."""
from copy import deepcopy
import unittest

from objectivity.case_actions import assess_actions
from objectivity.case_model import CaseFact
from objectivity.case_reasoning import reason_case
from objectivity.case_report import build_case_report
from objectivity.case_workflow import (
    add_case_fact, answer_case_question, edit_case_fact,
    migrate_legacy_assessment, review_case, save_case_action,
)
from objectivity.models import Assessment, Context
from tests.test_case_actions import action, fact, source_case


def save_existing(case, record, **changes):
    """Exercise the editor contract, including its retained hidden checks."""
    fields = dict(
        description=record.description, kind=record.kind, stage=record.stage,
        threat_ids=record.threat_ids, checks=dict(record.checks),
        action_id=record.id, actor_id=record.actor_id,
        evidence_detail=record.evidence_detail,
    )
    fields.update(changes)
    return save_case_action(case, **fields)


class CaseAuditRegressionTests(unittest.TestCase):
    def legacy_with_corrected_context(self):
        return Assessment(
            scenario='You are an audit manager reviewing revenue recognition. Your annual bonus depends on company profit.',
            context=Context(role='Financial accountant', decision='Assess an inventory write-down'),
            confirmed=True,
        )

    def test_legacy_structured_corrections_override_older_narrative_suggestions(self):
        previous = self.legacy_with_corrected_context()
        case = migrate_legacy_assessment(previous)
        active = [f for f in case.facts if f.status == 'reported']
        self.assertEqual([f.value for f in active if f.predicate == 'role'], ['Financial accountant'])
        self.assertEqual([f.value for f in active if f.predicate == 'decision'], ['Assess an inventory write-down'])
        self.assertTrue(any('Assess an inventory write-down' in t.mechanism for t in reason_case(case).threats))
        self.assertFalse(any('Revenue recognition' in t.mechanism for t in reason_case(case).threats))

    def test_migrated_party_role_matches_latest_structured_role(self):
        case = migrate_legacy_assessment(self.legacy_with_corrected_context())
        user = next(actor for actor in case.actors if actor.id == 'user')
        self.assertEqual(user.role, 'Financial accountant')
        parties = next(line for line in build_case_report(case).splitlines() if 'Recorded parties:' in line)
        self.assertNotIn('Audit manager', parties)

    def test_migration_preserves_original_assessment_and_source_history(self):
        previous = self.legacy_with_corrected_context()
        original = deepcopy(previous)
        case = migrate_legacy_assessment(previous)
        self.assertEqual(previous, original)
        self.assertIn(('Role', 'Financial accountant'), [(h.label, h.value) for h in case.legacy_records])
        self.assertIn(('Decision', 'Assess an inventory write-down'), [(h.label, h.value) for h in case.legacy_records])

    def case_with_unknown_connection(self):
        case = source_case()
        case.facts = [f for f in case.facts if f.predicate != 'interest_connection']
        question = next(q for q in reason_case(case).questions if q.predicate == 'interest_connection')
        answer_case_question(case, question.id, 'Unknown')
        return case, question

    def test_new_scoped_fact_supersedes_unknown_answer_and_report_uncertainty(self):
        case, question = self.case_with_unknown_connection()
        old_fact_id = case.answers[question.id].fact_id
        added = add_case_fact(case, question.subject, question.predicate, 'Yes',
                              question.object_id, decision_id=question.decision_id)
        self.assertEqual(added.value, 'Yes')
        self.assertNotIn(question.id, case.answers)
        self.assertFalse(any(f.id == old_fact_id and f.status != 'withdrawn' for f in case.facts))
        self.assertTrue(any(h.value == 'Unknown' for h in case.history))
        self.assertFalse(any(q.id == question.id for q in reason_case(case).questions))
        report = build_case_report(case)
        self.assertNotIn("The connection of You's interest to the decision remains unknown", report)

    def test_superseding_unknown_does_not_withdraw_other_party_scope(self):
        case, question = self.case_with_unknown_connection()
        other = CaseFact('other-connection', 'sister', 'interest_connection', 'Unknown',
                         object_id='firm', source='user', status='unknown', reviewed=True)
        case.facts.append(other)
        add_case_fact(case, question.subject, question.predicate, 'Yes',
                      question.object_id, decision_id=question.decision_id)
        self.assertEqual(other.status, 'unknown')
        self.assertIn(other, case.facts)

    def assert_evidence_requires_reassessment(self, case, record):
        self.assertFalse(assess_actions(case).actions[0].effective)
        self.assertFalse({key for key in record.checks if key != 'stage'},
                         'Old effectiveness answers must not be rebound to a materially different action.')
        self.assertTrue(case.action_history)

    def test_saving_stale_action_does_not_rebind_old_effectiveness_answers(self):
        case = source_case()
        record = action(case)
        self.assertTrue(assess_actions(case).actions[0].effective)
        edit_case_fact(case, 'bonus', 'Personal shareholding in the supplier selected by this decision')
        self.assertFalse(assess_actions(case).actions[0].effective)
        saved = save_existing(case, record)
        review_case(case)
        self.assert_evidence_requires_reassessment(case, saved)

    def test_changed_action_kind_discards_previous_effectiveness_answers(self):
        case = source_case()
        record = action(case)
        saved = save_existing(case, record, kind='remove_from_decision')
        self.assert_evidence_requires_reassessment(case, saved)

    def test_changed_implementation_stage_requires_new_effectiveness_evidence(self):
        case = source_case()
        record = action(case, stage='Planned')
        saved = save_existing(case, record, stage='Implemented')
        self.assert_evidence_requires_reassessment(case, saved)

    def test_expanded_threat_coverage_does_not_reuse_old_scope_answers(self):
        case = source_case(fact('pressure', 'pressure', 'CFO asks for a favourable inventory judgment', subject='cfo'))
        threats = reason_case(case).threats
        bonus = next(t.id for t in threats if t.kind == 'Self-interest')
        record = action(case, selected=(bonus,))
        self.assertTrue(assess_actions(case).actions[0].effective)
        saved = save_existing(case, record, threat_ids=tuple(t.id for t in threats))
        self.assert_evidence_requires_reassessment(case, saved)
        self.assertFalse(all(outcome.status.startswith('Threat adequately addressed')
                             for outcome in assess_actions(case).outcomes))

    def test_unchanged_valid_action_save_keeps_current_evidence(self):
        case = source_case()
        record = action(case)
        original_checks = dict(record.checks)
        saved = save_existing(case, record)
        self.assertTrue(assess_actions(case).actions[0].effective)
        self.assertEqual({k: v for k, v in saved.checks.items() if k != 'stage'}, original_checks)


if __name__ == '__main__':
    unittest.main()
