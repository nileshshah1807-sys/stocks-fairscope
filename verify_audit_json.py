"""Verify a FairScope exported model-audit JSON file."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def verify_file(path: str) -> tuple[bool, str, str]:
    record=json.loads(Path(path).read_text(encoding="utf-8"));stored=str(record.pop("audit_hash","")).lower();canonical=json.dumps(record,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str);calculated=hashlib.sha256(canonical.encode("utf-8")).hexdigest();return bool(stored) and stored==calculated,stored,calculated


def main() -> int:
    parser=argparse.ArgumentParser(description="Verify a DR. NILESH SHAH - STOCKS FAIRSCOPE audit JSON SHA-256 hash.")
    parser.add_argument("audit_json",help="Path to an exported audit JSON file")
    args=parser.parse_args();valid,stored,calculated=verify_file(args.audit_json)
    print(f"Stored:     {stored or 'missing'}")
    print(f"Calculated: {calculated}")
    print("Result:     VALID" if valid else "Result:     FAILED")
    print("Note: SHA-256 provides tamper-evidence; it is not a digital signature.")
    return 0 if valid else 1


if __name__=="__main__":raise SystemExit(main())
