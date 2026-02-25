"""Anthropic Claude API integration for AI-powered build diagnostics.

Sends build/test failure output to Claude and returns a structured
root-cause analysis with suggested fixes. Failure classification
covers common Bazel build failure modes:
  - dependency_error: missing or incompatible dependencies
  - compilation_error: syntax or type errors in source code
  - oom: out-of-memory during build or test
  - flaky_test: test that passes intermittently
  - missing_toolchain: required compiler/tool not found
  - configuration_error: misconfigured BUILD file or .bazelrc
  - timeout: build or test exceeded time limit

Phase 2 implementation plan:
  DiagnosisResult dataclass:
    - failure_type: str   (one of the categories above)
    - summary: str        (one-sentence plain-English summary)
    - root_cause: str     (detailed explanation)
    - suggested_fixes: list[str]  (numbered action items)
    - raw_response: str   (full Claude response for debugging)
    - model: str
    - input_hash: str     (SHA-256 of the input log, for deduplication)

  Analyzer class:
    - __init__(self, model: str, api_key: str | None = None)
        api_key falls back to os.environ["ANTHROPIC_API_KEY"].
    - diagnose(failure_text: str, context: str | None = None) -> DiagnosisResult
    - _build_prompt(failure_text: str, context: str | None) -> str
        Constructs a structured prompt instructing Claude to return
        a JSON object matching the DiagnosisResult schema.
"""
