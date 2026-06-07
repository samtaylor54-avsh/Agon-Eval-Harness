from agon.evals.gait_triage.task import gait_dataset


def test_dataset_has_ten_cases_with_critical_gait_004():
    samples = list(gait_dataset())
    assert len(samples) == 10
    by_id = {s.id: s for s in samples}
    crit = by_id["gait_004"]
    assert crit.metadata["risk_level"] == "critical"
    assert crit.target == "urgent_review"
