-- ELT untuk MySQL: membaca database ${RAW_DB}, menulis database ${ELT_DB}.

DROP TABLE IF EXISTS `${ELT_DB}`.fct_orders;
CREATE TABLE `${ELT_DB}`.fct_orders AS
SELECT
    o.order_id                                                  AS order_id,
    o.customer_id                                               AS customer_id,
    o.order_status                                              AS order_status,
    o.order_purchase_timestamp                                  AS order_purchase_timestamp,
    DATE(o.order_purchase_timestamp)                            AS order_date,
    o.order_delivered_customer_date                             AS order_delivered_customer_date,
    COALESCE(i.item_count, 0)                                   AS item_count,
    COALESCE(i.items_amount, 0)                                 AS items_amount,
    COALESCE(i.freight_amount, 0)                               AS freight_amount,
    COALESCE(p.payment_amount, 0)                               AS payment_amount,
    DATEDIFF(o.order_delivered_customer_date,
             o.order_purchase_timestamp)                        AS delivery_days,
    CASE WHEN o.order_delivered_customer_date IS NULL
           OR o.order_estimated_delivery_date IS NULL THEN NULL
         ELSE o.order_delivered_customer_date > o.order_estimated_delivery_date
    END                                                         AS is_late
FROM `${RAW_DB}`.olist_orders_dataset AS o
LEFT JOIN (
    SELECT order_id,
           COUNT(*)                                    AS item_count,
           SUM(CAST(price AS DECIMAL(18, 2)))          AS items_amount,
           SUM(CAST(freight_value AS DECIMAL(18, 2)))  AS freight_amount
    FROM `${RAW_DB}`.olist_order_items_dataset
    GROUP BY order_id
) AS i ON i.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, SUM(CAST(payment_value AS DECIMAL(18, 2))) AS payment_amount
    FROM `${RAW_DB}`.olist_order_payments_dataset
    GROUP BY order_id
) AS p ON p.order_id = o.order_id;


DROP TABLE IF EXISTS `${ELT_DB}`.daily_sales;
CREATE TABLE `${ELT_DB}`.daily_sales AS
SELECT
    f.order_date                                   AS order_date,
    c.customer_state                               AS customer_state,
    COUNT(*)                                       AS orders,
    SUM(f.items_amount)                            AS revenue,
    SUM(f.freight_amount)                          AS freight,
    ROUND(SUM(f.items_amount) / COUNT(*), 2)       AS avg_order_value
FROM `${ELT_DB}`.fct_orders AS f
JOIN (
    SELECT customer_id, MAX(customer_state) AS customer_state
    FROM `${RAW_DB}`.olist_customers_dataset
    GROUP BY customer_id
) AS c ON c.customer_id = f.customer_id
WHERE f.order_status NOT IN ('canceled', 'unavailable') AND f.order_date IS NOT NULL
GROUP BY f.order_date, c.customer_state;


DROP TABLE IF EXISTS `${ELT_DB}`.category_sales;
CREATE TABLE `${ELT_DB}`.category_sales AS
SELECT
    x.category                      AS category,
    COUNT(*)                        AS items_sold,
    COUNT(DISTINCT x.order_id)      AS orders,
    SUM(x.price)                    AS revenue
FROM (
    SELECT
        COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
        i.order_id                                  AS order_id,
        CAST(i.price AS DECIMAL(18, 2))             AS price
    FROM `${RAW_DB}`.olist_order_items_dataset AS i
    JOIN `${RAW_DB}`.olist_orders_dataset AS o ON o.order_id = i.order_id
    LEFT JOIN `${RAW_DB}`.olist_products_dataset AS p ON p.product_id = i.product_id
    LEFT JOIN `${RAW_DB}`.product_category_name_translation AS t
           ON t.product_category_name = p.product_category_name
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
) AS x
GROUP BY x.category
ORDER BY revenue DESC;
