#!/usr/bin/env bash
set -euo pipefail

DATA1=/tmp/coin-node1
DATA2=/tmp/coin-node2
rm -rf "$DATA1" "$DATA2"

ADDR="$(python3 - <<'PY'
from wallet.wallet import KeyPair
kp = KeyPair.generate()
print(kp.address)
PY
)"

python3 /home/kali/Documents/Coin/scripts/genesis.py --data "$DATA1" --address "$ADDR"
python3 /home/kali/Documents/Coin/rpc/explorer.py --data "$DATA1" --port 8080 &
echo "Explorer running at http://localhost:8080"

wait
