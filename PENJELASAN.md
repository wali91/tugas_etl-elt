# Penjelasan pipeline ETL dan ELT Olist

Dokumen ini menjelaskan cara kerja proyek, urutan prosesnya, dan alasan di balik pilihan desainnya.

## 1. Gambaran umum

Proyek ini mengambil data e-commerce Olist dari Kaggle, lalu menghasilkan tiga tabel ringkasan penjualan
di dua database (ClickHouse dan MySQL). Ada dua cara untuk sampai ke hasil yang sama:

- **ETL** (Extract, Transform, Load): data diolah di Python **sebelum** masuk ke database.
- **ELT** (Extract, Load, Transform): data mentah dimasukkan ke database **dulu**, lalu diolah dengan SQL di dalamnya.

```
              Kaggle
                |   extract.py
                v
         data/olist/*.csv
          /               \
   etl.py                  elt.py
   baca CSV (pandas)       baca CSV (pandas)
   transform (pandas)      load apa adanya  -> database raw
   load hasil -> etl       transform SQL    -> database elt
```

## 2. Extract (`extract.py`)

Tahap ini sengaja dibuat sesederhana mungkin:

1. `KaggleApi().authenticate()` membaca kredensial dari `~/.kaggle/kaggle.json` atau variabel
   `KAGGLE_USERNAME` dan `KAGGLE_KEY`.
2. `dataset_download_files(..., unzip=True)` mengunduh zip dataset dan langsung mengekstraknya menjadi
   file `.csv` di `data/olist/`.
3. Skrip memeriksa bahwa 9 file yang dibutuhkan ada, lalu berhenti dengan pesan jelas kalau ada yang hilang.

<!-- Tidak ada konversi format dan tidak ada DuckDB. CSV dibiarkan apa adanya sebagai sumber data. -->

**Konsekuensinya:** karena tidak ada file dengan skema tetap (seperti Parquet), tipe kolom ditebak pandas
saat membaca CSV. Kolom waktu perlu disebutkan eksplisit supaya terbaca sebagai tanggal, dan itu dilakukan
lewat `DATE_COLS` di `common.py`. Pandas membaca satu file CSV utuh ke memori. Ini aman untuk Olist
(file terbesar yang dipakai sekitar 100 ribu baris), tetapi untuk file yang jauh lebih besar sebaiknya
dibaca bertahap dengan `chunksize`.

**Tanpa Kaggle API:** unduh zip dari halaman dataset, ekstrak, taruh file `.csv` di `data/olist/`, lalu
jalankan `python extract.py --check`.

### File yang dipakai
Dataset Olist berisi lebih banyak file, tetapi hanya 6 yang dipakai (`RAW_TABLES` di `common.py`):

| File | Isi |
|---|---|
| `olist_orders_dataset` | pesanan, status, tanggal beli, kirim, dan estimasi |
| `olist_order_items_dataset` | barang per pesanan, harga, ongkos kirim |
| `olist_order_payments_dataset` | pembayaran per pesanan |
| `olist_customers_dataset` | pelanggan, kota, negara bagian |
| `olist_products_dataset` | produk dan nama kategori (bahasa Portugis) |
| `product_category_name_translation` | terjemahan nama kategori ke bahasa Inggris |

File `olist_geolocation_dataset` (sekitar 1 juta baris) dilewati karena tidak dibutuhkan.

## 3. ETL (`etl.py`)

Urutan di dalam `main()`:

1. **Extract:** `read_csv()` membaca 6 file CSV menjadi DataFrame.
2. **Transform** (`transform()`, semuanya di Python dengan pandas):
   - `fct_orders`: gabungkan pesanan dengan total barang dan total pembayaran per pesanan, hitung
     `delivery_days` (selisih hari beli sampai terkirim) dan `is_late` (terkirim setelah estimasi).
   - `daily_sales`: filter pesanan `canceled` dan `unavailable`, gabungkan dengan negara bagian
     pelanggan, lalu agregasi per hari dan per negara bagian.
   - `category_sales`: gabungkan barang, pesanan, produk, dan terjemahan kategori, lalu agregasi per kategori.
3. **Load:** `write_frame()` membuat tabel di database `etl` lalu mengisinya, untuk ClickHouse dan/atau MySQL.

Hanya hasil akhir yang masuk ke database. Data mentah tidak tersimpan di sana.

## 4. ELT (`elt.py`)

Urutan di dalam `main()`, untuk setiap tujuan:

1. **Extract:** `read_csv()` membaca CSV.
2. **Load:** `write_raw()` memasukkan isi CSV apa adanya ke database `raw`. Di MySQL, kolom teks berakhiran
   `_id` otomatis diberi indeks supaya `JOIN` cepat.
3. **Transform:** file SQL (`sql/elt_clickhouse.sql` atau `sql/elt_mysql.sql`) dijalankan di dalam database
   dan menulis hasilnya ke database `elt`. Semua perhitungan dilakukan oleh mesin database, bukan Python.

SQL ditulis dua kali karena dialeknya berbeda. Contohnya: ClickHouse memakai `toDecimal64`, `dateDiff`, dan
`join_use_nulls = 1`, sedangkan MySQL memakai `CAST(... AS DECIMAL)`, `DATEDIFF`, dan `DROP TABLE` sebelum
`CREATE TABLE ... AS SELECT`.

## 5. ETL atau ELT?

| | ETL | ELT |
|---|---|---|
| Transform dikerjakan oleh | Python (pandas) | database (SQL) |
| Data mentah tersimpan di database | tidak | ya (database `raw`) |
| Database hasil | `etl` | `elt` |
| Kalau logika bisnis berubah | ubah kode Python, jalankan ulang dari CSV | ubah SQL, bisa dijalankan ulang dari `raw` |
| Beban pemrosesan | memori dan CPU mesin yang menjalankan Python | server database |
| Cocok untuk | data kecil, logika rumit yang lebih mudah di Python | data besar, database kolumnar seperti ClickHouse |

Pada proyek ini kedua cara menghasilkan angka yang sama persis, jadi bisa dipakai untuk saling memverifikasi.

## 6. Tabel hasil

**`fct_orders`**: satu baris per pesanan

| Kolom | Arti |
|---|---|
| `order_id`, `customer_id`, `order_status` | identitas dan status pesanan |
| `order_purchase_timestamp`, `order_date` | waktu dan tanggal pembelian |
| `order_delivered_customer_date` | waktu barang sampai (kosong jika belum terkirim) |
| `item_count`, `items_amount`, `freight_amount` | jumlah barang, total harga, total ongkir |
| `payment_amount` | total pembayaran |
| `delivery_days` | lama pengiriman dalam hari |
| `is_late` | terlambat dibanding estimasi (kosong jika belum terkirim) |

**`daily_sales`**: omzet per hari dan per negara bagian pelanggan (`orders`, `revenue`, `freight`, `avg_order_value`).

**`category_sales`**: omzet per kategori produk dengan nama Inggris (`items_sold`, `orders`, `revenue`).
Produk tanpa kategori masuk ke kategori `unknown`.

## 7. Peta file

| File | Fungsi |
|---|---|
| `common.py` | konfigurasi dari `.env`, `download()`, `read_csv()`, daftar tabel dan kolom tanggal |
| `extract.py` | menjalankan tahap extract |
| `targets.py` | dua kelas dengan method yang sama: `ClickHouse` dan `MySQL` (`create_db`, `write_frame`, `write_raw`, `run_sql`, `count`) |
| `etl.py` | transform pandas lalu load |
| `elt.py` | load mentah lalu jalankan SQL |
| `sql/elt_clickhouse.sql`, `sql/elt_mysql.sql` | transform ELT per dialek |
| `docker-compose.yml` | MySQL 8.4 dan ClickHouse untuk dicoba lokal |
| `.env.example` | contoh pengaturan kredensial dan nama database |

## 8. Tipe data di database tujuan

| Data | ClickHouse | MySQL |
|---|---|---|
| teks | `Nullable(String)` | `VARCHAR(255)` |
| uang | `Nullable(Decimal(18, 2))` | `DECIMAL(18, 2)` |
| waktu | `Nullable(DateTime64(6))` | `DATETIME` |
| tanggal | `Nullable(Date)` | `DATE` |
| bilangan bulat | `Nullable(Int64)` | `BIGINT` |

Di MySQL teks memakai `VARCHAR(255)`, bukan `TEXT`, karena kolom `TEXT` tidak bisa di-index tanpa panjang
awalan dan membuat `JOIN` lambat.

## 9. Masalah yang sering muncul

| Gejala | Penyebab dan solusi |
|---|---|
| `File ini tidak ditemukan di ...` | CSV belum ada. Jalankan `python extract.py` atau taruh CSV di `data/olist/`. |
| Gagal autentikasi Kaggle | Isi `KAGGLE_USERNAME` dan `KAGGLE_KEY`, atau taruh `kaggle.json` di `~/.kaggle/`. |
| Koneksi ditolak ke MySQL atau ClickHouse | Jalankan `docker compose up -d` dan cek host, port, dan password di `.env`. |
| Error `pip3` saat memasang paket | Pakai `python -m pip install -r requirements.txt` di dalam virtualenv yang aktif. |
