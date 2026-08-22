from wallet.wallet import KeyPair, pubkey_to_address
import hashlib


def test_keypair_generate_and_address():
    kp = KeyPair.generate()
    assert len(kp.private_key_hex) == 64
    assert len(kp.public_key_hex) in (66,)
    addr_bytes = bytes.fromhex(kp.public_key_hex)
    addr = pubkey_to_address(addr_bytes)
    assert addr == kp.address


def test_sign_and_verify():
    kp = KeyPair.generate()
    message = b"hello"
    sig = kp.sign(message)
    assert kp.verify(message, sig)
    # wrong message should fail
    assert not kp.verify(b"world", sig)





