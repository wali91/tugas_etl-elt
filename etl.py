"""ETL: CSV -> TRANSFORM di Python (pandas) -> LOAD hasil akhir ke ClickHouse dan/atau MySQL (database etl)."""
import argparse

import pandas as pd

from common import DB_ETL, read_csv
from targets import TARGETS

EXCLUDED = ["canceled", "unavailable"]


def transform() -> dict[str, pd.DataFrame]:
    orders = read_csv("olist_orders_dataset")
    items = read_csv("olist_order_items_dataset")
    payments = read_csv("olist_order_payments_dataset")
    customers = read_csv("olist_customers_dataset")
    products = read_csv("olist_products_dataset")
    translation = read_csv("product_category_name_translation")

    for c in ["order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]:
        orders[c] = pd.to_datetime(orders[c], errors="coerce")

    # --- fct_orders: satu baris per pesanan
    item_agg = items.groupby("order_id", as_index=False).agg(
        item_count=("order_item_id", "size"),
        items_amount=("price", "sum"),
        freight_amount=("freight_value", "sum"),
    )
    pay_agg = payments.groupby("order_id", as_index=False).agg(payment_amount=("payment_value", "sum"))

    fct = orders.merge(item_agg, on="order_id", how="left").merge(pay_agg, on="order_id", how="left")
    num = ["item_count", "items_amount", "freight_amount", "payment_amount"]
    fct[num] = fct[num].fillna(0)
    fct["order_date"] = fct.order_purchase_timestamp.dt.date
    fct["delivery_days"] = (
        fct.order_delivered_customer_date.dt.normalize() - fct.order_purchase_timestamp.dt.normalize()
    ).dt.days.astype("Int64")
    known = fct.order_delivered_customer_date.notna() & fct.order_estimated_delivery_date.notna()
    fct["is_late"] = (
        (fct.order_delivered_customer_date > fct.order_estimated_delivery_date).astype("boolean").where(known)
    )
    fct = fct[[
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_date",
        "order_delivered_customer_date", "item_count", "items_amount", "freight_amount",
        "payment_amount", "delivery_days", "is_late",
    ]]

    # --- daily_sales: omzet per hari per negara bagian pelanggan
    valid = fct[~fct.order_status.isin(EXCLUDED) & fct.order_date.notna()]
    valid = valid.merge(
        customers[["customer_id", "customer_state"]].drop_duplicates("customer_id"), on="customer_id"
    )
    daily = valid.groupby(["order_date", "customer_state"], as_index=False).agg(
        orders=("order_id", "size"), revenue=("items_amount", "sum"), freight=("freight_amount", "sum"),
    )
    daily["avg_order_value"] = (daily.revenue / daily.orders).round(2)

    # --- category_sales: omzet per kategori produk (nama Inggris)
    cat = (items.merge(orders[["order_id", "order_status"]], on="order_id")
                .merge(products[["product_id", "product_category_name"]], on="product_id", how="left")
                .merge(translation, on="product_category_name", how="left"))
    cat = cat[~cat.order_status.isin(EXCLUDED)]
    cat["category"] = cat.product_category_name_english.fillna(cat.product_category_name).fillna("unknown")
    category = cat.groupby("category", as_index=False).agg(
        items_sold=("order_id", "size"), orders=("order_id", "nunique"), revenue=("price", "sum"),
    ).sort_values("revenue", ascending=False)

    return {"fct_orders": fct, "daily_sales": daily, "category_sales": category}


def main(targets: list[str]) -> None:
    tables = transform()
    for name in targets:
        t = TARGETS[name]()
        t.create_db(DB_ETL)
        for table, df in tables.items():
            n = t.write_frame(DB_ETL, table, df)
            print(f"[etl:{name}] {DB_ETL}.{table}: {n:,} baris")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", default=list(TARGETS), choices=list(TARGETS))
    main(ap.parse_args().targets)
