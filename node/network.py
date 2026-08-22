"""
ARCHE Network Configuration — Phase 13
Defines mainnet, testnet, and regtest network parameters.
Each network has its own magic bytes, ports, chain_id, and genesis parameters.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkParams:
    name: str
    chain_id: int           # used in transaction signing domain
    magic: bytes            # 4-byte network magic for P2P handshake
    p2p_port: int
    http_port: int
    address_version: int    # Base58Check version byte
    data_dir_suffix: str    # appended to ~/.arche/ for storage isolation


MAINNET = NetworkParams(
    name="mainnet",
    chain_id=1,
    magic=bytes([0xAC, 0xAC, 0xE1, 0x01]),
    p2p_port=9333,
    http_port=9334,
    address_version=0x17,
    data_dir_suffix="mainnet",
)

TESTNET = NetworkParams(
    name="testnet",
    chain_id=2,
    magic=bytes([0xAC, 0xAC, 0xE1, 0x02]),
    p2p_port=19333,
    http_port=19334,
    address_version=0x6F,
    data_dir_suffix="testnet",
)

REGTEST = NetworkParams(
    name="regtest",
    chain_id=3,
    magic=bytes([0xAC, 0xAC, 0xE1, 0x03]),
    p2p_port=29333,
    http_port=29334,
    address_version=0x6F,
    data_dir_suffix="regtest",
)

NETWORKS = {
    "mainnet": MAINNET,
    "testnet": TESTNET,
    "regtest": REGTEST,
}

# Default active network
_active: NetworkParams = MAINNET


def set_network(name: str) -> None:
    global _active
    if name not in NETWORKS:
        raise ValueError(f"Unknown network: {name}. Choose from {list(NETWORKS)}")
    _active = NETWORKS[name]


def get_network() -> NetworkParams:
    return _active
