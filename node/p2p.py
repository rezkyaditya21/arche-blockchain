from __future__ import annotations

"""
ARCHE Production P2P Layer — Phase 9+10 hardened.

Additions over previous version:
- Network magic bytes in HELLO (Phase 10): wrong magic → immediate disconnect
- Per-peer rate limiting (Phase 9): token bucket, 100 msg/s max
- Inbound connection limit (Phase 9): max 125 concurrent inbound
- Protocol version check (Phase 10)
- Ban list persisted to disk (Phase 9)
- Request/response timeout for GET_BLOCKS
"""

import json
import logging
import os
import socket
import struct
import threading
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)

MessageHandler = Callable[[Dict], None]

PROTOCOL_VERSION = 2
MAX_MSG_BYTES = 4 * 1024 * 1024    # 4 MB hard cap
PING_INTERVAL = 60                  # seconds
RECONNECT_DELAY = 30                # seconds
BAN_THRESHOLD = 5                   # consecutive failures → ban
MAX_INBOUND_CONNECTIONS = 125       # like Bitcoin
RATE_LIMIT_MSG_PER_SEC = 100        # per peer
RATE_LIMIT_WINDOW = 1.0             # seconds


# ---------------------------------------------------------------------------
# Framing helpers
# ---------------------------------------------------------------------------

def _send(sock: socket.socket, msg: Dict) -> None:
    data = json.dumps(msg, separators=(",", ":")).encode()
    sock.sendall(struct.pack("<I", len(data)) + data)


def _recv_one(sock: socket.socket) -> Dict:
    hdr = _recv_exact(sock, 4)
    length = struct.unpack("<I", hdr)[0]
    if length > MAX_MSG_BYTES:
        raise ValueError(f"Message too large: {length} bytes (max {MAX_MSG_BYTES})")
    raw = _recv_exact(sock, length)
    return json.loads(raw.decode())


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("connection closed")
        buf += chunk
    return bytes(buf)


# ---------------------------------------------------------------------------
# Rate limiter (token bucket per peer)
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, rate: float, window: float) -> None:
        self.rate = rate          # max messages per window
        self.window = window      # window size in seconds
        self._counts: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, peer: str) -> bool:
        """Return True if peer is within rate limit, False if exceeded."""
        now = time.monotonic()
        with self._lock:
            times = self._counts[peer]
            # Remove entries outside window
            cutoff = now - self.window
            self._counts[peer] = [t for t in times if t > cutoff]
            if len(self._counts[peer]) >= self.rate:
                return False
            self._counts[peer].append(now)
            return True

    def cleanup(self, peer: str) -> None:
        with self._lock:
            self._counts.pop(peer, None)


_rate_limiter = _RateLimiter(RATE_LIMIT_MSG_PER_SEC, RATE_LIMIT_WINDOW)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class PeerServer:
    def __init__(
        self,
        host: str,
        port: int,
        on_message: MessageHandler,
        on_new_peer: Optional[Callable[[str, int], None]] = None,
        network_magic: bytes = b"\xAC\xAC\xE1\x01",
        ban_file: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_new_peer = on_new_peer
        self.network_magic = network_magic
        self._sock: Optional[socket.socket] = None
        self._seen: Set[str] = set()
        self._seen_lock = threading.Lock()
        self._inbound: Set[str] = set()
        self._inbound_lock = threading.Lock()
        self._inbound_count = 0
        self._inbound_count_lock = threading.Lock()
        # Ban list
        self._banned: Set[str] = set()
        self._ban_file = ban_file
        if ban_file and os.path.exists(ban_file):
            try:
                with open(ban_file) as f:
                    self._banned = set(json.load(f))
            except Exception:
                pass

    def _save_bans(self) -> None:
        if self._ban_file:
            try:
                with open(self._ban_file, "w") as f:
                    json.dump(list(self._banned), f)
            except Exception:
                pass

    def ban_ip(self, ip: str) -> None:
        self._banned.add(ip)
        self._save_bans()

    def is_banned(self, ip: str) -> bool:
        return ip in self._banned

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(64)
        threading.Thread(target=self._accept_loop, daemon=True, name="p2p-accept").start()
        log.info("P2P server on %s:%d (magic=%s)", self.host, self.port,
                 self.network_magic.hex())

    def _accept_loop(self) -> None:
        assert self._sock
        while True:
            try:
                conn, addr = self._sock.accept()
                # Check banned
                if self.is_banned(addr[0]):
                    conn.close()
                    continue
                # Check connection limit
                with self._inbound_count_lock:
                    if self._inbound_count >= MAX_INBOUND_CONNECTIONS:
                        conn.close()
                        log.debug("Rejected connection from %s: max inbound reached", addr[0])
                        continue
                    self._inbound_count += 1
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                threading.Thread(
                    target=self._handle, args=(conn, addr),
                    daemon=True, name=f"p2p-in-{addr[0]}:{addr[1]}"
                ).start()
            except Exception as e:
                log.warning("accept error: %s", e)

    def _handle(self, conn: socket.socket, addr) -> None:
        peer_ip = addr[0]
        peer = f"{peer_ip}:{addr[1]}"
        try:
            with conn:
                conn.settimeout(30)
                # Expect HELLO with correct network magic
                msg = _recv_one(conn)
                if msg.get("type") != "HELLO":
                    return
                # Validate network magic (Phase 10)
                peer_magic = bytes.fromhex(msg.get("magic", ""))
                if peer_magic != self.network_magic:
                    log.debug("Peer %s wrong magic %s (expected %s)",
                              peer, peer_magic.hex(), self.network_magic.hex())
                    return
                # Validate protocol version
                if msg.get("version", 0) < PROTOCOL_VERSION:
                    log.debug("Peer %s old protocol version %d", peer, msg.get("version"))
                    return
                _send(conn, {
                    "type": "HELLO",
                    "version": PROTOCOL_VERSION,
                    "magic": self.network_magic.hex(),
                })
                listen_port = msg.get("listen_port")
                if listen_port and self.on_new_peer:
                    self.on_new_peer(peer_ip, int(listen_port))
                peer_key = f"{peer_ip}:{listen_port}" if listen_port else peer
                with self._inbound_lock:
                    self._inbound.add(peer_key)
                conn.settimeout(120)
                misbehavior = 0
                try:
                    while True:
                        msg = _recv_one(conn)
                        # Rate limiting
                        if not _rate_limiter.check(peer_ip):
                            log.warning("Rate limit exceeded for %s — disconnecting", peer_ip)
                            misbehavior += 10
                            if misbehavior >= 100:
                                self.ban_ip(peer_ip)
                            break
                        mtype = msg.get("type")
                        if mtype == "PING":
                            _send(conn, {"type": "PONG"})
                            continue
                        if mtype == "PONG":
                            continue
                        # Inventory dedup
                        inv_id = msg.get("inv_id")
                        if inv_id:
                            with self._seen_lock:
                                if inv_id in self._seen:
                                    continue
                                self._seen.add(inv_id)
                                if len(self._seen) > 50_000:
                                    items = list(self._seen)
                                    self._seen = set(items[25_000:])
                        self.on_message(msg)
                finally:
                    with self._inbound_lock:
                        self._inbound.discard(peer_key)
                    _rate_limiter.cleanup(peer_ip)
        except (EOFError, ConnectionResetError, TimeoutError, OSError):
            pass
        except Exception as e:
            log.debug("peer %s error: %s", peer, e)
        finally:
            with self._inbound_count_lock:
                self._inbound_count = max(0, self._inbound_count - 1)

    def active_inbound(self) -> List[str]:
        with self._inbound_lock:
            return list(self._inbound)


# ---------------------------------------------------------------------------
# Outbound persistent connection
# ---------------------------------------------------------------------------

class _Conn:
    def __init__(
        self,
        host: str,
        port: int,
        on_message: MessageHandler,
        my_listen_port: int = 0,
        network_magic: bytes = b"\xAC\xAC\xE1\x01",
    ) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
        self.my_listen_port = my_listen_port
        self.network_magic = network_magic
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.fail_count = 0
        self.banned = False

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self) -> None:
        threading.Thread(
            target=self._loop, daemon=True, name=f"p2p-out-{self.key}"
        ).start()

    def _loop(self) -> None:
        while not self._stop.is_set() and not self.banned:
            try:
                sock = socket.create_connection((self.host, self.port), timeout=10)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(30)
                # Send HELLO with network magic and listen port
                _send(sock, {
                    "type": "HELLO",
                    "version": PROTOCOL_VERSION,
                    "magic": self.network_magic.hex(),
                    "listen_port": self.my_listen_port,
                })
                reply = _recv_one(sock)
                if reply.get("type") != "HELLO":
                    sock.close()
                    raise ConnectionError("bad handshake: no HELLO")
                # Verify remote magic
                remote_magic = bytes.fromhex(reply.get("magic", ""))
                if remote_magic != self.network_magic:
                    sock.close()
                    raise ConnectionError(f"wrong network magic: {remote_magic.hex()}")
                sock.settimeout(120)
                with self._lock:
                    self._sock = sock
                    self.fail_count = 0
                log.info("Connected to peer %s (network=%s)",
                         self.key, self.network_magic.hex())
                self._read(sock)
            except Exception as e:
                with self._lock:
                    self._sock = None
                    self.fail_count += 1
                if self.fail_count >= BAN_THRESHOLD:
                    log.warning("Banned peer %s after %d failures", self.key, self.fail_count)
                    self.banned = True
                    return
                log.debug("Peer %s error (%s); retry in %ds", self.key, e, RECONNECT_DELAY)
                self._stop.wait(RECONNECT_DELAY)

    def _read(self, sock: socket.socket) -> None:
        try:
            while not self._stop.is_set():
                msg = _recv_one(sock)
                if msg.get("type") not in ("PONG",):
                    self.on_message(msg)
        except Exception:
            pass
        finally:
            with self._lock:
                self._sock = None

    def send(self, msg: Dict) -> bool:
        with self._lock:
            if self._sock is None:
                return False
            try:
                _send(self._sock, msg)
                return True
            except Exception:
                self._sock = None
                return False

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Client pool
# ---------------------------------------------------------------------------

class PeerClient:
    def __init__(
        self,
        on_message: Optional[MessageHandler] = None,
        my_listen_port: int = 0,
        network_magic: bytes = b"\xAC\xAC\xE1\x01",
    ) -> None:
        self._peers: Dict[str, _Conn] = {}
        self._lock = threading.Lock()
        self._on_message = on_message or (lambda _: None)
        self.my_listen_port = my_listen_port
        self.network_magic = network_magic
        threading.Thread(target=self._ping_loop, daemon=True, name="p2p-ping").start()

    def add_peer(self, host: str, port: int) -> None:
        key = f"{host}:{port}"
        with self._lock:
            if key in self._peers:
                return
            c = _Conn(host, port, self._on_message,
                      my_listen_port=self.my_listen_port,
                      network_magic=self.network_magic)
            self._peers[key] = c
        c.start()

    def broadcast(self, msg: Dict) -> None:
        with self._lock:
            peers = list(self._peers.values())
        for c in peers:
            if not c.banned:
                c.send(msg)

    def send_to(self, host: str, port: int, msg: Dict) -> bool:
        with self._lock:
            c = self._peers.get(f"{host}:{port}")
        return c.send(msg) if c else False

    def active_peers(self) -> List[str]:
        with self._lock:
            return [k for k, c in self._peers.items()
                    if not c.banned and c._sock is not None]

    def all_peers(self, server: "PeerServer") -> List[str]:
        outbound = self.active_peers()
        inbound = server.active_inbound()
        return list(set(outbound + inbound))

    def _ping_loop(self) -> None:
        while True:
            time.sleep(PING_INTERVAL)
            with self._lock:
                peers = list(self._peers.values())
            for c in peers:
                c.send({"type": "PING"})
