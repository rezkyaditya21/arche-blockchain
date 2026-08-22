"""
ARCHE Regtest Demo — Phase 14
Demonstrates the full lifecycle:
1. Create wallet
2. Mine blocks (instant in regtest)
3. Send a transaction
4. Mine the transaction
5. Verify balances
6. Restart node and verify state persistence
"""
import sys, os, json, shutil, tempfile, time, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from node.block import Block
from node.chain import Blockchain
from node.pow import mine_block
from node.tx import (
    Transaction, TxInput, TxOutput, create_signed_tx,
    validate_transaction, sha256d_hex,
)
from wallet.wallet import KeyPair, generate_mnemonic, save_wallet, load_wallet
from coin_params import INITIAL_SUBSIDY, COIN, COINBASE_MATURITY, to_arc

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def check(name, ok, detail=""):
    status = PASS if ok else FAIL
    msg = f"{status} {name}"
    if detail:
        msg += f" ({detail})"
    print(msg)
    results.append((name, ok))
    return ok

def make_coinbase(addr, value, height=0):
    outs = [{"value": value, "address": addr}]
    body = json.dumps({"inputs": [], "outputs": outs},
                      sort_keys=True, separators=(",", ":")).encode()
    return {"inputs": [], "outputs": outs, "coinbase": True, "txid": sha256d_hex(body)}

def mine(chain, index, prev, txs, difficulty=0):
    b = Block.create(index=index, prev_hash=prev, transactions=txs, difficulty=difficulty)
    mined, _ = mine_block(b, difficulty)
    return mined

print("=" * 55)
print("  ARCHE Regtest Demo")
print("=" * 55)

tmpdir = tempfile.mkdtemp()
wallet_dir = os.path.join(tmpdir, "wallets")
os.makedirs(wallet_dir)

try:
    # 1. Create wallets
    print("\n[1] Creating wallets...")
    mn_alice = generate_mnemonic(128)
    kp_alice = KeyPair.from_mnemonic(mn_alice)
    save_wallet(os.path.join(wallet_dir, "alice.json"), kp_alice, mnemonic=mn_alice)

    mn_bob = generate_mnemonic(128)
    kp_bob = KeyPair.from_mnemonic(mn_bob)
    save_wallet(os.path.join(wallet_dir, "bob.json"), kp_bob, mnemonic=mn_bob)

    check("Alice wallet created", os.path.exists(os.path.join(wallet_dir, "alice.json")))
    check("Bob wallet created", os.path.exists(os.path.join(wallet_dir, "bob.json")))
    check("Alice address starts with hex", len(kp_alice.address) == 40)

    # 2. Initialize chain (regtest: difficulty=0, instant mining)
    print("\n[2] Initializing regtest chain...")
    data_dir = os.path.join(tmpdir, "chain")
    chain = Blockchain(data_dir, no_retarget=True, network="regtest")
    cb0 = make_coinbase(kp_alice.address, INITIAL_SUBSIDY, height=0)
    genesis = chain.add_genesis(cb0)
    check("Genesis block created", chain.height == 0)
    check("Genesis prev_hash is zeros", genesis.prev_hash == "0" * 64)
    check("Alice has genesis balance", chain.get_balance(kp_alice.address) == INITIAL_SUBSIDY)

    # 3. Mine COINBASE_MATURITY + 2 blocks so we can spend genesis coinbase
    print(f"\n[3] Mining {COINBASE_MATURITY + 1} blocks for coinbase maturity...")
    prev = chain.tip
    for i in range(1, COINBASE_MATURITY + 2):
        # Use unique address per block so each coinbase has a unique txid
        # (prevents txid collision from overwriting coinbase_heights entry)
        dummy_addr = hashlib.sha256(f"block-{i}".encode()).hexdigest()[:40]
        cb = make_coinbase(dummy_addr, INITIAL_SUBSIDY)
        b = mine(chain, i, prev, [cb])
        ok = chain.add_block(b, 0)
        if not ok:
            check(f"Block {i} added", False, f"rejected at height {i}")
            break
        prev = b.compute_hash()
    check(f"Chain at height {COINBASE_MATURITY + 1}",
          chain.height == COINBASE_MATURITY + 1,
          f"actual={chain.height}")

    # 4. Send transaction: Alice → Bob
    print("\n[4] Sending transaction Alice → Bob...")
    send_amount = 10 * COIN
    fee = 1000

    # Get alice's spendable UTXOs (exclude coinbase from block 0 — might not be mature)
    # Use coinbase from block 1 (mined at height 1, current height = COINBASE_MATURITY + 1)
    alice_utxos = chain.get_utxos_for_address(kp_alice.address)
    check("Alice has UTXOs", len(alice_utxos) > 0, f"count={len(alice_utxos)}")

    # Find a mature coinbase UTXO
    mature_utxos = [
        u for u in alice_utxos
        if chain.utxo.coinbase_heights.get(u["txid"], 0) <= chain.height - COINBASE_MATURITY
    ]
    check("Alice has mature UTXOs", len(mature_utxos) > 0, f"count={len(mature_utxos)}")

    if mature_utxos:
        utxos_for_tx = [(u["txid"], u["index"], u["value"], u["address"])
                        for u in mature_utxos[:1]]
        signed_tx = create_signed_tx(
            kp_alice.private_key_hex,
            utxos_for_tx,
            kp_bob.address,
            send_amount,
            kp_alice.address,
            fee=fee,
            chain_id=3,   # regtest chain_id
        )
        check("Transaction created and signed", len(signed_tx.txid) == 64)

        # Validate against chain UTXO (with coinbase maturity)
        valid = validate_transaction(
            signed_tx, chain.utxo,
            chain_id=3,
            current_height=chain.height,
            coinbase_maturity=COINBASE_MATURITY,
        )
        check("Transaction validates against chain UTXO", valid)

        # 5. Mine the transaction
        print("\n[5] Mining transaction into block...")
        cb_mine = make_coinbase(kp_alice.address, INITIAL_SUBSIDY + fee)
        b_tx = mine(
            chain, chain.height + 1, chain.tip,
            [cb_mine, signed_tx.to_dict()],
            difficulty=0,
        )
        ok = chain.add_block(b_tx, 0)
        check("Block with transaction accepted", ok)
        check("Bob received funds",
              chain.get_balance(kp_bob.address) == send_amount,
              f"bob={to_arc(chain.get_balance(kp_bob.address))} ARC")
        check("Alice's UTXO spent",
              not chain.utxo.has(signed_tx.inputs[0].txid, signed_tx.inputs[0].index))

    # 6. Test persistence — restart node
    print("\n[6] Testing persistence after restart...")
    height_before = chain.height
    tip_before = chain.tip
    alice_bal_before = chain.get_balance(kp_alice.address)
    bob_bal_before = chain.get_balance(kp_bob.address)
    del chain

    chain2 = Blockchain(data_dir, no_retarget=True, network="regtest")
    check("Height persists after restart",
          chain2.height == height_before, f"{chain2.height}=={height_before}")
    check("Tip persists after restart", chain2.tip == tip_before)
    check("Alice balance persists",
          chain2.get_balance(kp_alice.address) == alice_bal_before)
    check("Bob balance persists",
          chain2.get_balance(kp_bob.address) == bob_bal_before)

    # 7. Test wallet load/save
    print("\n[7] Testing wallet persistence...")
    kp_alice2 = load_wallet(os.path.join(wallet_dir, "alice.json"))
    check("Wallet reloads correctly", kp_alice2.private_key_hex == kp_alice.private_key_hex)

    # 8. Test network separation — regtest tx not valid on mainnet chain
    print("\n[8] Testing network/chain separation...")
    data_dir_main = os.path.join(tmpdir, "chain_mainnet")
    chain_main = Blockchain(data_dir_main, no_retarget=True, network="mainnet")
    cb_main = make_coinbase(kp_alice.address, INITIAL_SUBSIDY)
    chain_main.add_genesis(cb_main)

    if mature_utxos:
        # The regtest-signed tx should fail on mainnet (different chain_id)
        valid_on_mainnet = validate_transaction(
            signed_tx, chain_main.utxo,
            chain_id=1,   # mainnet
            current_height=0,
            coinbase_maturity=0,
        )
        check("Regtest tx INVALID on mainnet (replay protection)",
              not valid_on_mainnet)

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

print()
print("=" * 55)
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
print(f"Total : {total}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
if failed:
    print("\nFailed tests:")
    for name, ok in results:
        if not ok:
            print(f"  {FAIL} {name}")
print("=" * 55)
sys.exit(0 if failed == 0 else 1)
