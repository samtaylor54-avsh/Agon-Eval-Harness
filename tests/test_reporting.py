"""T9 — reporting + recommendation."""

from xml.etree import ElementTree as ET

from agon.reporting import recommend, render_junit_xml, render_markdown
from agon.schemas import Recommendation
from tests.test_regression import make_digest, rec


def test_recommend_pass_on_high_pass_rate():
    d = make_digest("r", [rec("a", True, 0.95), rec("b", True, 0.95)])
    out = recommend(d, None, pass_threshold=0.90, investigate_threshold=0.80)
    assert out is Recommendation.PASS


def test_recommend_investigate_in_band():
    d = make_digest("r", [rec("a", True, 0.9), rec("b", True, 0.9), rec("c", False, 0.1),
                          rec("d", True, 0.9), rec("e", True, 0.9)])  # 80% pass
    out = recommend(d, None, pass_threshold=0.90, investigate_threshold=0.80)
    assert out is Recommendation.INVESTIGATE


def test_recommend_fail_low_pass_rate():
    d = make_digest("r", [rec("a", False, 0.1), rec("b", False, 0.1)])
    out = recommend(d, None, pass_threshold=0.90, investigate_threshold=0.80)
    assert out is Recommendation.FAIL


def test_critical_safety_failure_forces_fail():
    crit = rec("a", False, 0.0, risk="critical")
    crit.detected_failure_labels = ["unsafe_answer"]
    # Even with everything else perfect, a critical safety fail → FAIL.
    d = make_digest("r", [crit] + [rec(f"ok{i}", True, 1.0) for i in range(20)])
    out = recommend(d, None, pass_threshold=0.90, investigate_threshold=0.80)
    assert out is Recommendation.FAIL


def test_markdown_contains_key_sections():
    d = make_digest("run-123", [rec("a", True, 0.95), rec("b", False, 0.2)])
    md = render_markdown(d, None, Recommendation.INVESTIGATE)
    assert "Agon Eval Report" in md
    assert "run-123" in md
    assert "Failed cases" in md
    assert "INVESTIGATE" in md


def test_junit_xml_is_valid_and_counts_failures():
    d = make_digest("r", [rec("a", True, 0.95), rec("b", False, 0.2)])
    xml = render_junit_xml(d)
    root = ET.fromstring(xml)
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "2"
    assert root.attrib["failures"] == "1"
    names = {tc.attrib["name"] for tc in root.findall("testcase")}
    assert names == {"a", "b"}
