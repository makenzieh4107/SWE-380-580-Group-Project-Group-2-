"""Detect security-sensitive patterns in artifact text.

The detector treats GitSkills content strictly as text. It never executes
commands or code contained in an artifact.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Detection:
    """A potential security-sensitive pattern match."""

    category: str
    matched_pattern: str
    matched_text: str
    evidence: str
    line_number: int


PATTERNS: dict[str, list[str]] = {
    "command_execution": [
        r"\bos\.system\s*\(",
        r"\bos\.popen\s*\(",
        r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\(",
        r"\bshell\s*=\s*True\b",
        r"\b(?:bash|sh)\s+-c\b",
        r"\bpowershell(?:\.exe)?\b",
        r"\bcmd\.exe\b",
        r"\bos\.(?:spawn|spawnl|spawnlp|spawnv|spawnvp)\s*\(",
        r"\bexecv(?:e|p)?\s*\(",
    ],
    "file_system_access": [
        r"\bopen\s*\(",
        r"\bread_text\s*\(",
        r"\bwrite_text\s*\(",
        r"\bos\.(?:remove|unlink|listdir|scandir|walk|makedirs)\s*\(",
        r"\bPath\([^)]*\)",
        r"\b…\.(?:read_text|write_text|unlink|iterdir|glob)\s*\(",
        r"\bshutil\.(?:rmtree|copy|copy2|move)\s*\(",
        r"\bglob\.glob\s*\(",
        r"\bmkdir\b",
        r"\brm\s+(?:-[A-Za-z]*r[A-Za-z]*\s+|--recursive\b)",
    ],
    "network_access": [
        r"\brequests\.(?:get|post|put|delete|patch|request)\s*\(",
        r"\burllib\.request\b",
        r"\burlopen\s*\(",
        r"\bhttp\.client\b",
        r"\bhttpx\.",
        r"\baiohttp\b",
        r"\bsocket\.(?:connect|create_connection)\s*\(",
        r"\bparamiko\b",
        r"\bftp\b",
        r"\b(?:curl|wget)\b",
    ],
}


def _line_evidence(
    content: str,
    start: int,
    end: int,
) -> tuple[str, int]:
    """Return the matching line and its one-based line number."""

    line_start = content.rfind("\n", 0, start) + 1
    line_end = content.find("\n", end)

    if line_end == -1:
        line_end = len(content)

    evidence = content[line_start:line_end].strip()
    line_number = content.count("\n", 0, start) + 1

    return evidence[:500], line_number


def detect_capabilities(content: str | None) -> list[Detection]:
    """Return potential security-sensitive pattern matches."""

    if not content:
        return []

    findings: list[Detection] = []

    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(
                pattern,
                content,
                flags=re.IGNORECASE,
            ):
                evidence, line_number = _line_evidence(
                    content,
                    match.start(),
                    match.end(),
                )

                findings.append(
                    Detection(
                        category=category,
                        matched_pattern=pattern,
                        matched_text=match.group(0),
                        evidence=evidence,
                        line_number=line_number,
                    )
                )

    return findings
    