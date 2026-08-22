from __future__ import annotations

import hashlib
import json

from wallet.wallet import KeyPair
from node.tx import UTXOSet, TxOutput, TxInput, Transaction, create_signed_tx, validate_transaction


def test_create_and_validate_transaction():
    # Prepare a UTXO belonging to sender
    sender = KeyPair.generate()
    to = KeyPair.generate().address
    # fabricate a previous tx output paying to sender
    prev_outputs = [{"value": 5000, "address": sender.address}]
    prev_txid = hashlib.sha256(json.dumps({"inputs": [], "outputs": prev_outputs}, sort_keys=True).encode()).hexdigest()

    utxo = UTXOSet()
    utxo.utxos[(prev_txid, 0)] = TxOutput(value=5000, address=sender.address)

    tx = create_signed_tx(sender, [(prev_txid, 0, 5000, sender.address)], to, 1200, sender.address)
    assert validate_transaction(tx, utxo)

    # Apply spend and ensure double-spend fails
    utxo.spend(TxInput(txid=prev_txid, index=0, signature=tx.inputs[0].signature, pubkey=tx.inputs[0].pubkey))
    assert not validate_transaction(tx, utxo)


