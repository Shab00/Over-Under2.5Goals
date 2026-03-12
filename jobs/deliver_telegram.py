from __future__ import annotations

import os
import subprocess
import sys

def main() -> int:
    cmd = [sys.executable, "scripts/send_telegram_digest.py"]

    print("[deliver] running:", " ".join(cmd))
    return subprocess.call(cmd, env=os.environ.copy())

if __name__ == "__main__":
    raise SystemExit(main())
