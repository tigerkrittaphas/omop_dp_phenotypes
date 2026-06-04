import numpy as np
import hashlib
from scipy.optimize import minimize_scalar

class LiquidLegions:
    def __init__(self, m: int = 50_000, a: float = 10.0, salt: str = "ll"):
        self.m = m
        self.a = a
        self.salt = salt
        self.bits = np.zeros(m, dtype=np.int8)
        k = np.arange(m)
        norm = 1.0 - np.exp(-a)
        self.p_k = (np.exp(-a * k / m) - np.exp(-a * (k + 1) / m)) / norm
        self._dp_p_flip = 0.0

    def _hash01(self, item) -> float:
        h = hashlib.blake2b(f"{self.salt}:{item}".encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") / (1 << 64)

    def _register(self, item) -> int:
        u = self._hash01(item)
        x = -np.log1p(-u * (1.0 - np.exp(-self.a))) / self.a
        return min(int(x * self.m), self.m - 1)

    def add(self, item) -> None:
        self.bits[self._register(item)] = 1

    def add_many(self, items) -> None:
        for it in items:
            self.add(it)

    @classmethod
    def union(cls, sketches: list["LiquidLegions"]) -> "LiquidLegions":
        ref = sketches[0]
        out = cls(m=ref.m, a=ref.a, salt=ref.salt)
        for s in sketches:
            assert s.m == ref.m and s.a == ref.a and s.salt == ref.salt, "sketch params must match"
            np.maximum(out.bits, s.bits, out=out.bits)
        return out

    def apply_dp(self, epsilon: float, rng: np.random.Generator) -> None:
        p = 1.0 / (1.0 + np.exp(epsilon))
        flips = rng.binomial(1, p, size=self.m).astype(np.int8)
        self.bits = np.bitwise_xor(self.bits, flips)
        self._dp_p_flip = p