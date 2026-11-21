# This test can be ran in the terminal using python -m pytest .\test_capability_detector.py -v -s. 
# Just verifying that the capability_detector.py is working as expected. 
# It is not a comprehensive test of all possible cases, but it does cover some common scenarios.

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capability_detector import detect_capabilities


def categories(content):
    return {finding.category for finding in detect_capabilities(content)}


def test_detects_command_execution():
    content = "subprocess.run(['git', 'status'])"
    assert "command_execution" in categories(content)


def test_detects_file_system_access():
    content = 'Path("output.txt").write_text("hello")'
    assert "file_system_access" in categories(content)


def test_detects_network_access():
    content = "response = requests.get(url)"
    assert "network_access" in categories(content)


def test_detects_multiple_categories():
    content = """
response = requests.get(url)
Path("output.txt").write_text(response.text)
subprocess.run(["git", "status"])
"""
    assert categories(content) == {
        "command_execution",
        "file_system_access",
        "network_access",
    }


def test_empty_content_has_no_findings():
    assert detect_capabilities(None) == []
    assert detect_capabilities("") == []


def test_ordinary_text_has_no_findings():
    content = "Summarize this document and explain its main purpose."
    assert detect_capabilities(content) == []


def test_evidence_and_line_number():
    content = "first line\nresponse = requests.get(url)\nthird line"
    findings = detect_capabilities(content)

    network_findings = [
        finding
        for finding in findings
        if finding.category == "network_access"
    ]

    assert len(network_findings) == 1
    assert network_findings[0].line_number == 2
    assert network_findings[0].evidence == "response = requests.get(url)"


def test_case_insensitive_detection():
    content = "REQUESTS.GET(url)"
    assert "network_access" in categories(content)