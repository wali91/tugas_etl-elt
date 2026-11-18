"""Konfigurasi bersama + tahap Extract (dipakai ETL dan ELT)."""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DATASET = os.getenv("KAGGLE_DATASET", "olistbr/brazilian-ecommerce")
DATA_DIR = ROOT /"data"/"olist"   # CSV hasil download Kaggle
SQL_DIR = ROOT / "sql"

# Nama database tujuan (di ClickHouse maupun MySQL)
DB_RAW = os.getenv("DB_RAW", "raw")   # ELT: data mentah
DB_ELT = os.getenv("DB_ELT", "elt")   # ELT: hasil transform SQL
DB_ETL = os.getenv("DB_ETL", "etl")   # ETL: hasil transform Python

CLICKHOUSE = dict(
    host=os.getenv("CLICKHOUSE_HOST", "localhost"),
    port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
    username=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse"),
)
MYSQL = dict(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", "mysql"),
)

# Hanya file CSV ini yang dipakai (dataset Olist punya file lain, mis. geolocation 1 juta baris)
RAW_TABLES = [
    "olist_orders_dataset",
    "olist_order_items_dataset",
    "olist_order_payments_dataset",
    "olist_customers_dataset",
    "olist_products_dataset",
    "product_category_name_translation",
]
# Kolom tanggal-waktu yang dibaca sebagai datetime (kolom lain dibaca otomatis oleh pandas)
DATE_COLS = {
    "olist_orders_dataset": [
        "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ],
    "olist_order_items_dataset": ["shipping_limit_date"],
}
OUTPUT_TABLES = ["fct_orders", "daily_sales", "category_sales"]
MONEY_COLS = {"items_amount", "freight_amount", "payment_amount", "revenue", "freight"}


def missing_files() -> list[str]:
    return [f"{t}.csv" for t in RAW_TABLES if not (DATA_DIR / f"{t}.csv").exists()]


def download() -> None:
    """EXTRACT: download dataset dari Kaggle (zip otomatis di-unzip menjadi file CSV).
    Butuh ~/.kaggle/kaggle.json atau env KAGGLE_USERNAME + KAGGLE_KEY."""
    from kaggle.api.kaggle_api_extended import KaggleApi


    api = KaggleApi()
    api.authenticate()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(DATASET, path=str(DATA_DIR), unzip=True)
    for f in sorted(DATA_DIR.glob("*.csv")):
        print(f"[extract] {f.name} ({f.stat().st_size / 1e6:.1f} MB)")
    if missing := missing_files():
        raise SystemExit(f"File ini tidak ditemukan di {DATA_DIR}: {', '.join(missing)}")


def read_csv(table: str) -> pd.DataFrame:
    """Baca satu file CSV menjadi DataFrame (kolom waktu otomatis jadi datetime)."""
    path = DATA_DIR / f"{table}.csv"
    if not path.exists():
        raise SystemExit(f"{path} tidak ada. Jalankan dulu: python extract.py")
    return pd.read_csv(path, parse_dates=DATE_COLS.get(table, []))
