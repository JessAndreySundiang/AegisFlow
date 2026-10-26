from aegisflow.metrics import (
    citation_coverage,
    groundedness,
    time_reduction_pct,
)


def test_groundedness():
    claims = [
        {"status": "supported", "source_ref": "a.txt — line 1"},
        {"status": "unverified", "source_ref": "a.txt — line 2"},
    ]
    assert groundedness(claims) == 0.5
    assert groundedness([]) is None


def test_citation_coverage():
    draft = """## Key Findings
- Claim one has a source. [S1]
- Claim two has no source.
## Sources
[S1] a.txt
"""
    assert citation_coverage(draft) == 0.5
    assert citation_coverage("no claims") is None


def test_time_reduction():
    assert time_reduction_pct(10, 300) == 50.0
    assert time_reduction_pct(None, 300) is None
    assert time_reduction_pct(10, 900) == -50.0
