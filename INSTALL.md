# ARCHE Installation Guide

Complete guide to running an ARCHE node from scratch.

> ⚠️ **Current status:** The network is not yet publicly deployed. Your node will run locally.
> Once a public VPS is live, your node will automatically connect to the network.

---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| OS | Windows 10/11, macOS 12+, Ubuntu 20.04+ |
| Python | 3.11 or newer |
| RAM | 1 GB |
| Storage | 1 GB |
| Internet | Required for peer sync |

---

## Step 0 — Install Python (if not already installed)

**Check if Python is installed:**
```bash
python --version
```

If not installed or version is below 3.11:

**Windows:**
- Download from https://python.org/downloads
- During install, check **"Add Python to PATH"**
- Restart terminal after install

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install python3.11 python3-pip
```

**macOS:**
```bash
brew install python@3.11
```

---

## Step 1 — Download ARCHE

**Option 1 — Git (recommended):**
```bash
git clone https://github.com/rezkyaditya21/arche-blockchain.git
cd arche-blockchain
```

**Option 2 — Download ZIP:**
- Go to https://github.com/rezkyaditya21/arche-blockchain
- Click the green **Code** button → **Download ZIP**
- Extract to any folder
- Open a terminal in that folder

---

## Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

If you get `pip not found`:
```bash
python -m pip install -r requirements.txt
```

> **Windows note:** LevelDB (fast database) is not available on Windows without
> Microsoft C++ Build Tools. ARCHE automatically falls back to a JSON store —
> this is normal and works fine for testnet.

---

## Step 3 — Create a Wallet

```bash
python -m wallet.cli_wallet create --base58
```

Example output:
```json
{
  "address_hex": "4782fc318e605987dc49266a7ef395802e02c41f",
  "address_base58": "ANHzY8BvJ2gR7MUWNtyYK8FkdBSaf5Txpr",
  "mnemonic": "soldier mountain legend alert rice valid access hurdle hand boss fantasy tent",
  "encrypted": false
}
```

> ⚠️ **IMPORTANT:** Save your 12-word mnemonic somewhere safe (write it on paper).
> This is the only way to recover your wallet if the file is lost.
> Never share your mnemonic with anyone.

**Create an encrypted wallet (more secure):**
```bash
python -m wallet.cli_wallet create --base58 --password "yourpassword"
```

---

## Step 4 — Create Genesis Block

This step only needs to be done **once** during first-time setup.

```bash
python -m scripts.genesis --data ./arc-data --address <YOUR_ADDRESS> --difficulty 1
```

Replace `<YOUR_ADDRESS>` with the `address_hex` from Step 3.

---

## Step 5 — Run Node and Start Mining

```bash
python -m node.node \
  --data ./arc-data \
  --port 9333 \
  --http-port 9334 \
  --difficulty 1 \
  --mine \
  --miner <YOUR_ADDRESS> \
  --no-retarget \
  --network testnet
```

**Windows (single line):**
```bash
python -m node.node --data ./arc-data --port 9333 --http-port 9334 --difficulty 1 --mine --miner <YOUR_ADDRESS> --no-retarget --network testnet
```

The node is running successfully when you see logs like:
```
[ARCHE] Node started  height=0
[ARC] Mined block h=1  0a3f...
[ARC] Mined block h=2  0b7c...
```

---

## Step 6 — Open Explorer (Optional)

Open a new terminal:
```bash
python -m rpc.explorer --data ./arc-data --port 8080
```

Open in browser: **http://127.0.0.1:8080/ui/index.html**

---

## Step 7 — Check Balance

```bash
python -m wallet.cli_wallet balance <YOUR_ADDRESS> --rpc http://127.0.0.1:9334
```

> **Note:** Mining rewards (coinbase) cannot be spent immediately.
> You must wait **100 blocks** after the reward is received (coinbase maturity rule).

---

## Send ARC to Someone

```bash
python -m wallet.cli_wallet send <RECIPIENT_ADDRESS> <AMOUNT> \
  --wallet ~/.arc_wallet/default.json \
  --rpc http://127.0.0.1:9334 \
  --fee 1000 \
  --wait 60
```

Example — send **1 ARC** (= 100,000,000 base units):
```bash
python -m wallet.cli_wallet send ANHz...xxxx 100000000 --wallet ~/.arc_wallet/default.json --rpc http://127.0.0.1:9334 --fee 1000 --wait 60
```

---

## Recover Wallet from Mnemonic

If you switch computers or lose your wallet file:
```bash
python -m wallet.cli_wallet recover \
  --seed "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"
```

---

## Full Demo (Regtest)

To try all features automatically:
```bash
python scripts/regtest_demo.py
```

This demo will: create wallets, mine 101 blocks, send a transaction, verify balances, and test persistence after restart.

---

## FAQ

**Q: How long does blockchain sync take?**
A: Very fast for early testnet (under 1 minute). Depends on chain length.

**Q: How much is the mining reward?**
A: 50 ARC per block. Halving every 500,000 blocks. Total supply 50 million ARC.

**Q: Why can't I spend my mining reward right away?**
A: This is the **Coinbase Maturity Rule** — a standard security measure. Mining rewards must wait 100 blocks before they can be spent.

**Q: Which ports need to be open?**
A: Port **9333** (P2P) so other nodes can find you. Port 9334 (HTTP API) is optional.

**Q: Is my data safe if the computer shuts down?**
A: Yes. All data is stored in the `arc-data` folder. The node resumes from the last block when restarted.

**Q: Can I connect to other nodes right now?**
A: Not yet. The public network has not been deployed. Your node runs locally for now.

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: coincurve` | `pip install coincurve` |
| `ModuleNotFoundError: flask` | `pip install flask` |
| `RIPEMD160 unavailable` | `sudo apt install libssl-dev` (Linux) |
| `Port already in use` | Change `--port` to another number |
| `Address already in use` | A node is already running. Stop it or use a different port |
| Node not mining | Make sure `--mine` and `--miner` flags are set |
| Balance 0 after mining | Wait 100 blocks (coinbase maturity rule) |
