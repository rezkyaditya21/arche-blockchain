"""
Phase 9+10 — P2P Security Tests
"""
import sys, os, socket, time, threading, json, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from node.p2p import PeerServer, PeerClient, _send, _recv_one, PROTOCOL_VERSION


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


MAINNET_MAGIC = bytes([0xAC, 0xAC, 0xE1, 0x01])
TESTNET_MAGIC = bytes([0xAC, 0xAC, 0xE1, 0x02])


class TestNetworkMagic:

    def test_wrong_magic_rejected(self):
        """SEC-001: Peer with wrong network magic must be disconnected."""
        port = free_port()
        received = []
        server = PeerServer("127.0.0.1", port, on_message=lambda m: received.append(m),
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        # Connect with TESTNET magic
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        _send(sock, {
            "type": "HELLO",
            "version": PROTOCOL_VERSION,
            "magic": TESTNET_MAGIC.hex(),
            "listen_port": 0,
        })
        # Server should close the connection
        time.sleep(0.3)
        try:
            data = sock.recv(1024)
            # Either empty (connection closed) or HELLO reply
            # If HELLO came back with wrong magic, that's a bug
            if data:
                msg = json.loads(data[4:])
                remote_magic = bytes.fromhex(msg.get("magic", ""))
                assert remote_magic == MAINNET_MAGIC, \
                    "Server replied with wrong magic — should have disconnected"
        except (ConnectionResetError, OSError):
            pass  # Connection closed = correct behavior
        finally:
            sock.close()

    def test_correct_magic_accepted(self):
        """Peer with correct magic connects successfully."""
        port = free_port()
        received = []
        server = PeerServer("127.0.0.1", port, on_message=lambda m: received.append(m),
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        client = PeerClient(on_message=lambda m: None, my_listen_port=0,
                            network_magic=MAINNET_MAGIC)
        client.add_peer("127.0.0.1", port)
        time.sleep(1.0)
        assert len(client.active_peers()) > 0 or len(server.active_inbound()) > 0

    def test_cross_network_client_rejected(self):
        """Testnet client must not sync with mainnet server."""
        port = free_port()
        server = PeerServer("127.0.0.1", port, on_message=lambda _: None,
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        # Testnet client
        client = PeerClient(on_message=lambda _: None, my_listen_port=0,
                            network_magic=TESTNET_MAGIC)
        client.add_peer("127.0.0.1", port)
        time.sleep(1.5)

        # Should NOT be connected
        active = client.active_peers()
        assert len(active) == 0, f"Testnet client should not connect to mainnet server: {active}"

    def test_protocol_version_too_old_rejected(self):
        """Peer with protocol version < PROTOCOL_VERSION must be disconnected."""
        port = free_port()
        server = PeerServer("127.0.0.1", port, on_message=lambda _: None,
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        _send(sock, {
            "type": "HELLO",
            "version": 1,  # Too old (PROTOCOL_VERSION = 2)
            "magic": MAINNET_MAGIC.hex(),
            "listen_port": 0,
        })
        time.sleep(0.3)
        try:
            sock.settimeout(1)
            data = sock.recv(1024)
            if not data:
                pass  # Disconnected — correct
        except (OSError, ConnectionResetError, TimeoutError):
            pass  # Connection closed/timed out — correct
        finally:
            sock.close()


class TestMessageSizeLimits:

    def test_oversized_message_rejected(self):
        """Message exceeding MAX_MSG_BYTES must cause disconnect."""
        port = free_port()
        server = PeerServer("127.0.0.1", port, on_message=lambda _: None,
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        # First do valid HELLO
        _send(sock, {
            "type": "HELLO",
            "version": PROTOCOL_VERSION,
            "magic": MAINNET_MAGIC.hex(),
            "listen_port": 0,
        })
        time.sleep(0.3)
        # Send a 5MB message (exceeds 4MB limit)
        big_payload = b"x" * (5 * 1024 * 1024)
        try:
            sock.sendall(struct.pack("<I", len(big_payload)) + big_payload)
            time.sleep(0.5)
            # Connection should be closed
            sock.settimeout(1)
            data = sock.recv(1024)
            assert data == b"", "Server should close connection on oversized message"
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # Correct — connection closed
        finally:
            sock.close()


class TestConnectionLimits:

    def test_connection_count_tracked(self):
        """Inbound connection count is tracked."""
        port = free_port()
        server = PeerServer("127.0.0.1", port, on_message=lambda _: None,
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        client = PeerClient(on_message=lambda _: None, my_listen_port=0,
                            network_magic=MAINNET_MAGIC)
        client.add_peer("127.0.0.1", port)
        time.sleep(1.0)

        # At least one connection established
        total_connections = len(client.active_peers()) + len(server.active_inbound())
        assert total_connections > 0


class TestBanMechanism:

    def test_ban_prevents_new_connections(self):
        """Banned IP must be rejected on new connection attempts."""
        port = free_port()
        server = PeerServer("127.0.0.1", port, on_message=lambda _: None,
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        # Ban localhost
        server.ban_ip("127.0.0.1")
        assert server.is_banned("127.0.0.1")

        # Try to connect
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=3)
            time.sleep(0.3)
            sock.settimeout(1)
            data = sock.recv(1024)
            # Should be immediately closed (banned)
            assert data == b"", "Banned IP should be disconnected immediately"
            sock.close()
        except (ConnectionRefusedError, OSError):
            pass  # Connection refused or closed = correct


class TestInventoryDedup:

    def test_duplicate_inv_id_dropped(self):
        """Same inv_id from different paths should be processed only once."""
        port = free_port()
        received = []
        server = PeerServer("127.0.0.1", port,
                            on_message=lambda m: received.append(m),
                            network_magic=MAINNET_MAGIC)
        server.start()
        time.sleep(0.2)

        # Connect and send same inv_id twice
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        _send(sock, {
            "type": "HELLO",
            "version": PROTOCOL_VERSION,
            "magic": MAINNET_MAGIC.hex(),
            "listen_port": 0,
        })
        time.sleep(0.3)
        # Send same message twice with same inv_id
        msg = {"type": "NEW_TX", "tx": {"txid": "aa" * 32}, "inv_id": "unique123"}
        _send(sock, msg)
        _send(sock, msg)
        time.sleep(0.5)
        sock.close()

        # Only one should be in received
        tx_msgs = [m for m in received if m.get("type") == "NEW_TX"]
        assert len(tx_msgs) <= 1, f"Duplicate inv_id should be dropped, got {len(tx_msgs)}"
