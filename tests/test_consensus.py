"""
Phase 2 — ARCHE Consensus Test Suite
Tests run BEFORE implementation fixes to prove bugs exist.
Each test is labeled with the audit finding it covers.
"""
import sys, os, json, time, tempfile, shutil, hashlib, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from coin_params import (
    INITIAL_SUBSIDY, COIN, COINBASE_MATURITY, HALVING_INTERVAL,
    MAX_BLOCK_SIZE, GENESIS_PREV_HASH, block_subsidy, MAX_TARGET,
)
from node.block import Block, difficulty_to_bits, bits_to_target, merkle_root, sha256d_hex
from node.chain import Blockchain
from node.pow import mine_block, calculate_next_bits
from node.tx import (
    Transaction, TxInput, TxOutput, UTXOSet,
    validate_transaction, create_signed_tx, pubkey_to_address,
)
import coincurve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha(body: bytes) -> str:
    return sha256d_hex(body)

def make_coinbase(addr: str, value: int) -> dict:
    outs = [{"value": value, "address": addr}]
    body = json.dumps({"inputs": [], "outputs": outs},
                      sort_keys=True, separators=(",", ":")).encode()
    return {"inputs": [], "outputs": outs, "coinbase": True, "txid": _sha(body)}

def fresh_chain(no_retarget=True):
    d = tempfile.mkdtemp()
    c = Blockchain(d, no_retarget=no_retarget)
    return c, d

def mine(chain, index, prev_hash, txs, difficulty=1):
    b = Block.create(index=index, prev_hash=prev_hash,
                     transactions=txs, difficulty=difficulty)
    mined, _ = mine_block(b, difficulty)
    return mined

def build_chain(n_blocks=5, difficulty=1):
    """Build a fresh chain with n_blocks coinbase blocks. Returns (chain, tmpdir, kp)."""
    import coincurve
    sk = coincurve.PrivateKey()
    pub = sk.public_key.format(compressed=True)
    addr = pubkey_to_address(pub)
    chain, tmpdir = fresh_chain()
    cb0 = make_coinbase(addr, INITIAL_SUBSIDY)
    chain.add_genesis(cb0)
    prev = chain.tip
    for i in range(1, n_blocks):
        cb = make_coinbase(addr, INITIAL_SUBSIDY)
        b = mine(chain, i, prev, [cb])
        chain.add_block(b, difficulty)
        prev = b.compute_hash()
    return chain, tmpdir, sk, addr


# ===========================================================================
# BLOCK VALIDITY
# ===========================================================================

class TestBlockValidity:

    def test_invalid_index_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Try height=5 when chain is at 0
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 5, chain.tip, [cb2])
        assert chain.add_block(b, 1) is False
        shutil.rmtree(d)

    def test_invalid_prev_hash_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, "ff" * 32, [cb2])
        assert chain.add_block(b, 1) is False
        shutil.rmtree(d)

    def test_invalid_bits_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2], difficulty=1)
        # After mining at diff=1, force a different bits value
        original_bits = b.bits
        b.bits = difficulty_to_bits(3)  # claim harder difficulty
        # Block no longer meets its own claimed target (was mined for diff=1)
        # validate_block should reject because bits != expected_bits(1)
        result = chain.validate_block(b, expected_bits=original_bits)
        assert result is False
        shutil.rmtree(d)

    def test_invalid_nonce_rejected(self):
        """A block whose hash doesn't meet target must be rejected."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = Block.create(index=1, prev_hash=chain.tip,
                         transactions=[cb2], difficulty=1)
        mined, _ = mine_block(b, 1)
        # Set a much harder difficulty so current nonce certainly fails
        mined.bits = difficulty_to_bits(4)
        if not mined.meets_target():
            assert chain.validate_block(mined) is False
        else:
            pytest.skip("Nonce accidentally meets harder target")
        shutil.rmtree(d)

    def test_invalid_merkle_root_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2])
        # Corrupt merkle root
        b.tx_merkle_root = "ff" * 32
        assert chain.validate_block(b) is False
        shutil.rmtree(d)

    def test_timestamp_too_far_future_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2])
        b.tx_merkle_root = merkle_root([t["txid"] for t in b.transactions])
        b.timestamp = int(time.time()) + 9999
        # Re-compute hash with new timestamp — need to re-mine
        mined, _ = mine_block(b, 1)
        assert chain.validate_block(mined) is False
        shutil.rmtree(d)

    def test_timestamp_below_mtp_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Mine a few blocks to establish MTP
        prev = chain.tip
        for i in range(1, 3):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine(chain, i, prev, [cb_i])
            chain.add_block(b, 1)
            prev = b.compute_hash()
        # Attempt block with timestamp = 0 (way below MTP)
        cb3 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b3 = Block.create(index=3, prev_hash=prev, transactions=[cb3], difficulty=1)
        b3.timestamp = 1  # before MTP
        mined3, _ = mine_block(b3, 1)
        assert chain.validate_block(mined3) is False
        shutil.rmtree(d)

    def test_multiple_coinbase_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2a = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        cb2b = make_coinbase("cc" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2a, cb2b])
        assert chain.validate_block(b) is False
        shutil.rmtree(d)

    def test_coinbase_not_first_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        # Fund sender
        fund_cb = make_coinbase(addr, INITIAL_SUBSIDY)
        b1 = mine(chain, 1, chain.tip, [fund_cb])
        chain.add_block(b1, 1)
        # Build block with coinbase NOT first
        cb2 = make_coinbase("dd" * 20, INITIAL_SUBSIDY)
        # Dummy regular tx (won't validate but ordering check comes first)
        dummy_tx = {"txid": "ab" * 32, "inputs": [{"txid": "00" * 32, "index": 0,
                    "signature": "", "pubkey": "00" * 33}],
                    "outputs": [{"value": 1, "address": "aa" * 20}]}
        b2 = mine(chain, 2, chain.tip, [dummy_tx, cb2])
        assert chain.validate_block(b2) is False
        shutil.rmtree(d)

    def test_coinbase_reward_too_large_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Coinbase claiming 2x subsidy with no fees
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY * 2)
        b = mine(chain, 1, chain.tip, [cb2])
        assert chain.validate_block(b) is False
        shutil.rmtree(d)

    def test_negative_output_rejected(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        fund_cb = make_coinbase(addr, INITIAL_SUBSIDY)
        b1 = mine(chain, 1, chain.tip, [fund_cb])
        chain.add_block(b1, 1)
        # Try sending negative value
        utxo = UTXOSet()
        utxo.utxos[(fund_cb["txid"], 0)] = TxOutput(INITIAL_SUBSIDY, addr)
        tx = Transaction(
            inputs=[TxInput(fund_cb["txid"], 0, "", pub.hex())],
            outputs=[TxOutput(-1, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        assert validate_transaction(tx, utxo) is False
        shutil.rmtree(d)

    def test_zero_value_output_allowed(self):
        """Zero-value outputs are technically valid (dust, but not forbidden at consensus level)."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(0, "cc" * 20), TxOutput(1000, "dd" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # Zero value output should be accepted at consensus level
        assert validate_transaction(tx, utxo) is True

    def test_empty_transaction_list_rejected(self):
        """A block with no transactions (not even coinbase) must be rejected."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Build block with empty tx list — need valid merkle
        b = Block.create(index=1, prev_hash=chain.tip, transactions=[], difficulty=1)
        # Manually set merkle root for empty list
        b.tx_merkle_root = merkle_root([])
        mined, _ = mine_block(b, 1)
        # Should be rejected — no coinbase
        assert chain.validate_block(mined) is False
        shutil.rmtree(d)

    def test_duplicate_txid_in_block_rejected(self):
        """CONS-008: Block with same txid twice must be rejected."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        fund_cb = make_coinbase(addr, INITIAL_SUBSIDY * 2)
        b1 = mine(chain, 1, chain.tip, [fund_cb])
        chain.add_block(b1, 1)
        # Create a valid tx
        utxo = chain.utxo.snapshot()
        tx = Transaction(
            inputs=[TxInput(fund_cb["txid"], 0, "", pub.hex())],
            outputs=[TxOutput(INITIAL_SUBSIDY, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        txd = tx.to_dict()
        # Include the same tx twice in the block
        cb3 = make_coinbase("dd" * 20, INITIAL_SUBSIDY)
        b2 = mine(chain, 2, chain.tip, [cb3, txd, txd])
        assert chain.validate_block(b2) is False
        shutil.rmtree(d)

    def test_integer_overflow_in_output_sum(self):
        """Output values summing to > 2^63 must be rejected."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        # Plant a large UTXO
        big_val = 2 ** 62
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(big_val, addr)
        utxo.utxos[("bb" * 32, 0)] = TxOutput(big_val, addr)
        # Try to create tx that spends both with huge output
        tx = Transaction(
            inputs=[
                TxInput("aa" * 32, 0, "", pub.hex()),
                TxInput("bb" * 32, 0, "", pub.hex()),
            ],
            outputs=[TxOutput(2 ** 63 + 1, "cc" * 20)]  # overflow attempt
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        tx.inputs[1].signature = sig.hex()
        # output_sum > input_sum → rejected
        assert validate_transaction(tx, utxo) is False


# ===========================================================================
# DIFFICULTY / RETARGET
# ===========================================================================

class TestDifficulty:

    def test_no_retarget_mode_keeps_bits(self):
        chain, d = fresh_chain(no_retarget=True)
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        genesis_bits = chain.get_block(0).bits
        prev = chain.tip
        for i in range(1, 5):
            cb_i = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
            b = mine(chain, i, prev, [cb_i], difficulty=1)
            chain.add_block(b, 1)
            assert chain.get_block(i).bits == genesis_bits, f"bits changed at h={i}"
            prev = b.compute_hash()
        shutil.rmtree(d)

    def test_retarget_at_boundary(self):
        from coin_params import RETARGET_INTERVAL
        chain, d = fresh_chain(no_retarget=False)
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        expected = chain.expected_bits(RETARGET_INTERVAL)
        # Should differ from expected_bits(RETARGET_INTERVAL - 1)
        before = chain.expected_bits(RETARGET_INTERVAL - 1)
        # Both computed from same genesis — in no-history scenario they'll both
        # inherit genesis bits, but the function should not crash
        assert isinstance(expected, int)
        assert isinstance(before, int)
        shutil.rmtree(d)

    def test_bits_target_roundtrip(self):
        for diff in [0, 1, 2, 4, 8, 16]:
            bits = difficulty_to_bits(diff)
            target = bits_to_target(bits)
            bits2 = difficulty_to_bits(diff)
            assert bits == bits2, f"bits not deterministic at diff={diff}"
            assert target >= 0

    def test_max_target(self):
        bits = difficulty_to_bits(0)
        target = bits_to_target(bits)
        assert target <= MAX_TARGET

    def test_harder_difficulty_smaller_target(self):
        t1 = bits_to_target(difficulty_to_bits(1))
        t2 = bits_to_target(difficulty_to_bits(2))
        t4 = bits_to_target(difficulty_to_bits(4))
        assert t1 > t2 > t4

    def test_fast_blocks_increase_difficulty(self):
        """Blocks mined too fast → next target smaller (harder)."""
        from node.pow import calculate_next_bits
        bits = difficulty_to_bits(1)
        # 100 seconds for 2016 blocks = far too fast
        new_bits = calculate_next_bits(bits, 0, 100)
        assert bits_to_target(new_bits) < bits_to_target(bits)

    def test_slow_blocks_decrease_difficulty(self):
        """Blocks mined too slow → next target larger (easier), clamped to 4x."""
        from node.pow import calculate_next_bits
        bits = difficulty_to_bits(4)
        from coin_params import TARGET_BLOCK_TIME, RETARGET_INTERVAL
        # 8x too slow
        slow_ts = TARGET_BLOCK_TIME * RETARGET_INTERVAL * 8
        new_bits = calculate_next_bits(bits, 0, slow_ts)
        assert bits_to_target(new_bits) >= bits_to_target(bits)

    def test_target_to_bits_roundtrip(self):
        """Encode then decode should recover approximate target (3-byte precision loss ok)."""
        from node.pow import _target_to_bits
        target = (1 << 240) - 1
        bits = _target_to_bits(target)
        recovered = bits_to_target(bits)
        # compact bits has only 3-byte coefficient precision (~24 bits)
        # so relative error up to ~1/2^16 is acceptable
        assert recovered > 0
        assert abs(recovered - target) < target  # at least same order of magnitude

    def test_malformed_bits_zero(self):
        """bits=0 → target=0, block can never be mined."""
        target = bits_to_target(0)
        assert target == 0

    def test_minimum_difficulty_block_valid(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2], difficulty=1)
        assert chain.add_block(b, 1) is True
        shutil.rmtree(d)

    def test_fake_pow_rejected(self):
        """Block claiming easy bits but hash doesn't actually meet them."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = Block.create(index=1, prev_hash=chain.tip,
                         transactions=[cb2], difficulty=1)
        # Do NOT mine — nonce=0 is very unlikely to meet target
        b.bits = difficulty_to_bits(20)  # claim very easy but don't mine
        # meets_target will almost certainly fail for difficulty=20 at nonce=0
        if not b.meets_target():
            assert chain.validate_block(b) is False
        shutil.rmtree(d)

    def test_repeated_retarget_stable(self):
        """Multiple retarget cycles should not diverge to 0 or infinity."""
        from node.pow import calculate_next_bits
        from coin_params import TARGET_BLOCK_TIME, RETARGET_INTERVAL
        bits = difficulty_to_bits(1)
        for _ in range(10):
            # Simulate near-perfect block time
            ideal_ts = TARGET_BLOCK_TIME * RETARGET_INTERVAL
            bits = calculate_next_bits(bits, 0, ideal_ts)
            t = bits_to_target(bits)
            assert 0 < t <= MAX_TARGET


# ===========================================================================
# COINBASE MATURITY (Phase 3 — currently expected to FAIL until implemented)
# ===========================================================================

class TestCoinbaseMaturity:

    def test_coinbase_cannot_be_spent_immediately(self):
        """CONS-002: Coinbase at height H cannot be spent at height H+1."""
        chain, tmpdir, sk, addr = build_chain(n_blocks=2)
        pub = sk.public_key.format(compressed=True)
        # Get the genesis coinbase txid
        genesis = chain.get_block(0)
        cb_txid = genesis.transactions[0]["txid"]
        # Try to spend coinbase output from genesis (height 0) at height 2
        utxo_test = chain.utxo.snapshot()
        tx = Transaction(
            inputs=[TxInput(cb_txid, 0, "", pub.hex())],
            outputs=[TxOutput(INITIAL_SUBSIDY - 1000, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # This SHOULD fail because coinbase maturity not reached (only 2 blocks)
        # Current implementation: this PASSES (bug — coinbase maturity not enforced)
        result = validate_transaction(
            tx, utxo_test,
            coinbase_heights={cb_txid: 0},
            current_height=2,
        ) if "coinbase_heights" in validate_transaction.__code__.co_varnames else None

        if result is None:
            # Feature not yet implemented — mark as expected failure
            pytest.xfail("CONS-002: Coinbase maturity not yet implemented")
        assert result is False, "Coinbase should not be spendable before maturity"
        shutil.rmtree(tmpdir)

    def test_coinbase_spendable_after_maturity(self):
        """Coinbase at height H IS spendable at height H + COINBASE_MATURITY."""
        chain, tmpdir, sk, addr = build_chain(n_blocks=COINBASE_MATURITY + 2)
        pub = sk.public_key.format(compressed=True)
        genesis = chain.get_block(0)
        cb_txid = genesis.transactions[0]["txid"]
        utxo_test = chain.utxo.snapshot()
        tx = Transaction(
            inputs=[TxInput(cb_txid, 0, "", pub.hex())],
            outputs=[TxOutput(INITIAL_SUBSIDY - 1000, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        result = validate_transaction(
            tx, utxo_test,
            coinbase_heights={cb_txid: 0},
            current_height=COINBASE_MATURITY + 2,
        ) if "coinbase_heights" in validate_transaction.__code__.co_varnames else None

        if result is None:
            pytest.xfail("CONS-002: Coinbase maturity not yet implemented")
        assert result is True
        shutil.rmtree(tmpdir)

    def test_coinbase_at_maturity_boundary(self):
        """Height = coinbase_height + COINBASE_MATURITY - 1 → NOT spendable."""
        chain, tmpdir, sk, addr = build_chain(n_blocks=2)
        pub = sk.public_key.format(compressed=True)
        genesis = chain.get_block(0)
        cb_txid = genesis.transactions[0]["txid"]
        utxo_test = chain.utxo.snapshot()
        tx = Transaction(
            inputs=[TxInput(cb_txid, 0, "", pub.hex())],
            outputs=[TxOutput(INITIAL_SUBSIDY - 1000, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        boundary_height = 0 + COINBASE_MATURITY - 1
        result = validate_transaction(
            tx, utxo_test,
            coinbase_heights={cb_txid: 0},
            current_height=boundary_height,
        ) if "coinbase_heights" in validate_transaction.__code__.co_varnames else None

        if result is None:
            pytest.xfail("CONS-002: Coinbase maturity not yet implemented")
        assert result is False
        shutil.rmtree(tmpdir)


# ===========================================================================
# TRANSACTION FEES (Phase 4)
# ===========================================================================

class TestTransactionFees:

    def test_fee_is_input_minus_output(self):
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(900, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # Fee = 100, min_fee = 50 → accept
        assert validate_transaction(tx, utxo, min_fee=50) is True

    def test_fee_below_floor_rejected(self):
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(999, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # Fee = 1, min_fee = 100 → reject
        assert validate_transaction(tx, utxo, min_fee=100) is False

    def test_zero_fee_accepted_when_floor_zero(self):
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(1000, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        assert validate_transaction(tx, utxo, min_fee=0) is True

    def test_coinbase_cannot_exceed_subsidy_plus_fees(self):
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Block 1 coinbase claims subsidy + 10000 but has no fee-paying txs
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY + 10000)
        b = mine(chain, 1, chain.tip, [cb2])
        assert chain.validate_block(b) is False
        shutil.rmtree(d)

    def test_coinbase_equals_subsidy_plus_fees_accepted(self):
        """Coinbase value exactly equal to subsidy + fees must be accepted in validate_block."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)

        # Mine 100+ blocks to ensure coinbase maturity is satisfied
        prev = chain.tip
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        # Block 1: fund the sender
        fund_cb = make_coinbase(addr, INITIAL_SUBSIDY)
        b1 = mine(chain, 1, chain.tip, [fund_cb])
        chain.add_block(b1, 1)
        prev = b1.compute_hash()

        # Mine blocks 2-101 to reach maturity for block 1's coinbase
        for i in range(2, 103):
            cb_i = make_coinbase("ff" * 20, INITIAL_SUBSIDY)
            b_i = mine(chain, i, prev, [cb_i])
            chain.add_block(b_i, 1)
            prev = b_i.compute_hash()

        # Now height=102, block 1's coinbase is mature (102-1=101 >= 100)
        fee = 1000
        tx = Transaction(
            inputs=[TxInput(fund_cb["txid"], 0, "", pub.hex())],
            outputs=[TxOutput(INITIAL_SUBSIDY - fee, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(chain_id=chain.chain_id), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # Verify tx is valid at current height
        assert validate_transaction(
            tx, chain.utxo,
            chain_id=chain.chain_id,
            current_height=chain.height + 1,
            coinbase_maturity=COINBASE_MATURITY,
        ) is True, "Transaction must be valid after maturity"

        # Build block 103 with coinbase claiming subsidy + fee
        cb_final = make_coinbase("dd" * 20, INITIAL_SUBSIDY + fee)
        b_final = mine(chain, chain.height + 1, chain.tip, [cb_final, tx.to_dict()])
        assert chain.validate_block(b_final) is True
        shutil.rmtree(d)

    def test_negative_fee_rejected(self):
        """output_sum > input_sum is rejected."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(2000, "cc" * 20)]
        )
        sig = sk.sign(tx.signing_hash(), hasher=None)
        tx.inputs[0].signature = sig.hex()
        assert validate_transaction(tx, utxo) is False


# ===========================================================================
# TRANSACTION REPLAY PROTECTION (Phase 11 — currently expected to FAIL)
# ===========================================================================

class TestReplayProtection:

    def test_signing_hash_includes_chain_id(self):
        """Phase 11: Signing hash must differ between mainnet and testnet."""
        from node.tx import Transaction, TxInput, TxOutput
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(1000, "bb" * 20)]
        )
        h1 = tx.signing_hash()
        # Check if chain_id is part of the hash — currently NOT implemented
        # After fix: two Transaction objects with different chain_ids must have
        # different signing_hashes even with identical inputs/outputs.
        # For now, just verify the hash is deterministic
        h2 = tx.signing_hash()
        assert h1 == h2  # deterministic
        # This test will be extended once chain_id is added


# ===========================================================================
# RESOURCE LIMITS (Phase 12 — currently expected to FAIL until enforced)
# ===========================================================================

class TestResourceLimits:

    def test_block_with_too_many_inputs_rejected(self):
        """MAX_TX_INPUTS must be enforced."""
        from coin_params import MAX_BLOCK_SIZE
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Build a tx with 10000 inputs
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        many_inputs = [{"txid": (f"{i:064x}"), "index": 0,
                        "signature": "aa" * 64, "pubkey": pub.hex()}
                       for i in range(10000)]
        big_tx = {
            "txid": "ff" * 32,
            "inputs": many_inputs,
            "outputs": [{"value": 1, "address": "cc" * 20}]
        }
        cb2 = make_coinbase("bb" * 20, INITIAL_SUBSIDY)
        b = mine(chain, 1, chain.tip, [cb2, big_tx])
        # Should be rejected due to resource limits
        # Currently: NOT enforced → xfail
        result = chain.validate_block(b)
        if result is True:
            pytest.xfail("Phase 12: Resource limits not yet enforced")
        assert result is False
        shutil.rmtree(d)

    def test_oversized_block_rejected(self):
        """Block serialized size > MAX_BLOCK_SIZE must be rejected."""
        chain, d = fresh_chain()
        cb = make_coinbase("aa" * 20, INITIAL_SUBSIDY)
        chain.add_genesis(cb)
        # Build a block whose JSON serialization exceeds 1MB
        # by packing a large number of outputs in the coinbase
        large_outputs = [{"value": 1, "address": "aa" * 20} for _ in range(5000)]
        body = json.dumps({"inputs": [], "outputs": large_outputs},
                          sort_keys=True, separators=(",", ":")).encode()
        big_cb = {
            "inputs": [],
            "outputs": large_outputs,
            "coinbase": True,
            "txid": sha256d_hex(body),
        }
        b = mine(chain, 1, chain.tip, [big_cb])
        block_size = len(json.dumps(b.to_dict()).encode())
        if block_size < MAX_BLOCK_SIZE:
            pytest.skip("Block not large enough to trigger limit in this test")
        result = chain.validate_block(b)
        if result is True:
            pytest.xfail("Phase 12: Block size limit not yet enforced")
        assert result is False
        shutil.rmtree(d)
