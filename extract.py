"""Langkah 1 (Extract): download dataset dari Kaggle menjadi file CSV di data/olist/.

Tidak ada konversi format. File CSV dibiarkan apa adanya, lalu dibaca langsung oleh etl.py dan elt.py.
Alternatif tanpa Kaggle API: download zip dari halaman dataset di kaggle.com, extract, dan taruh
file .csv di folder data/olist/, lalu jalankan `python extract.py --check`.
"""
import argparse
from common import download, missing_files, DATA_DIR

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="hanya cek file CSV di data/olist/, tanpa download")
    args = ap.parse_args()

    if args.check:
        if missing := missing_files():
            raise SystemExit(f"File ini tidak ditemukan di {DATA_DIR}: {', '.join(missing)}")
        print("[extract] semua file CSV yang dibutuhkan sudah ada")
    else:
        download()
