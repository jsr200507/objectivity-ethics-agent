"""Short presentation text over existing findings; never an assessment engine."""
from .case_actions import SUPPORTED
from .case_reasoning import ACCEPTABLE


def threat_overview(case, threat):
    """Explain the recorded source and possible mechanism without a new verdict."""
    name = next((actor.label for actor in case.actors if actor.id == threat.subject), "the relevant party")
    source = next((fact for fact in case.facts if fact.id in threat.evidence_ids[:1]), None)
    if threat.kind == "Self-interest":
        benefit = source.value if source else "an outcome-linked incentive"
        if benefit == "Organisational financing or loan covenant interest":
            problem = f"{name} has a reported financing or loan covenant interest in the outcome."
        else:
            problem = f"Reported incentive for {name}: {benefit}."
        return (problem,
                "An outcome-linked incentive could displace judgment based on the professional evidence.")
    if threat.kind == "Intimidation":
        detail = source.value.strip().rstrip('.') if source else "pressure concerning this decision"
        problem = (f"Reported pressure: {detail}." if name.casefold() in detail.casefold()
                   else f"{name} — reported pressure: {detail}.")
        return (problem,
                "The request may discourage independent challenge; it does not establish that your work has changed.")
    if threat.kind == "Familiarity":
        employment = next((fact for fact in case.facts if fact.id in threat.evidence_ids and fact.predicate == "employment"), None)
        provider = next((actor.label for actor in case.actors if employment and actor.id == employment.object_id), "")
        connection = f"You report a personal or family connection with {name}"
        if provider:
            connection += f", who is reported to work for {provider}"
        return (connection + ".",
                "Loyalty or trust could reduce critical challenge; the relationship alone does not prove bias or involvement in the work.")
    if threat.kind == "Self-review":
        detail = source.value.strip().rstrip('.') if source else "earlier work relevant to the current assessment"
        return (f"{name} — reported earlier work: {detail}.",
                "Reliance on earlier judgments could make their assumptions or errors harder to challenge.")
    if threat.kind == "Advocacy":
        detail = source.value.strip().rstrip('.') if source else "a promotional or representative role relevant to this judgment"
        return (f"{name} — reported advocacy: {detail}.",
                "Defending a position could make it harder to assess contrary evidence objectively.")
    return threat.mechanism, "The recorded influence requires case-specific professional judgment."


def status_summary(assessment, *, reference="safeguard cards"):
    """Count existing residual findings without changing or replacing them."""
    total = len(assessment.outcomes)
    unresolved = [number for number, outcome in enumerate(assessment.outcomes, 1)
                  if outcome.status not in {ACCEPTABLE, SUPPORTED}]
    if not total:
        return "No potential threat is established on the recognised information; missing facts may still limit the assessment."
    if unresolved:
        numbers = ", ".join(f"{number:02}" for number in unresolved)
        count = f"{len(unresolved)} of {total} threats need" if total > 1 else "The recorded threat needs"
        return f"{count} further action or evidence. See {reference} {numbers}."
    if total == 1:
        qualifier = "remaining evidence gaps still need review" if assessment.unknowns else "reassess if the circumstances change"
        return f"The recorded threat position is conditionally supported; {qualifier}."
    if assessment.unknowns:
        return f"All {total} threat positions are conditionally supported; remaining evidence gaps still need review."
    return f"All {total} threat positions are conditionally supported on the recorded evidence. Reassess if the circumstances change."
