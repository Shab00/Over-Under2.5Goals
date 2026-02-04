#!/usr/bin/env python3
from pathlib import Path
p = Path("src/api/main.py")
if not p.exists():
    print("ERROR: src/api/main.py not found. Run from repo root or adjust path.")
    raise SystemExit(1)

bak = p.with_suffix(".py.bak")
bak.write_bytes(p.read_bytes())
text = p.read_text()

# Remove any existing add_prometheus_metrics(...) calls
lines = [ln for ln in text.splitlines()]
lines = [ln for ln in lines if "add_prometheus_metrics(" not in ln]

# Find first assignment line that creates a FastAPI instance
inserted = False
out = []
for i, ln in enumerate(lines):
    out.append(ln)
    if not inserted and "FastAPI(" in ln and "=" in ln:
        lhs = ln.split("=", 1)[0].strip()
        # Insert call on the next line
        out.append(f"add_prometheus_metrics({lhs})")
        inserted = True

if not inserted:
    print("Warning: did not find a line assigning FastAPI(...). No insertion made.")
else:
    p.write_text("\n".join(out))
    print(f"Patched {p} (backup created at {bak}).")
