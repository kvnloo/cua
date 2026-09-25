# Issue 28

Tests: `test_lazy_vision.py`. Fixture versions: Python caller on branch `test/rfc-fast-path-one-candidate-20260925`, upstream pin `c5ee191c02b11448ffefcc38b78b064a87d8ef23`.

`optional_visual_observation` already returns none when the visual tools are absent. Recommendation: no new caller helper and no new public Driver API.
