# ARCHE (ARC) Blockchain

A production-grade blockchain implementation in Python.

## Features

- **UTXO model** — Bitcoin-style unspent transaction outputs
- **Proof of Work** — double-SHA256, 256-bit integer target comparison
- **BIP39 wallet** — 2048-word mnemonic, encrypted with AES-256-GCM + scrypt
- **P2P networking** — persistent connections, network magic, rate limiting
- **Replay protection** — chain_id in signing domain (mainnet/testnet/regtest)
- **Coinbase maturity** — 100 block lockup enforced at consensus level
- **Fork/reorg** — cumulative chain-work based chain selection
- **Web explorer** — live block/tx/address browser
- **3 network modes** — mainnet, testnet, regtest

## Coin Parameters

| Parameter | Value |
|-----------|-------|
| Ticker | ARC |
| Max Supply | 50,000,000 ARC |
| Block Reward | 50 ARC (halving every 500,000 blocks) |
| Block Time | 2 minutes |
| Coinbase Maturity | 100 blocks |
| Address Prefix | A (Base58Check) |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Create wallet
python -m wallet.cli_wallet create --base58

# Create genesis block
python -m scripts.genesis --data ./arc-data --address <YOUR_ADDRESS> --difficulty 1

# Run node
python -m node.node --data ./arc-data --port 9333 --http-port 9334 \
  --difficulty 1 --mine --miner <YOUR_ADDRESS> --no-retarget --network testnet

# Run explorer
python -m rpc.explorer --data ./arc-data --port 8080
# Open http://127.0.0.1:8080/ui/index.html
```

## Regtest Demo

```bash
python scripts/regtest_demo.py
```

## Run Tests

```bash
python test_all.py
```

## Project Structure

```
coin_params.py          # All network constants (single source of truth)
node/
  block.py              # Block structure, hashing, PoW
  chain.py              # Blockchain, UTXO, validation, reorg
  tx.py                 # Transactions, signing, validation
  pow.py                # Mining, difficulty retarget
  storage.py            # LevelDB / JSON KV store
  p2p.py                # P2P networking, network magic, rate limit
  node.py               # Full node (P2P + mempool + HTTP API)
  network.py            # Network params (mainnet/testnet/regtest)
wallet/
  wallet.py             # BIP39, HD keys, encrypted storage
  cli_wallet.py         # Wallet CLI
rpc/
  explorer.py           # HTTP explorer API
explorer/               # Web frontend (HTML/CSS/JS)
scripts/
  genesis.py            # Genesis block generator
  regtest_demo.py       # End-to-end demo
tests/                  # Test suites
docs/
  CONSENSUS.md          # Full consensus specification
  THREAT_MODEL.md       # Security threat model
audit/                  # Audit reports
```

## Security

- Private keys encrypted with AES-256-GCM + scrypt
- Signatures use secp256k1 via `coincurve` (libsecp256k1 binding — no timing leaks)
- See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for full threat analysis

## License

MIT
