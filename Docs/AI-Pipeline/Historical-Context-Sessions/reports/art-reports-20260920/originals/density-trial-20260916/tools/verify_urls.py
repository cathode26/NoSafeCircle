"""Check that the pinned raw GitHub URLs serve the same bytes as the local sources."""
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = Path(r"C:\NSC\NSC\NoSafeCircle")
SHA = "96a6293c47cf2346b5c98f968e8790ce561674d3"
PATHS = [
    "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/masculine-light/selected/standing/south.png",
    "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/enemy_ranged_se_idle_00.png",
]


def main() -> int:
    ok = True
    for path in PATHS:
        url = f"https://raw.githubusercontent.com/cathode26/NoSafeCircle/{SHA}/{path}"
        with urllib.request.urlopen(url, timeout=30) as response:
            remote = response.read()
            status = response.status
        local = (REPO / path).read_bytes()
        remote_hash = hashlib.sha256(remote).hexdigest()
        local_hash = hashlib.sha256(local).hexdigest()
        match = remote_hash == local_hash
        ok &= match
        print(url)
        print(f"  http {status}, {len(remote)} bytes, sha256 {remote_hash}, matches local: {match}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
