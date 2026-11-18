"""ELT: LOAD CSV mentah ke ClickHouse dan/atau MySQL (database raw)
-> TRANSFORM pakai SQL di dalam database itu sendiri (database elt)."""
import argparse

from common import SQL_DIR, DB_RAW, DB_ELT, RAW_TABLES, OUTPUT_TABLES, read_csv
from targets import TARGETS, fill


def main(targets: list[str]) -> None:
    params = {"RAW_DB": DB_RAW, "ELT_DB": DB_ELT}
    for name in targets:
        t = TARGETS[name]()
        t.create_db(DB_RAW)
        t.create_db(DB_ELT)

        # E + L: isi CSV masuk apa adanya, tanpa transformasi bisnis
        for table in RAW_TABLES:
            n = t.write_raw(DB_RAW, table, read_csv(table))
            print(f"[elt:load:{name}] {DB_RAW}.{table}: {n:,} baris")

        # T: SQL khusus tiap database (dialek ClickHouse dan MySQL berbeda)
        sql = (SQL_DIR / f"elt_{name}.sql").read_text()
        t.run_sql(fill(sql, params))
        for table in OUTPUT_TABLES:
            print(f"[elt:transform:{name}] {DB_ELT}.{table}: {t.count(DB_ELT, table):,} baris")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", default=list(TARGETS), choices=list(TARGETS))
    main(ap.parse_args().targets)
