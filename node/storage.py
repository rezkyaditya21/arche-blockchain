from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Dict, Generator, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# WriteBatch — accumulate ops then flush atomically
# ---------------------------------------------------------------------------

class WriteBatch:
    def __init__(self) -> None:
        self._ops: List[Tuple[str, bytes, Optional[bytes]]] = []

    def put(self, key: bytes, value: bytes) -> None:
        self._ops.append(("put", key, value))

    def delete(self, key: bytes) -> None:
        self._ops.append(("del", key, None))

    def __len__(self) -> int:
        return len(self._ops)


# ---------------------------------------------------------------------------
# Abstract store
# ---------------------------------------------------------------------------

class KeyValueStore(ABC):
    @abstractmethod
    def get(self, key: bytes) -> Optional[bytes]: ...

    @abstractmethod
    def put(self, key: bytes, value: bytes) -> None: ...

    @abstractmethod
    def delete(self, key: bytes) -> None: ...

    @abstractmethod
    def write_batch(self, batch: WriteBatch) -> None:
        """Apply all ops atomically."""
        ...

    @abstractmethod
    def iter_prefix(self, prefix: bytes) -> Iterable[Tuple[bytes, bytes]]:
        """Yield (key, value) pairs where key starts with prefix."""
        ...

    @contextmanager
    def atomic(self) -> Generator[WriteBatch, None, None]:
        """Convenience context manager — yields WriteBatch, commits on exit."""
        batch = WriteBatch()
        yield batch
        self.write_batch(batch)


# ---------------------------------------------------------------------------
# LevelDB backend (production)
# ---------------------------------------------------------------------------

class LevelDBStore(KeyValueStore):
    def __init__(self, path: str) -> None:
        import plyvel  # type: ignore
        os.makedirs(path, exist_ok=True)
        self.db = plyvel.DB(path, create_if_missing=True)

    def get(self, key: bytes) -> Optional[bytes]:
        return self.db.get(key)

    def put(self, key: bytes, value: bytes) -> None:
        self.db.put(key, value, sync=True)

    def delete(self, key: bytes) -> None:
        self.db.delete(key, sync=True)

    def write_batch(self, batch: WriteBatch) -> None:
        wb = self.db.write_batch(sync=True)
        for op, key, value in batch._ops:
            if op == "put":
                wb.put(key, value)   # type: ignore[arg-type]
            else:
                wb.delete(key)
        wb.write()

    def iter_prefix(self, prefix: bytes) -> Iterable[Tuple[bytes, bytes]]:
        with self.db.iterator(prefix=prefix) as it:
            for k, v in it:
                yield k, v


# ---------------------------------------------------------------------------
# JSON fallback backend (development / no LevelDB)
# ---------------------------------------------------------------------------

class JSONStore(KeyValueStore):
    """
    Crash-safe JSON store with Windows-compatible atomic writes.

    Write strategy:
    - Write new content to a temp file in the same directory
    - On Windows, delete the target before rename (Windows can't replace
      an open file, so we close it first then replace)
    - Falls back to direct overwrite if rename still fails
    """

    def __init__(self, path: str, readonly: bool = False) -> None:
        self.path = path
        self.readonly = readonly
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.exists(path):
            if not readonly:
                self._flush({})
        self._cache: Dict[str, str] = self._load() if os.path.exists(path) else {}

    def _load(self) -> Dict[str, str]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _flush(self, data: Dict[str, str]) -> None:
        """Windows-safe atomic write: write temp → close → replace target."""
        if self.readonly:
            return
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            # Windows: remove target first if it exists, then rename
            try:
                os.replace(tmp, self.path)
            except PermissionError:
                # Last resort: direct overwrite (not atomic but avoids crash)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, key: bytes) -> Optional[bytes]:
        v = self._cache.get(key.hex())
        return bytes.fromhex(v) if v is not None else None

    def put(self, key: bytes, value: bytes) -> None:
        self._cache[key.hex()] = value.hex()
        self._flush(self._cache)

    def delete(self, key: bytes) -> None:
        self._cache.pop(key.hex(), None)
        self._flush(self._cache)

    def write_batch(self, batch: WriteBatch) -> None:
        for op, key, value in batch._ops:
            if op == "put":
                self._cache[key.hex()] = value.hex()  # type: ignore[arg-type]
            else:
                self._cache.pop(key.hex(), None)
        self._flush(self._cache)

    def iter_prefix(self, prefix: bytes) -> Iterable[Tuple[bytes, bytes]]:
        for k_hex, v_hex in list(self._cache.items()):
            if bytes.fromhex(k_hex).startswith(prefix):
                yield bytes.fromhex(k_hex), bytes.fromhex(v_hex)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def open_kv_store(data_dir: str, readonly: bool = False) -> KeyValueStore:
    os.makedirs(data_dir, exist_ok=True)
    try:
        return LevelDBStore(os.path.join(data_dir, "leveldb"))
    except Exception:
        return JSONStore(os.path.join(data_dir, "store.json"), readonly=readonly)
