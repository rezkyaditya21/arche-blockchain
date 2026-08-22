# Contributing to ARCHE

Thank you for your interest in contributing.

## Getting Started

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
pip install -r requirements-dev.txt
python test_all.py  # all 7 suites must pass before you start
```

## Rules

1. **Tests first** — write a failing test before fixing a bug or adding a feature
2. **All tests must pass** — `python test_all.py` must show `Failed: 0` before PR
3. **No consensus shortcuts** — never mock consensus rules to make tests pass
4. **No private keys in commits** — check `.gitignore`, never commit wallet files

## What to work on

- See [audit/consensus_audit.md](audit/consensus_audit.md) for known consensus gaps
- See [audit/security_audit.md](audit/security_audit.md) for security improvements
- See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for remaining risks

## Pull Request

- Branch name: `feature/...` or `fix/...`
- Keep commits focused — one logical change per commit
- Describe what you changed and why in the PR description

## Code Style

- Python 3.11+, type hints where practical
- `snake_case` for functions and variables
- Constants in `coin_params.py` — never hardcode network values
