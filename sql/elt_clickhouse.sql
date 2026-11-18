-- ELT untuk ClickHouse: membaca database ${RAW_DB}, menulis database ${ELT_DB}.

CREATE OR REPLACE TABLE ${ELT_DB}.fct_orders
ENGINE = MergeTree ORDER BY order_id AS
SELECT
    assumeNotNull(o.order_id)                                   AS order_id,
    o.customer_id                                               AS customer_id,
    o.order_status                                              AS order_status,
    o.order_purchase_timestamp                                  AS order_purchase_timestamp,
    toDate(o.order_purchase_timestamp)                          AS order_date,
    o.order_delivered_customer_date                             AS order_delivered_customer_date,
    ifNull(i.item_count, 0)                                     AS item_count,
    ifNull(i.items_amount, toDecimal64(0, 2))                   AS items_amount,
    ifNull(i.freight_amount, toDecimal64(0, 2))                 AS freight_amount,
    ifNull(p.payment_amount, toDecimal64(0, 2))                 AS payment_amount,
    dateDiff('day', toDate(o.order_purchase_timestamp),
                    toDate(o.order_delivered_customer_date))    AS delivery_days,
    if(o.order_delivered_customer_date IS NULL OR o.order_estimated_delivery_date IS NULL, NULL,
       o.order_delivered_customer_date > o.order_estimated_delivery_date) AS is_late
FROM ${RAW_DB}.olist_orders_dataset AS o
LEFT JOIN (
    SELECT order_id,
           count()                                         AS item_count,
           sum(toDecimal64(ifNull(price, 0), 2))           AS items_amount,
           sum(toDecimal64(ifNull(freight_value, 0), 2))   AS freight_amount
    FROM ${RAW_DB}.olist_order_items_dataset
    GROUP BY order_id
) AS i ON i.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, sum(toDecimal64(ifNull(payment_value, 0), 2)) AS payment_amount
    FROM ${RAW_DB}.olist_order_payments_dataset
    GROUP BY order_id
) AS p ON p.order_id = o.order_id
SETTINGS join_use_nulls = 1;


CREATE OR REPLACE TABLE ${ELT_DB}.daily_sales
ENGINE = MergeTree ORDER BY (order_date, customer_state) AS
SELECT
    order_date,
    customer_state,
    count()                                             AS orders,
    sum(items_amount)                                   AS revenue,
    sum(freight_amount)                                 AS freight,
    round(toFloat64(sum(items_amount)) / count(), 2)    AS avg_order_value
FROM (
    SELECT
        assumeNotNull(f.order_date)      AS order_date,
        assumeNotNull(c.customer_state)  AS customer_state,
        f.items_amount                   AS items_amount,
        f.freight_amount                 AS freight_amount
    FROM ${ELT_DB}.fct_orders AS f
    INNER JOIN (
        SELECT customer_id, any(customer_state) AS customer_state
        FROM ${RAW_DB}.olist_customers_dataset
        GROUP BY customer_id
    ) AS c ON c.customer_id = f.customer_id
    WHERE f.order_status NOT IN ('canceled', 'unavailable') AND f.order_date IS NOT NULL
)
GROUP BY order_date, customer_state;


CREATE OR REPLACE TABLE ${ELT_DB}.category_sales
ENGINE = MergeTree ORDER BY category AS
SELECT
    category,
    count()               AS items_sold,
    uniqExact(order_id)   AS orders,
    sum(price)            AS revenue
FROM (
    SELECT
        assumeNotNull(coalesce(t.product_category_name_english, p.product_category_name, 'unknown')) AS category,
        i.order_id                                  AS order_id,
        toDecimal64(ifNull(i.price, 0), 2)          AS price
    FROM ${RAW_DB}.olist_order_items_dataset AS i
    INNER JOIN ${RAW_DB}.olist_orders_dataset AS o ON o.order_id = i.order_id
    LEFT JOIN ${RAW_DB}.olist_products_dataset AS p ON p.product_id = i.product_id
    LEFT JOIN ${RAW_DB}.product_category_name_translation AS t
           ON t.product_category_name = p.product_category_name
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
)
GROUP BY category
SETTINGS join_use_nulls = 1;
