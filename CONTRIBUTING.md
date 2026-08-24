# Contributing to ARCHE

Thank you for your interest in contributing to ARCHE.

---

## Getting Started

```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
pip install -r requirements-dev.txt
python test_all.py  # All 12 suites must pass before you start
```

---

## Rules

1. **Test first** — write a failing test before fixing a bug or adding a feature
2. **All tests must pass** — `python test_all.py` must show `Failed: 0` before submitting a PR
3. **Never mock consensus** — do not fake consensus rules just to make tests pass
4. **No private keys in commits** — check `.gitignore`, never commit wallet files
5. **Read VISION.md first** — understand the project direction before proposing big changes

---

## Areas That Need Help

| Priority | Area | Notes |
|----------|------|-------|
| 🔴 High | VPS deployment | Set up a public node |
| 🔴 High | AI Worker runtime | Integrate PyTorch/ONNX for real inference |
| 🟡 Medium | Explorer UI for AI | Show jobs/workers in the browser |
| 🟡 Medium | Payment automation | Automate escrow transactions |
| 🟢 Low | Documentation | Fix or expand guides |
| 🔬 Research | ZKML | Follow developments in ZK library ecosystem |

See [audit/](audit/) for a list of identified bugs and issues.

---

## Pull Request

- Branch name: `feature/...` or `fix/...`
- One logical change per commit
- Explain what you changed and why in the PR description
- No unnecessary references to other projects

## Code Style

- Python 3.11+, type hints where practical
- `snake_case` for functions and variables
- All network constants in `coin_params.py` — never hardcode values
- Read `docs/VISION.md` to understand the project direction
