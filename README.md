# devbox

I built `devbox` as a Python CLI for developer productivity workflows!

It has three core capabilities:
- Fast containerized workspaces with warm-pool provisioning
- Bazel dependency-graph analysis (critical path + bottlenecks)
- AI-assisted build failure diagnosis with local history/pattern tracking


## What You Can Do

| Command Group | Purpose | Output |
|---|---|---|
| `devbox workspace` | Create and manage Docker-based dev environments | Live workspace list, connect shell, destroy, warm-pool status |
| `devbox build-analyzer` | Analyze Bazel target dependency graphs | Critical path, bottleneck targets, optional interactive HTML report |
| `devbox ai-diagnose` | Diagnose build log failures using AI (or dry run) | Structured root cause + suggested fixes + saved history/patterns |

## Prerequisites

- Python 3.11+
- Docker Desktop running
- Bazel/Bazelisk installed (for build analyzer)
- Anthropic API key (for real `ai-diagnose`; dry-run works without it)

## Installation

```bash
git clone <repo-url>
cd devbox
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration

Create your `.env` file:

```bash
cp .env.example .env
```

Set:

```bash
ANTHROPIC_API_KEY=your_key_here
```

Optional environment variables:

- `DEVBOX_DB_DIR`: custom directory for local SQLite DB files
- `DEVBOX_DOCKER_PLATFORM`: force Docker platform (example: `linux/arm64`)
- `USE_BAZEL_VERSION`: pin Bazelisk version (example: `9.0.0`)

## Quick Start (End-to-End)

From project root:

```bash
source venv/bin/activate

# 1) Workspace: warm pool + create + list
DEVBOX_DOCKER_PLATFORM=linux/arm64 devbox workspace pool init --size 2 --template bazel-python
devbox workspace create demo --template bazel-python
devbox workspace list

# 2) Build analyzer: summary + HTML
export USE_BAZEL_VERSION=9.0.0
devbox build-analyzer analyze -p sample-project //app:integration_test --visualize -o build-report.html
open build-report.html

# 3) AI diagnose: dry-run + real + history
printf "ERROR: //app:cli timed out while compiling\n" | devbox ai-diagnose diagnose --dry-run
printf "ERROR: //app:cli timed out while compiling\n" | devbox ai-diagnose diagnose
devbox ai-diagnose diagnose --history
devbox ai-diagnose diagnose --patterns
```

## Feature Guide

### 1) Workspace Provisioner (`devbox workspace`)

Create a workspace:

```bash
devbox workspace create myenv --template bazel-python --cpu 2 --memory 4g
```

List workspaces (includes state, uptime, live usage):

```bash
devbox workspace list
```

Connect to a workspace shell:

```bash
devbox workspace connect myenv
```

Destroy a workspace:

```bash
devbox workspace destroy myenv --force
```

Warm pool commands:

```bash
devbox workspace pool init --size 3 --template bazel-python
devbox workspace pool status
```

Supported built-in templates:

- `base`
- `python`
- `node`
- `bazel-python`
- `bazel-java`

### 2) Bazel Build Analyzer (`devbox build-analyzer`)

Analyze all dependencies for a target:

```bash
devbox build-analyzer analyze -p sample-project //app:integration_test
```

Generate interactive HTML visualization:

```bash
devbox build-analyzer analyze \
  -p sample-project \
  //app:integration_test \
  --visualize \
  --output build-report.html
```

Auto-open report after generation:

```bash
devbox build-analyzer analyze -p sample-project //app:integration_test --visualize --open
```

What the analyzer computes:

- Node and edge counts
- Critical path (longest dependency chain)
- Bottleneck targets (high in-degree + out-degree)
- Parallelism estimate

### 3) AI Build Failure Analyzer (`devbox ai-diagnose`)

Diagnose from a file:

```bash
devbox ai-diagnose diagnose /path/to/build.log
```

Diagnose from piped output:

```bash
bazel build //app:integration_test 2>&1 | devbox ai-diagnose diagnose
```

Demo mode (no API call):

```bash
devbox ai-diagnose diagnose /path/to/build.log --dry-run
```

History and recurring patterns:

```bash
devbox ai-diagnose diagnose --history
devbox ai-diagnose diagnose --patterns
```

## How It Works

### Workspace subsystem

- `devbox/workspace/docker_client.py`
  - Builds local template images from `templates/<name>/Dockerfile` when present
  - Pulls remote images when no local template exists
  - Selects host-compatible Docker platform (important on Apple Silicon)
  - Creates/stops/removes/renames containers and reads live stats

- `devbox/workspace/db.py`
  - Stores workspace metadata in SQLite
  - Tracks name, state, template, container ID, resources
  - Stores warm-pool settings (target size/template)

- `devbox/workspace/pool.py`
  - Maintains pre-created warm containers
  - Claims a warm container on `workspace create` (fast path)
  - Replenishes pool asynchronously in the background

### Build analyzer subsystem

- `devbox/build_analyzer/graph.py`
  - Runs `bazel query deps(...) --output graph`
  - Parses DOT graph text into a `networkx.DiGraph`
  - Computes critical path using DAG longest-path logic
  - Scores bottlenecks by `in_degree + out_degree`

- `devbox/build_analyzer/visualizer.py`
  - Writes a self-contained HTML report
  - Highlights critical path and bottleneck nodes
  - Includes pan/zoom for easier graph exploration

### AI diagnosis subsystem

- `devbox/ai_diagnose/analyzer.py`
  - Reads build log text
  - Uses AI model for structured classification/root-cause/fix suggestions
  - Includes a `--dry-run` local heuristic mode for demos/tests

- `devbox/ai_diagnose/db.py`
  - Persists diagnoses in SQLite
  - Supports history view and aggregate pattern analysis by type/target

- `devbox/ai_diagnose/commands.py`
  - Handles CLI modes: diagnose, history, patterns
  - Renders structured output in Rich tables/panels

## Repository Layout

```text
devbox/
├── devbox/
│   ├── cli.py
│   ├── workspace/
│   ├── build_analyzer/
│   ├── ai_diagnose/
│   └── utils/
├── sample-project/          # Bazel graph demo project
├── templates/               # Workspace Docker templates
├── tests/                   # Unit tests
├── pyproject.toml
└── README.md
```

## Running Tests

```bash
source venv/bin/activate
python -m unittest discover -s tests -v
```

## Troubleshooting

Docker not reachable:

- Start Docker Desktop
- Re-run command

Architecture mismatch / rosetta errors on Apple Silicon:

```bash
unset DOCKER_DEFAULT_PLATFORM
DEVBOX_DOCKER_PLATFORM=linux/arm64 devbox workspace pool init --size 1 --template bazel-python
```

Bazel not found:

```bash
brew install bazelisk
bazel version
```

Bazelisk cannot resolve latest version:

```bash
export USE_BAZEL_VERSION=9.0.0
```

Missing API key for real AI diagnose:

- Set `ANTHROPIC_API_KEY` in `.env`
- Or use `--dry-run` for offline demo mode

## Notes

- This is a local demo project focused on clarity and architecture.
- The warm-pool, graph analysis, and diagnosis patterns are intentionally designed to be understandable and easy to demonstrate.
