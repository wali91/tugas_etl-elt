# ETL dan ELT sederhana: Olist (Kaggle) → ClickHouse dan MySQL

Dataset: [`olistbr/brazilian-ecommerce`](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
Extract hanya mengunduh **CSV** (tanpa konversi Parquet, tanpa DuckDB). CSV dibaca langsung dengan pandas,
lalu dimuat ke **ClickHouse** dan **MySQL** dengan dua cara.

```
Kaggle -> data/olist/*.csv
              |
   ETL -------+------- ELT
   pandas transform di Python        load CSV mentah -> database raw
   -> hasil akhir ke database etl    SQL di dalam database -> database elt
```

Penjelasan lengkap ada di [`PENJELASAN.md`](PENJELASAN.md).

## Cara pakai
```bash
python3 -m venv .venv_etl && source .venv_etl/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env                 # isi KAGGLE_USERNAME dan KAGGLE_KEY
docker compose up -d                 # MySQL (3306) dan ClickHouse (8123)

python extract.py                    # download CSV dari Kaggle ke data/olist/
python etl.py                        # ke ClickHouse dan MySQL
python elt.py                        # ke ClickHouse dan MySQL

python etl.py --targets mysql        # hanya satu tujuan
python elt.py --targets clickhouse
```

Tanpa Kaggle API: download zip dari halaman dataset, extract, taruh file `.csv` di `data/olist/`,
lalu jalankan `python extract.py --check` untuk memastikan file lengkap.

## Cek hasil
```bash
docker compose exec mysql mysql -uroot -pmysql -e \
  "SELECT 'etl', COUNT(*) FROM etl.fct_orders UNION ALL SELECT 'elt', COUNT(*) FROM elt.fct_orders"

docker compose exec clickhouse clickhouse-client --password clickhouse -q \
  "SELECT 'etl', count() FROM etl.fct_orders UNION ALL SELECT 'elt', count() FROM elt.fct_orders"
```

## File
| File | Fungsi |
|---|---|
| `common.py` | konfigurasi, download Kaggle, pembaca CSV |
| `extract.py` | menjalankan tahap extract |
| `targets.py` | penulis data untuk ClickHouse dan MySQL (kelas `ClickHouse`, `MySQL`) |
| `etl.py` | transform pandas lalu load |
| `elt.py` + `sql/elt_*.sql` | load mentah lalu transform SQL |
