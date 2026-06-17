"""DuckDB クエリランナー。

使い方:
    uv run python main.py collections/output1_loyalty_distribution.sql
    uv run python main.py collections/output1_loyalty_distribution.sql \\
        collections/output2_feature_health_summary.sql
    uv run python main.py collections/output1_loyalty_distribution.sql \\
        --output result.csv
"""

import sys
from pathlib import Path

from kpi import db

_OUTPUT_DIR = Path(__file__).parent / "output" / "csv"


def run_one(sql_file: Path, output_path: Path) -> None:
    sql = sql_file.read_text(encoding="utf-8")
    conn = db.load()
    result = conn.sql(sql).df()
    conn.close()
    print(f"\n=== {sql_file.name} ===")
    print(result.to_string())
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"-> {output_path} に保存しました")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("使い方: python main.py <sql_file> [<sql_file2> ...]", file=sys.stderr)
        sys.exit(1)

    # --output は単一ファイル指定時のみ有効
    if "--output" in args:
        idx = args.index("--output")
        sql_files = [Path(a) for a in args[:idx]]
        output_path = Path(args[idx + 1])
        if len(sql_files) == 1:
            run_one(sql_files[0], output_path)
            return

    sql_files = [Path(a) for a in args if not a.startswith("-")]
    for sql_file in sql_files:
        run_one(sql_file, _OUTPUT_DIR / (sql_file.stem + ".csv"))


if __name__ == "__main__":
    main()
