from portable_evidence import normalize_events


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_verified_maps_to_pass():
    receipt = normalize_events(
        [{"event": "outcome", "outcome": "verified", "backend": "local"}],
        revision=SHA,
    )
    assert receipt["outcome"] == "pass"
    assert receipt["evidence"][0]["result"] == "pass"


def test_refuted_maps_to_fail():
    receipt = normalize_events(
        [{"event": "outcome", "outcome": "refuted"}],
        revision=SHA,
    )
    assert receipt["outcome"] == "fail"
    assert receipt["evidence"][0]["result"] == "fail"


def test_abstained_never_maps_to_pass():
    receipt = normalize_events(
        [{"event": "outcome", "outcome": "abstained", "backend": "browser"}],
        revision=SHA,
    )
    assert receipt["outcome"] == "abstain"
    assert receipt["evidence"][0]["result"] == "unknown"
    assert receipt["invariants"][0]["result"] == "pass"


def test_missing_outcome_stays_unknown():
    receipt = normalize_events(
        [{"event": "step", "step": 1, "backend": "browser"}],
        revision=SHA,
    )
    assert receipt["outcome"] == "unknown"


def test_requires_exact_revision():
    try:
        normalize_events([], revision="main")
    except ValueError:
        pass
    else:
        raise AssertionError("expected exact revision validation")
