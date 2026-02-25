"""Anthropic integration for AI-powered build diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass


FAILURE_TYPES = (
    "dependency_error",
    "compilation_error",
    "oom",
    "flaky_test",
    "missing_toolchain",
    "configuration_error",
    "timeout",
    "test_failure",
    "unknown",
)

TARGET_PATTERN = re.compile(r"(//[A-Za-z0-9_./-]+(?::[A-Za-z0-9_./-]+)?)")


@dataclass
class DiagnosisResult:
    """Structured diagnosis produced from a build log."""

    target: str | None
    failure_type: str
    summary: str
    root_cause: str
    suggested_fixes: list[str]
    raw_response: str
    model: str
    input_hash: str


def _extract_target(failure_text: str) -> str | None:
    match = TARGET_PATTERN.search(failure_text)
    return match.group(1) if match else None


def _normalize_failure_type(value: str | None) -> str:
    if not value:
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in FAILURE_TYPES else "unknown"


def _safe_parse_json(payload: str) -> dict:
    payload = payload.strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    candidate = payload[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {}


class BuildFailureAnalyzer:
    """Diagnose build failures using Claude."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

    def diagnose(self, failure_text: str, context: str | None = None) -> DiagnosisResult:
        """Analyze a build log by calling Anthropic."""
        if not failure_text.strip():
            raise ValueError("Build log is empty.")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your environment or .env file.")

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic package is not installed.") from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        prompt = self._build_prompt(failure_text, context=context)
        response = client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = self._extract_response_text(response)
        parsed = _safe_parse_json(raw_text)
        return self._to_result(parsed, raw_text=raw_text, failure_text=failure_text)

    def diagnose_dry_run(self, failure_text: str, context: str | None = None) -> DiagnosisResult:
        """Return a synthetic diagnosis without calling external APIs."""
        if not failure_text.strip():
            failure_text = "No log input provided."

        lowered = failure_text.lower()
        failure_type = "unknown"
        if "no such package" in lowered or "cannot find module" in lowered:
            failure_type = "dependency_error"
        elif "out of memory" in lowered or "oom" in lowered:
            failure_type = "oom"
        elif "timed out" in lowered or "timeout" in lowered:
            failure_type = "timeout"
        elif "toolchain" in lowered or "not found: gcc" in lowered:
            failure_type = "missing_toolchain"
        elif "build file" in lowered or "error loading package" in lowered:
            failure_type = "configuration_error"
        elif "test failed" in lowered or "assertionerror" in lowered:
            failure_type = "test_failure"
        elif "error:" in lowered or "failed to build" in lowered:
            failure_type = "compilation_error"

        target = _extract_target(failure_text)
        ctx_suffix = f" Context: {context}." if context else ""
        summary = f"Dry-run diagnosis for {failure_type.replace('_', ' ')}{ctx_suffix}"
        root_cause = (
            "This is a simulated diagnosis generated locally from keyword matching. "
            "Use without --dry-run for model-based analysis."
        )
        fixes = [
            "Re-run with full verbose logs (`-s`/`--sandbox_debug`) and capture the first error.",
            "Check recently changed targets and dependency declarations around the failing label.",
            "Run the failing target in isolation to reduce noise.",
        ]
        payload = {
            "target": target,
            "failure_type": failure_type,
            "summary": summary,
            "root_cause": root_cause,
            "suggested_fixes": fixes,
        }
        return self._to_result(payload, raw_text=json.dumps(payload), failure_text=failure_text)

    def _to_result(self, parsed: dict, raw_text: str, failure_text: str) -> DiagnosisResult:
        target = parsed.get("target") if isinstance(parsed.get("target"), str) else _extract_target(failure_text)
        failure_type = _normalize_failure_type(parsed.get("failure_type"))
        summary = str(parsed.get("summary") or "No summary returned.")
        root_cause = str(parsed.get("root_cause") or "No root cause returned.")
        fixes = parsed.get("suggested_fixes")
        if isinstance(fixes, list):
            suggested_fixes = [str(item).strip() for item in fixes if str(item).strip()]
        else:
            suggested_fixes = []
        if not suggested_fixes:
            suggested_fixes = ["Inspect the first failing target and verify dependencies/toolchain configuration."]

        input_hash = hashlib.sha256(failure_text.encode("utf-8")).hexdigest()
        return DiagnosisResult(
            target=target,
            failure_type=failure_type,
            summary=summary,
            root_cause=root_cause,
            suggested_fixes=suggested_fixes,
            raw_response=raw_text,
            model=self.model,
            input_hash=input_hash,
        )

    @staticmethod
    def _extract_response_text(response: object) -> str:
        """Extract text blocks from Anthropic response objects."""
        content = getattr(response, "content", None)
        if not content:
            return ""
        blocks: list[str] = []
        for block in content:
            if getattr(block, "type", None) == "text":
                blocks.append(getattr(block, "text", ""))
        return "\n".join(blocks).strip()

    @staticmethod
    def _build_prompt(failure_text: str, context: str | None = None) -> str:
        """Prompt for structured JSON diagnosis output."""
        context_text = context if context else "none"
        return (
            "You are a build failure diagnosis assistant. "
            "Analyze the log and return ONLY valid JSON with fields: "
            "target (string or null), "
            "failure_type (one of: dependency_error, compilation_error, oom, flaky_test, "
            "missing_toolchain, configuration_error, timeout, test_failure, unknown), "
            "summary (string), root_cause (string), suggested_fixes (array of 2-5 strings). "
            "Do not include markdown.\n\n"
            f"Context: {context_text}\n\n"
            "Build log:\n"
            f"{failure_text}"
        )
