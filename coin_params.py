"""
ARCHE (ARC) — Coin Parameters
==============================
Single source of truth for all network constants.
Import this module everywhere instead of hardcoding values.
"""

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
COIN_NAME        = "ARCHE"
COIN_TICKER      = "ARC"
COIN_VERSION     = "1.0.0"

# ---------------------------------------------------------------------------
# Denomination
# ---------------------------------------------------------------------------
# 1 ARC = 100_000_000 base units (same as Bitcoin's satoshi)
COIN             = 100_000_000          # base units per 1 ARC
COIN_DECIMALS    = 8

def to_arc(base_units: int) -> float:
    """Convert base units to ARC (display)."""
    return base_units / COIN

def to_base(arc: float) -> int:
    """Convert ARC amount to base units."""
    return int(arc * COIN)

# ---------------------------------------------------------------------------
# Block & mining parameters
# ---------------------------------------------------------------------------
TARGET_BLOCK_TIME   = 120               # seconds (2 minutes)
RETARGET_INTERVAL   = 2016              # blocks between difficulty adjustments
                                        # ≈ 2016 × 2min = 2.8 days per retarget

# PoW: min/max timespan clamp for retarget (prevents wild swings)
MIN_RETARGET_TIMESPAN = TARGET_BLOCK_TIME * RETARGET_INTERVAL // 4
MAX_RETARGET_TIMESPAN = TARGET_BLOCK_TIME * RETARGET_INTERVAL * 4

# Max target — absolute easiest (difficulty=0 means any hash passes)
MAX_TARGET          = (1 << 256) - 1

BLOCK_VERSION       = 1

# ---------------------------------------------------------------------------
# Supply & rewards
# ---------------------------------------------------------------------------
# Total max supply: 50,000,000 ARC
# INITIAL_SUBSIDY × HALVING_INTERVAL × 2  =  50 ARC × 500,000 × 2  =  50,000,000 ARC ✓
INITIAL_SUBSIDY     = 50 * COIN         # 50 ARC in base units = 5_000_000_000
HALVING_INTERVAL    = 500_000           # blocks between halvings
MAX_SUPPLY          = 50_000_000 * COIN # 50,000,000 ARC in base units

def block_subsidy(height: int) -> int:
    """
    Bitcoin-style halving every HALVING_INTERVAL blocks.
    Converges to MAX_SUPPLY = 50,000,000 ARC total.
    """
    halvings = height // HALVING_INTERVAL
    if halvings >= 64:
        return 0
    return INITIAL_SUBSIDY >> halvings

# ---------------------------------------------------------------------------
# Network ports (defaults)
# ---------------------------------------------------------------------------
DEFAULT_P2P_PORT    = 9333
DEFAULT_HTTP_PORT   = 9334
DEFAULT_TESTNET_P2P = 19333
DEFAULT_TESTNET_HTTP = 19334

# ---------------------------------------------------------------------------
# Address version bytes (Base58Check)
# ---------------------------------------------------------------------------
# 'A' prefix → version byte 0x17 → Base58 addresses start with 'A'
PUBKEY_ADDRESS_VERSION = 0x17           # produces 'A' prefix in Base58Check

# ---------------------------------------------------------------------------
# Seed nodes — hard-coded bootstrap peers
# Node baru akan otomatis connect ke seed ini saat pertama kali join network
# Format: "host:port"
# ---------------------------------------------------------------------------
SEED_NODES = {
    "mainnet": [
        # Tambahkan IP VPS kamu di sini setelah deploy
        # Contoh: "125.166.0.117:9333",
    ],
    "testnet": [
        # Contoh: "125.166.0.117:19333",
    ],
    "regtest": [],
}
COINBASE_MATURITY   = 100               # blocks before coinbase can be spent
MAX_BLOCK_SIZE      = 1_000_000         # bytes (1 MB)
MAX_TX_SIZE         = 100_000           # bytes (100 KB)
MAX_TX_INPUTS       = 1_000            # max inputs per transaction
MAX_TX_OUTPUTS      = 1_000            # max outputs per transaction
MAX_MEMPOOL_SIZE    = 5_000            # max transactions in mempool
MAX_FUTURE_SECONDS  = 7200              # 2 hours clock drift tolerance
GENESIS_PREV_HASH   = "0" * 64
