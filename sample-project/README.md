# Sample Bazel Project

This workspace is intentionally structured for build-graph analysis demos.

It includes:
- Linear dependency chains (critical path candidates)
- Fan-in targets (many dependents)
- Independent branches that can execute in parallel

Run:

```bash
bazel query 'deps(//app:cli)' --output graph
```
