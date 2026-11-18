"""Penulisan data untuk ClickHouse dan MySQL. Keduanya punya method yang sama:

    create_db(db)                    buat database
    write_frame(db, table, df)       tulis hasil transform (dipakai ETL)
    write_raw(db, table, df)         tulis data CSV mentah apa adanya (dipakai ELT)
    run_sql(sql_text)                jalankan beberapa statement SQL (dipakai ELT)
    count(db, table)                 jumlah baris
"""
import datetime as dt
from decimal import Decimal
from urllib.parse import quote_plus

import pandas as pd

from common import CLICKHOUSE, MYSQL, MONEY_COLS

BATCH = 50_000


def fill(text: str, params: dict[str, str]) -> str:
    for k, v in params.items():
        text = text.replace("${" + k + "}", v)
    return text


def split_sql(text: str) -> list[str]:
    """Pisahkan file SQL menjadi statement (buang baris komentar '--')."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def _is_date_obj(s: pd.Series) -> bool:
    first = s.dropna().iloc[0] if s.notna().any() else None
    return isinstance(first, dt.date) and not isinstance(first, dt.datetime)


# ================================================================== ClickHouse
def _df_to_ch(s: pd.Series, money: bool) -> str:
    if money:
        return "Nullable(Decimal(18, 2))"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "Nullable(DateTime64(6))"
    if pd.api.types.is_bool_dtype(s):
        return "Nullable(Bool)"
    if pd.api.types.is_integer_dtype(s):
        return "Nullable(Int64)"
    if pd.api.types.is_float_dtype(s):
        return "Nullable(Float64)"
    return "Nullable(Date)" if _is_date_obj(s) else "Nullable(String)"


class ClickHouse:
    name = "clickhouse"

    def __init__(self):
        import clickhouse_connect

        self.c = clickhouse_connect.get_client(**CLICKHOUSE)

    def create_db(self, db: str) -> None:
        self.c.command(f"CREATE DATABASE IF NOT EXISTS `{db}`")

    def _create(self, db: str, table: str, cols: list[tuple[str, str]]) -> None:
        ddl = ", ".join(f"`{n}` {t}" for n, t in cols)
        self.c.command(f"DROP TABLE IF EXISTS `{db}`.`{table}`")
        self.c.command(f"CREATE TABLE `{db}`.`{table}` ({ddl}) ENGINE = MergeTree ORDER BY tuple()")

    def write_frame(self, db: str, table: str, df: pd.DataFrame) -> int:
        cols = [(c, _df_to_ch(df[c], c in MONEY_COLS)) for c in df.columns]
        self._create(db, table, cols)
        obj = df.astype(object).where(df.notna(), None)
        for c in MONEY_COLS & set(df.columns):
            obj[c] = obj[c].map(lambda v: None if v is None else Decimal(str(round(float(v), 2))))
        rows = obj.values.tolist()
        for i in range(0, len(rows), BATCH):
            self.c.insert(f"`{db}`.`{table}`", rows[i:i + BATCH], column_names=list(df.columns))
        return len(rows)

    def write_raw(self, db: str, table: str, df: pd.DataFrame) -> int:
        return self.write_frame(db, table, df)

    def run_sql(self, sql_text: str) -> None:
        for stmt in split_sql(sql_text):
            self.c.command(stmt)

    def count(self, db: str, table: str) -> int:
        return int(self.c.command(f"SELECT count() FROM `{db}`.`{table}`"))


# ================================================================== MySQL
def _sa_types(df: pd.DataFrame) -> dict:
    """Tipe kolom MySQL: VARCHAR(255) untuk teks (bukan TEXT, supaya bisa di-index), DECIMAL untuk uang."""
    from sqlalchemy import types as T

    out = {}
    for c in df.columns:
        s = df[c]
        if c in MONEY_COLS:
            out[c] = T.DECIMAL(18, 2)
        elif pd.api.types.is_datetime64_any_dtype(s):
            out[c] = T.DateTime()
        elif s.dtype == object or pd.api.types.is_string_dtype(s):
            out[c] = T.Date() if _is_date_obj(s) else T.String(255)
    return out


class MySQL:
    name = "mysql"

    def __init__(self):
        from sqlalchemy import create_engine

        c = MYSQL
        self.engine = create_engine(
            f"mysql+pymysql://{c['user']}:{quote_plus(c['password'])}@{c['host']}:{c['port']}/?charset=utf8mb4"
        )

    def create_db(self, db: str) -> None:
        with self.engine.begin() as con:
            con.exec_driver_sql(f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4")

    def write_frame(self, db: str, table: str, df: pd.DataFrame) -> int:
        df = df.copy()
        for c in MONEY_COLS & set(df.columns):
            df[c] = df[c].round(2)
        df.to_sql(table, self.engine, schema=db, if_exists="replace", index=False,
                  dtype=_sa_types(df), chunksize=2000, method="multi")
        return len(df)

    def write_raw(self, db: str, table: str, df: pd.DataFrame) -> int:
        n = self.write_frame(db, table, df)
        # index pada kolom teks *_id supaya JOIN di tahap transform cepat
        from sqlalchemy import types as T

        types = _sa_types(df)
        with self.engine.begin() as con:
            for col in df.columns:
                if col.endswith("_id") and isinstance(types.get(col), T.String):
                    con.exec_driver_sql(f"CREATE INDEX `ix_{col}` ON `{db}`.`{table}` (`{col}`(64))")
        return n

    def run_sql(self, sql_text: str) -> None:
        with self.engine.begin() as con:
            for stmt in split_sql(sql_text):
                con.exec_driver_sql(stmt)

    def count(self, db: str, table: str) -> int:
        with self.engine.begin() as con:
            return int(con.exec_driver_sql(f"SELECT count(*) FROM `{db}`.`{table}`").scalar())


TARGETS = {"clickhouse": ClickHouse, "mysql": MySQL}
