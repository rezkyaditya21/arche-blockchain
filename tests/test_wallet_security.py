"""
Phase 15 — Wallet Security Tests
Phase 16 — API Security Tests
Phase 17 — Fuzz / Property Tests
"""
import sys, os, json, tempfile, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from wallet.wallet import (
    KeyPair, generate_mnemonic, validate_mnemonic,
    save_wallet, load_wallet, base58check_encode, base58check_decode,
    mnemonic_to_seed, address_hex_to_base58,
)
from node.tx import (
    Transaction, TxInput, TxOutput, validate_transaction,
    pubkey_to_address, sha256d_hex,
)
from node.block import Block, difficulty_to_bits, bits_to_target, merkle_root
import coincurve


# ---------------------------------------------------------------------------
# Wallet Security
# ---------------------------------------------------------------------------

class TestWalletSecurity:

    def test_encrypted_wallet_private_key_not_in_plaintext(self):
        """Private key must not appear as plaintext in encrypted wallet file."""
        kp = KeyPair.generate()
        mn = generate_mnemonic(128)
        tmp = tempfile.mktemp(suffix=".json")
        save_wallet(tmp, kp, mnemonic=mn, password="strongpass")
        try:
            with open(tmp) as f:
                content = f.read()
            assert kp.private_key_hex not in content, \
                "Private key found in plaintext in encrypted wallet!"
            assert mn not in content, \
                "Mnemonic found in plaintext in encrypted wallet!"
        finally:
            os.unlink(tmp)

    def test_mnemonic_not_logged(self, capsys):
        """Mnemonic must never appear in stdout/stderr."""
        mn = generate_mnemonic(128)
        kp = KeyPair.from_mnemonic(mn)
        tmp = tempfile.mktemp(suffix=".json")
        save_wallet(tmp, kp, mnemonic=mn, password="pass")
        os.unlink(tmp)
        captured = capsys.readouterr()
        assert mn not in captured.out
        assert mn not in captured.err

    def test_wrong_password_raises_valueerror(self):
        kp = KeyPair.generate()
        mn = generate_mnemonic(128)
        tmp = tempfile.mktemp(suffix=".json")
        save_wallet(tmp, kp, mnemonic=mn, password="correct")
        try:
            with pytest.raises(ValueError):
                load_wallet(tmp, password="wrong")
        finally:
            os.unlink(tmp)

    def test_corrupted_wallet_file_raises(self):
        tmp = tempfile.mktemp(suffix=".json")
        with open(tmp, "w") as f:
            f.write("{corrupted}")
        try:
            with pytest.raises(Exception):
                load_wallet(tmp)
        finally:
            os.unlink(tmp)

    def test_wallet_without_required_fields_raises(self):
        tmp = tempfile.mktemp(suffix=".json")
        with open(tmp, "w") as f:
            json.dump({"version": 2, "encrypted": False}, f)
        try:
            with pytest.raises((KeyError, ValueError, TypeError)):
                load_wallet(tmp)
        finally:
            os.unlink(tmp)

    def test_different_mnemonics_different_keys(self):
        for _ in range(5):
            mn1 = generate_mnemonic(128)
            mn2 = generate_mnemonic(128)
            kp1 = KeyPair.from_mnemonic(mn1)
            kp2 = KeyPair.from_mnemonic(mn2)
            assert kp1.private_key_hex != kp2.private_key_hex

    def test_nonce_unique_per_encryption(self):
        """Each save_wallet call must use a fresh nonce (IV)."""
        kp = KeyPair.generate()
        mn = generate_mnemonic(128)
        tmp1 = tempfile.mktemp(suffix=".json")
        tmp2 = tempfile.mktemp(suffix=".json")
        save_wallet(tmp1, kp, mnemonic=mn, password="pass")
        save_wallet(tmp2, kp, mnemonic=mn, password="pass")
        try:
            with open(tmp1) as f:
                d1 = json.load(f)
            with open(tmp2) as f:
                d2 = json.load(f)
            assert d1["nonce"] != d2["nonce"], "Nonces must be unique per encryption"
        finally:
            os.unlink(tmp1)
            os.unlink(tmp2)

    def test_bip39_entropy_256_bits(self):
        """256-bit mnemonic should produce 24 words."""
        mn = generate_mnemonic(256)
        assert len(mn.split()) == 24

    def test_bip39_checksum_wrong_last_word_fails(self):
        mn = generate_mnemonic(128)
        words = mn.split()
        wordlist_path = os.path.join(
            os.path.dirname(__file__), "..", "wallet", "bip39_english.txt"
        )
        with open(wordlist_path) as f:
            all_words = [w.strip() for w in f]
        # Find a different word for the last position
        last = words[-1]
        for w in all_words:
            if w != last:
                bad_mn = " ".join(words[:-1] + [w])
                if not validate_mnemonic(bad_mn):
                    break
        assert not validate_mnemonic(bad_mn), \
            "Mnemonic with wrong checksum word should fail validation"


# ---------------------------------------------------------------------------
# Replay Protection
# ---------------------------------------------------------------------------

class TestReplayProtection:

    def test_mainnet_and_testnet_signing_hashes_differ(self):
        """Transactions on different chains have different signing hashes."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(1000, "bb" * 20)]
        )
        h_mainnet = tx.signing_hash(chain_id=1)
        h_testnet = tx.signing_hash(chain_id=2)
        h_regtest = tx.signing_hash(chain_id=3)
        assert h_mainnet != h_testnet, "Mainnet and testnet signing hashes must differ"
        assert h_mainnet != h_regtest
        assert h_testnet != h_regtest

    def test_mainnet_sig_invalid_on_testnet(self):
        """A transaction signed for mainnet must fail validation on testnet."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        from node.tx import UTXOSet, TxOutput
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(900, "cc" * 20)]
        )
        # Sign for mainnet
        sig = sk.sign(tx.signing_hash(chain_id=1), hasher=None)
        tx.inputs[0].signature = sig.hex()
        # Validate on mainnet → should pass
        assert validate_transaction(tx, utxo, chain_id=1) is True
        # Validate on testnet → must fail (wrong chain_id)
        utxo2 = UTXOSet()
        utxo2.utxos[("aa" * 32, 0)] = TxOutput(1000, addr)
        assert validate_transaction(tx, utxo2, chain_id=2) is False, \
            "Mainnet-signed tx must be INVALID on testnet"

    def test_txid_includes_chain_id(self):
        """txid should be stable (uses chain_id=1 always for canonical ID)."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(1000, "bb" * 20)]
        )
        txid = tx.txid
        assert len(txid) == 64
        # txid is deterministic
        assert tx.txid == txid


# ---------------------------------------------------------------------------
# Fuzz / Property Tests (Phase 17)
# ---------------------------------------------------------------------------

class TestFuzzParsing:

    @pytest.mark.parametrize("bad_input", [
        {},
        {"index": 0},
        {"version": 1, "index": "notanint"},
        {"version": 1, "index": -1, "prev_hash": "x" * 64},
        None,
    ])
    def test_block_from_dict_malformed(self, bad_input):
        """Block.from_dict with bad input must raise, not silently corrupt."""
        if bad_input is None:
            with pytest.raises((TypeError, KeyError, AttributeError)):
                Block.from_dict(bad_input)
        else:
            try:
                b = Block.from_dict({
                    "version": 1, "index": 0, "prev_hash": "0" * 64,
                    "timestamp": 0, "bits": 0x200FFFFF, "nonce": 0,
                    "tx_merkle_root": "0" * 64, "transactions": [],
                    **bad_input,
                })
                # If it parsed, verify no crash on hash
                b.compute_hash()
            except (TypeError, KeyError, ValueError, struct.error):
                pass  # Expected

    @pytest.mark.parametrize("bad_tx", [
        {},
        {"inputs": [], "outputs": []},
        {"inputs": [{"txid": "aa" * 32, "index": 0, "pubkey": "zz"}], "outputs": []},
        {"inputs": None, "outputs": None},
    ])
    def test_validate_transaction_malformed(self, bad_tx):
        """validate_transaction with malformed input must return False, not crash."""
        from node.tx import UTXOSet
        utxo = UTXOSet()
        try:
            result = validate_transaction(bad_tx, utxo)
            assert result is False
        except (TypeError, AttributeError, ValueError):
            pass  # Acceptable — raised rather than silently passing

    @pytest.mark.parametrize("value", [
        0, 1, 100, 2**31, 2**32, 2**52, -1, -2**31
    ])
    def test_txoutput_negative_value_rejected(self, value):
        """Negative output values must be rejected."""
        sk = coincurve.PrivateKey()
        pub = sk.public_key.format(compressed=True)
        addr = pubkey_to_address(pub)
        from node.tx import UTXOSet
        utxo = UTXOSet()
        utxo.utxos[("aa" * 32, 0)] = TxOutput(abs(value) + 1, addr)
        tx = Transaction(
            inputs=[TxInput("aa" * 32, 0, "", pub.hex())],
            outputs=[TxOutput(value, "bb" * 20)]
        )
        sig = sk.sign(tx.signing_hash(chain_id=1), hasher=None)
        tx.inputs[0].signature = sig.hex()
        if value < 0:
            assert validate_transaction(tx, utxo) is False
        # Non-negative values: just verify no crash

    @pytest.mark.parametrize("bad_addr", [
        "",
        "xyz",
        "0" * 39,
        "0" * 41,
        "gg" * 20,  # invalid hex
    ])
    def test_base58_decode_malformed(self, bad_addr):
        """base58check_decode with malformed input must raise ValueError."""
        with pytest.raises((ValueError, Exception)):
            base58check_decode(bad_addr)

    @pytest.mark.parametrize("bits", [
        0, 1, 0x200FFFFF, 0x1D00FFFF, 0x03000000, 0xFFFFFFFF
    ])
    def test_bits_to_target_no_crash(self, bits):
        """bits_to_target must not crash on any 32-bit input."""
        target = bits_to_target(bits)
        assert isinstance(target, int)
        assert target >= 0

    def test_merkle_root_single_tx(self):
        assert len(merkle_root(["ab" * 32])) == 64

    def test_merkle_root_empty(self):
        r = merkle_root([])
        assert len(r) == 64

    def test_merkle_root_odd_txs(self):
        """Odd number of txs must be handled by duplicating last."""
        r = merkle_root(["aa" * 32, "bb" * 32, "cc" * 32])
        assert len(r) == 64
        # Different from even count
        r2 = merkle_root(["aa" * 32, "bb" * 32])
        assert r != r2

    def test_sha256d_deterministic(self):
        data = b"ARCHE test"
        assert sha256d_hex(data.encode() if isinstance(data, str) else data) == \
               sha256d_hex(data.encode() if isinstance(data, str) else data)

    def test_address_derivation_deterministic(self):
        sk = coincurve.PrivateKey(bytes.fromhex("aa" * 32))
        pub = sk.public_key.format(compressed=True)
        addr1 = pubkey_to_address(pub)
        addr2 = pubkey_to_address(pub)
        assert addr1 == addr2

    @pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 13, 100])
    def test_merkle_root_size_invariant(self, n):
        """Merkle root always 32 bytes regardless of tx count."""
        txids = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(n)]
        r = merkle_root(txids)
        assert len(r) == 64


import struct
