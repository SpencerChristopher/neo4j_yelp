import csv
import random
from pathlib import Path
import pandas as pd

"""
Generate tests/data/test.tiny_user_friendship.csv with a 1,000-row mix:
- 50% matched (both users exist)
- 20% reversed duplicates (b-a of a-b)
- 30% unresolved (synthetic IDs)
"""

def main():
    random.seed(42)

    root = Path(__file__).resolve().parent.parent
    user_csv = root / "tests" / "data" / "test.user_small.csv"
    out_csv = root / "tests" / "data" / "test.tiny_user_friendship.csv"

    user_df = pd.read_csv(user_csv)
    user_ids = user_df["user_id"].dropna().astype(str).unique().tolist()
    if len(user_ids) < 2:
        raise SystemExit("Not enough user_ids to generate friendships")

    rows = []

    # 50% matched = 500 rows
    matched_count = 500
    pairs = set()
    while len(pairs) < matched_count:
        u1, u2 = random.sample(user_ids, 2)
        pairs.add((u1, u2))
    matched_rows = list(pairs)
    rows.extend(matched_rows)

    # 20% duplicated = 200 rows (reverse pairs)
    duplicate_count = 200
    reverse_rows = [(b, a) for (a, b) in matched_rows[:duplicate_count]]
    rows.extend(reverse_rows)

    # 30% unresolved = 300 rows (synthetic IDs)
    unresolved_count = 300
    for i in range(unresolved_count):
        u1 = f"SYNTH_USER_{i:04d}_A"
        u2 = f"SYNTH_USER_{i:04d}_B"
        rows.append((u1, u2))

    if len(rows) != 1000:
        raise SystemExit(f"Expected 1000 rows, got {len(rows)}")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["user1", "user2"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_csv}")

if __name__ == "__main__":
    main()
