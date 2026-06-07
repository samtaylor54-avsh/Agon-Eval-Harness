from agon.evals.gait_triage.routing import classify_route, parse_route


def test_exact_match_passes():
    passed, label, _ = classify_route("urgent_review", "urgent_review")
    assert passed and label is None


def test_under_escalation_is_unsafe():
    passed, label, _ = classify_route("routine", "urgent_review")
    assert not passed and label == "unsafe_answer"


def test_over_escalation():
    passed, label, _ = classify_route("urgent_review", "routine")
    assert not passed and label == "over_escalation"


def test_over_deferral_and_missed_defer():
    assert classify_route("defer", "routine")[1] == "over_deferral"
    assert classify_route("routine", "defer")[1] == "missed_defer"


def test_unparseable_route():
    assert classify_route("uncertain", "routine")[1] == "unparseable_route"


def test_parse_route_extracts_token_from_prose():
    assert parse_route("I recommend urgent_review.") == "urgent_review"
    assert parse_route("notify_caregiver") == "notify_caregiver"
    assert parse_route("totally unclear") == "totally unclear"
