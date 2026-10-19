# Automated validation

Run the service tests from the repository root:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

The suite covers chat authentication and response behavior, input/output guardrails, e-mail redaction, role-protected operational endpoints, session history isolation and deletion, request-body limits, bounded memory retention/capacity, memory expiry, and safe handling/logging of unexpected errors. API tests replace Ollama with a deterministic in-process model and use temporary storage.

The automated suite does not require Ollama, real API keys, or network access. Live Ollama generation, Docker image build, and an external Prometheus scrape are deployment checks and are not covered by these tests.
