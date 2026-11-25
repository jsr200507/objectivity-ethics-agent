"""Diagnostic smoke tests for the two exact Appendix A vignettes (do not merge)."""
import unittest
from objectivity.case_workflow import start_case, review_case
from objectivity.case_reasoning import reason_case
from objectivity.case_report import build_case_report

CASE_1 = ("You are the audit manager on a listed client. The CFO, a close personal friend "
          "from university, has asked you to 'go easy' on a revenue recognition judgement "
          "that is aggressive but arguably within the standard, hinting that your firm's "
          "tax advisory contract renewal next quarter depends on a smooth audit.")
CASE_2 = ("Your firm has been asked to both design and later audit a new internal-control "
          "system for a mid-sized manufacturing client, and the client has requested the "
          "same partner lead both engagements to 'save time and fees.'")


class AppendixASmoke(unittest.TestCase):
    def _inspect(self, number, scenario):
        case = start_case(scenario)
        review_case(case)
        snapshot = reason_case(case)
        report = build_case_report(case)
        print(f"APPENDIX_CASE_{number} ACTORS: " + repr([(a.id,a.label) for a in case.actors]))
        print(f"APPENDIX_CASE_{number} FACTS: " + repr([(f.predicate,f.subject,f.value,f.status) for f in case.facts]))
        print(f"APPENDIX_CASE_{number} THREATS: " + repr([(t.kind,t.subject) for t in snapshot.threats]))
        print(f"APPENDIX_CASE_{number} FOLLOWUPS: " + repr([(q.predicate,q.prompt) for q in snapshot.questions]))
        print(f"APPENDIX_CASE_{number} REPORT_SECTION: " + repr(report[-2200:]))
        self.assertTrue(case.scenario)
        self.assertIn("Overall Conclusion", report)

    def test_appendix_a_case_1(self):
        self._inspect(1, CASE_1)

    def test_appendix_a_case_2(self):
        self._inspect(2, CASE_2)


if __name__ == "__main__":
    unittest.main()
