from __future__ import annotations

import tempfile
import shutil

from node.chain import Blockchain
from node.block import Block


def test_add_genesis_and_block_validation():
    tmp = tempfile.mkdtemp(prefix="coin-chain-")
    try:
        chain = Blockchain(tmp)
        # create genesis coinbase manually
        coinbase = {"inputs": [], "outputs": [{"value": 100, "address": "aa"}], "coinbase": True}
        import hashlib, json
        coinbase["txid"] = hashlib.sha256(json.dumps({"inputs": [], "outputs": coinbase["outputs"]}, sort_keys=True).encode()).hexdigest()
        genesis = Block.create(index=0, prev_hash="0" * 64, transactions=[coinbase])
        assert chain.add_block(genesis, difficulty=0)
        # add empty tx block
        b1 = Block.create(index=1, prev_hash=genesis.compute_hash(), transactions=[])
        b1.nonce = 0
        # no PoW requirement in this test
        assert chain.add_block(b1, difficulty=0)
        assert chain.height == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


