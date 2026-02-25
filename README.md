# devbox

A developer toolbox CLI for workspace provisioning, build-graph analysis, and AI-assisted diagnostics.

| Component | What it does |
|---|---|
| `devbox workspace` | Spin up Docker-based dev environments with warm-pool provisioning |
| `devbox build-analyzer` | Analyze dependency graphs, find critical paths and bottlenecks |
| `devbox ai-diagnose` | Pipe build output to Claude for AI-powered root-cause diagnosis |

## Architecture

```
devbox/
├── cli.py                   # Top-level Click group; wires all subcommands
├── workspace/               # Docker container lifecycle + warm pool
│   ├── commands.py          # CLI commands (create, list, connect, destroy, pool)
│   ├── docker_client.py     # docker-py SDK wrapper
│   ├── pool.py              # Warm pool manager
│   └── db.py                # SQLite workspace registry
├── build_analyzer/          # Bazel build graph analysis
│   ├── commands.py          # CLI commands (analyze)
│   ├── graph.py             # networkx DAG parsing + critical path
│   └── visualizer.py        # Interactive HTML report generator
├── ai_diagnose/             # Claude-powered build diagnostics
│   ├── commands.py          # CLI commands (diagnose)
│   ├── analyzer.py          # Anthropic API integration
│   └── db.py                # SQLite diagnosis history
└── utils/
    └── console.py           # Shared Rich console instance
```

## Installation

```bash
git clone <repo-url>
cd devbox
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

## Usage

```bash
# Top-level help
devbox --help
devbox --version

# Workspace management
devbox workspace create myenv --template base
devbox workspace list
devbox workspace connect myenv
devbox workspace destroy myenv

# Warm pool
devbox workspace pool init --size 3
devbox workspace pool status

# Build graph analysis
devbox build-analyzer analyze               # analyzes //... in current Bazel workspace
devbox build-analyzer analyze //my/pkg/... --visualize --open

# AI diagnosis
bazel build //... 2>&1 | devbox ai-diagnose diagnose   # pipe from stdin
devbox ai-diagnose diagnose build.log                   # from file
devbox ai-diagnose diagnose --dry-run                   # demo mode, no API call
devbox ai-diagnose diagnose --history                   # show past diagnoses
devbox ai-diagnose diagnose --patterns                  # group by failure type + target
```

## Development Status

| Phase | Status | Description |
|---|---|---|
| 1 | ✅ Complete | Project scaffolding and CLI skeleton |
| 2 | ✅ Complete | Workspace provisioner with Docker warm pool and metrics |
| 3 | ✅ Complete | Build graph analyzer with HTML visualization |
| 4 | ✅ Complete | AI diagnosis with Claude API and SQLite history/patterns |

## Tech Stack

- [Click](https://click.palletsprojects.com/) — CLI framework
- [Rich](https://rich.readthedocs.io/) — terminal formatting
- [docker-py](https://docker-py.readthedocs.io/) — Docker SDK
- [networkx](https://networkx.org/) — graph analysis
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) — Claude API
- [python-dotenv](https://saurabh-kumar.com/python-dotenv/) — `.env` loading
