# Design Document — Sales Analytics Platform
**Dự án:** Data Engineering Challenge — Olist Sales Analytics

---

## 1. Phân Tích Đề Bài & Quyết Định Thiết Kế (Business Ambiguities & Decisions)

| Vấn đề | Chi tiết & Rủi ro | Quyết định thiết kế & Lý do |
|---|---|---|
| **Định nghĩa Doanh thu (Revenue)** | • Hai nguồn: `price` (`order_items`) vs `payment_value` (`order_payments`).<br>• `payment_value` ở mức đơn hàng (order-level grain) nên không biết số tiền phân bổ cho sản phẩm nào.<br>• `order_items` lưu chi tiết sản phẩm (item-level grain) giúp phân rã được theo category. | • **Revenue = `SUM(order_items.price)`** (Doanh thu thuần, loại trừ phí vận chuyển `freight_value`).<br>• Tính cả đơn trạng thái `approved` (đã duyệt thanh toán nhưng chưa giao) để phản ánh hiệu suất chốt đơn của Sales. |
| **Xử lý Freight (Phí vận chuyển)** | • Freight là khoản thu hộ chi hộ cho logistics. | • Lưu riêng `freight_value` trong Fact để phân tích chi phí, không cộng gộp vào Revenue. |
| **Doanh thu Thuế & Trả góp** | • Không có dữ liệu thuế suất cụ thể.<br>• Khách trả góp nhiều tháng (`payment_installments > 1`). | • Ghi nhận **Gross Sales** (bao gồm thuế tiêu dùng ICMS).<br>• Giả định Olist nhận ứng trước 100% dòng tiền giao dịch đầu kỳ $\rightarrow$ Ghi nhận 100% doanh thu tại thời điểm đặt hàng thay vì bẻ nhỏ theo dòng tiền hàng tháng. |
| **Ngày tra tỷ giá (Order Date)** | • Đơn hàng có 5 mốc thời gian. | • Dùng **`order_purchase_timestamp`** làm mốc chốt tỷ giá để phản ánh đúng thời điểm khách hàng đưa ra quyết định mua. |
| **Đơn hàng bị Hủy (Canceled)** | • Đơn hàng bị hủy/không khả dụng làm sai lệch doanh thu thực. | • Phân nhóm trạng thái:<br>  - *Tính doanh thu:* `approved`, `processing`, `invoiced`, `shipped`, `delivered`.<br>  - *Không tính:* `canceled`, `unavailable`, `created`.<br>• Khi hủy đơn, giữ nguyên tỷ giá ngày mua để triệt tiêu dòng tiền đối soát. |
| **Sai số tiền tệ** | • Dùng Float gây sai số làm tròn khi thực hiện các phép aggregate lớn. | • Ép toàn bộ trường tiền tệ về kiểu **`DECIMAL(18, 4)`** để đảm bảo độ chính xác tài chính. |
| **Báo cáo MTD lịch sử** | • Dữ liệu lịch sử (2018) $\rightarrow$ nếu dùng ngày hiện tại thì MTD luôn bằng 0. | • Tham số hóa `execution_date` đóng vai trò "ngày chạy báo cáo giả lập" (ví dụ: `2018-08-15`). |
| **Repeat Buyer Rate** | • Không có định nghĩa chuẩn thế nào là khách "quay lại".<br>• Đếm trọn đời dễ bị tăng tiến lũy kế ảo.<br>• Chu kỳ mua lại thực tế phụ thuộc rất nhiều vào danh mục sản phẩm (hàng tiêu dùng nhanh: 1-3 tháng, điện tử/gia dụng lớn: 1-2 năm). | • **Lifetime Repeat Buyer Rate**: Khách mua $\ge 2$ đơn trọn đời (cung cấp góc nhìn tích lũy tổng thể).<br>• **90-Day Repeat Rate**: Khách mua lại trong vòng 90 ngày. Đây là giả định chung (working assumption) cho các chiến dịch re-engagement, hoạt động tốt với hàng tiêu dùng nhanh nhưng sẽ là ngoại lệ hiếm gặp với hàng gia dụng lớn. |


---

## 2. Khám Phá Nguồn Dữ Liệu (Data Exploration & Constraints)

```
[customers] ──── 1:N ────► [orders] ──── 1:N ────► [order_items] ──── N:1 ──► [products]
                                │                                        └──── N:1 ──► [sellers]
                                ├──── 1:N ──► [order_payments]
                                └──── 1:N ──► [order_reviews]
```

### 2.1. Các bẫy dữ liệu (Data Traps) & Giải pháp

1. **Hai tầng định danh khách hàng:**
   * *Bẫy:* `customer_id` thay đổi theo từng đơn hàng.
   * *Giải pháp:* Dùng `customer_unique_id` để định danh khách hàng duy nhất và tính Repeat Buyer Rate.
2. **Sự dịch chuyển địa lý (Geographical Shift):**
   * *Bẫy:* Khách hàng thay đổi địa chỉ làm sai lệch doanh thu lịch sử theo vùng miền.
   * *Giải pháp:* Áp dụng **SCD Type 2** sử dụng **dbt Snapshots** cho `customer_state` (Region chính). Việc này giúp đối soát chính xác: đơn hàng cũ phát sinh khi khách ở Region nào sẽ được giữ nguyên doanh thu ở Region đó, không bị ghi đè/dồn hết về Region mới khi khách chuyển nhà.
3. **Rủi ro nhân dòng (Fan-out chéo):**
   * *Bẫy:* JOIN trực tiếp `order_items` (1-N) và `order_payments` (1-N) gây nhân đôi doanh thu ảo.
   * *Giải pháp:* Tách thành **2 Fact tables riêng biệt**: `fact_order_items` và `fact_order_payments`.
4. **Địa lý Fan-out (Geolocation):**
   * *Bẫy:* `zip_code_prefix` trong `geolocation` không unique (chứa nhiều tọa độ GPS).
   * *Giải pháp:* Không JOIN bảng này vào Fact. Chỉ dùng `customer_state` có sẵn trong Dim để báo cáo khu vực.
5. **Dịch danh mục sản phẩm (Product Category Translation):**
   * *Bẫy:* Một số danh mục không có trong bảng translation tiếng Anh $\rightarrow$ INNER JOIN sẽ mất dòng.
   * *Giải pháp:* Dùng `LEFT JOIN` kết hợp `COALESCE(translation, Portuguese_name)`.
6. **Lệch múi giờ khi tra tỷ giá:**
   * *Bẫy:* Dữ liệu Olist được ghi nhận theo múi giờ Brazil (BRT, UTC-3), trong khi Frankfurter API lưu trữ tỷ giá và hoạt động theo chuẩn giờ UTC. Nếu `CAST(timestamp AS DATE)` trực tiếp mà không chuyển đổi múi giờ, các giao dịch phát sinh vào cuối ngày tại Brazil (ví dụ 22:00 BRT) sẽ bị tra lệch sang tỷ giá của ngày hôm sau trên hệ thống UTC.
   * *Giải pháp:* Đã được xử lý triệt để ở tầng Staging (`stg_orders`) bằng cách quy đổi thời gian của Olist từ giờ Brazil về UTC (`AT TIME ZONE 'America/Sao_Paulo' AT TIME ZONE 'UTC'`) trước khi trích xuất ngày để JOIN tỷ giá.
7. **Bản ghi mồ côi (Orphan Records):**
   * *Bẫy:* `product_id` trong đơn hàng không tồn tại trong danh mục sản phẩm.
   * *Giải pháp:* `LEFT JOIN` và map vào `'unknown'` category để bảo toàn 100% doanh thu.
8. **Tỷ giá cuối tuần (Weekend FX Rates):**
   * *Bẫy:* API Frankfurter không có tỷ giá thứ 7 và Chủ Nhật.
   * *Giải pháp:* Sử dụng Range API v2 lấy 1 request duy nhất: `GET https://api.frankfurter.dev/v2/2016-09-01..2018-10-31?base=BRL&symbols=USD`. Áp dụng câu lệnh SQL để tự động **fallback lấy tỷ giá ngày thứ Sáu gần nhất** điền cho thứ 7 và Chủ Nhật.

---

## 3. Kế Hoạch Kiểm Chứng (Data Verification Queries)

Các query kiểm chứng chạy trực tiếp trên tầng Raw:

### 3.1. Kiểm chứng Customer Identity
```sql
-- Kiểm chứng tính duy nhất
SELECT
    COUNT(customer_id)                 AS total_rows,
    COUNT(DISTINCT customer_id)        AS unique_customer_ids,
    COUNT(DISTINCT customer_unique_id) AS unique_real_customers
FROM customers;

-- Tìm khách có nhiều địa chỉ
SELECT customer_unique_id, COUNT(DISTINCT customer_zip_code_prefix) AS zip_count
FROM customers
GROUP BY 1 HAVING COUNT(DISTINCT customer_zip_code_prefix) > 1
ORDER BY 2 DESC LIMIT 10;
```

### 3.2. Kiểm chứng Fan-out
```sql
-- So sánh dòng JOIN chéo với dòng thực tế
SELECT COUNT(*) AS joined_rows 
FROM order_items oi 
JOIN order_payments op ON oi.order_id = op.order_id;

SELECT COUNT(*) FROM order_items; -- Nếu joined_rows > count -> xảy ra fan-out
```

### 3.3. Đối soát số tiền giữa 2 nguồn (Items vs Payments)
```sql
WITH items_sum AS (
    SELECT order_id, SUM(price + freight_value) AS items_total
    FROM order_items GROUP BY 1
),
payments_sum AS (
    SELECT order_id, SUM(payment_value) AS payments_total
    FROM order_payments GROUP BY 1
)
SELECT
    COUNT(*)                                         AS total_orders_compared,
    COUNT(CASE WHEN ABS(i.items_total - p.payments_total) > 0.01 THEN 1 END) AS orders_with_diff,
    AVG(ABS(i.items_total - p.payments_total))       AS avg_diff_brl,
    COUNT(CASE WHEN ABS(i.items_total - p.payments_total) > 0.01 THEN 1 END)::FLOAT
        / NULLIF(COUNT(*), 0) * 100                  AS pct_orders_with_diff
FROM items_sum i
JOIN payments_sum p ON i.order_id = p.order_id;
```

### 3.4. Kiểm tra Orphan Records & Translation
```sql
-- Check sản phẩm mồ côi
SELECT COUNT(DISTINCT product_id) AS orphan_product_count
FROM order_items
WHERE product_id NOT IN (SELECT product_id FROM products);

-- Check category thiếu bản dịch
SELECT DISTINCT p.product_category_name
FROM products p
WHERE p.product_category_name IS NOT NULL
  AND p.product_category_name NOT IN (SELECT product_category_name FROM product_category_name_translation);
```

### 3.5. Đối soát Raw vs Warehouse (Reconciliation Check)
```sql
SELECT
    SUM(r.price)          AS raw_total_brl,
    SUM(f.price_brl)      AS warehouse_total_brl,
    ABS(SUM(r.price) - SUM(f.price_brl)) / NULLIF(SUM(r.price), 0) * 100  AS diff_pct
FROM raw_order_items r
FULL OUTER JOIN fact_order_items f ON r.order_id = f.order_id AND r.order_item_id = f.order_item_id;
```

---

## 4. Kiến Trúc Hệ Thống (System Architecture)

### 4.1. Luồng dữ liệu 3 tầng (ELT)
```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4.1. Luồng dữ liệu 3 tầng (ELT)                                                              │
│ ├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ [DATA SOURCES]        [RAW (Bronze)]        [STAGING (Silver)]       [WAREHOUSE (Gold)]      │
│                                                                                              │
│                       ┌──────────────┐      ┌──────────────┐         ┌─────────────────────┐ │
│                       │ raw_orders   │ ──►  │ stg_orders   │ ──┬──►  │  fact_order_items   │ │
│ Kaggle CSVs           ├──────────────┤      ├──────────────┤   │     ├─────────────────────┤ │
│ (orders, items,  ──►  │ raw_items    │ ──►  │ stg_items    │ ──┤     │  fact_order_payments│ │
│  payments,            ├──────────────┤      ├──────────────┤   │     └─────────────────────┘ │
│  customers,           │ raw_payments │ ──►  │ stg_payments │ ──┤     ┌─────────────────────┐ │
│  products)            ├──────────────┤      ├──────────────┤   │     │  dim_customers (SCD2│ │
│                       │ raw_customers│ ──►  │ stg_customers│ ──┼──►  ├─────────────────────┤ │
│                       ├──────────────┤      ├──────────────┤   │     │  dim_products (SCD1)│ │
│                       │ raw_products │ ──►  │ stg_products │ ──┤     ├─────────────────────┤ │
│                       └──────────────┘      └──────────────┘   │     │  dim_date           │ │
│                                                                │     ├─────────────────────┤ │
│ Frankfurter API ──►   ┌──────────────┐      ┌──────────────┐   │     │  dim_exchange_rate  │ │
│ (FX Rates BRL/USD)    │ raw_rates    │ ──►  │ stg_rates    │ ──┘     └─────────────────────┘ │
│                       └──────────────┘      └──────────────┘                │                │
│                                                                             ▼                │
│                                                                      [BI LAYER]              │
│                                                                      Power BI Dashboard      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```
* **Raw:** Chứa 100% dữ liệu gốc (Kaggle CSV và tỷ giá API).
* **Staging:** Ép kiểu dữ liệu (`DECIMAL(18, 4)`), rename chuẩn hóa, xử lý NULL.
* **Core:** Thiết kế Star Schema phục vụ truy vấn tối ưu cho Dashboard.

### 4.2. Công nghệ lựa chọn
* **Database:** PostgreSQL (Hỗ trợ các câu lệnh phân tích và dbt native).
* **Transformation:** dbt (Quản lý DAG, kiểm thử tự động, tối ưu hóa code).
* **Ingestion:** Python (Tải CSV, gọi Frankfurter API).
* **Orchestration:** Apache Airflow.

### 4.3. Điều phối (Orchestration Strategy)
Luồng chạy (DAGs) trong Airflow được thiết kế phân tách cơ chế giữa lần chạy đầu tiên và chạy định kỳ hàng ngày:

**Kịch bản 1: Lần chạy đầu tiên (Initial Load) / Backfill toàn bộ**
Do nguồn Kaggle CSV là dạng tĩnh, trong lần chạy đầu tiên (hoặc khi cần backfill), pipeline sẽ tải toàn bộ dữ liệu CSV và gọi API tỷ giá Frankfurter cho toàn bộ chuỗi ngày giao dịch lịch sử (`fetch_rates_range`). `dbt run` sẽ build full toàn bộ các bảng trong Data Warehouse.

**Kịch bản 2: Chạy định kỳ hàng ngày (Daily Incremental)**
Vận hành bằng **2 DAGs Airflow** độc lập, sử dụng tham số `execution_date` của Airflow để quyết định lấy dữ liệu ngày nào:
* **DAG A (`dag_refresh_dimensions`)**: Chạy 1 lần/ngày lúc `00:00 UTC`. 
  * *Quy trình:* Ingest dữ liệu ngày hiện tại $\rightarrow$ `dbt run Dim` $\rightarrow$ `dbt test Dim`.
  * Ở bước dbt, bảng `dim_customers` (SCD Type 2) sử dụng cơ chế `snapshot` để tự động đối chiếu toàn bảng, đóng bản ghi cũ và sinh bản ghi mới nếu có thay đổi. Bảng `dim_products` (SCD Type 1) sử dụng `materialized='table'` để ghi đè (Full Refresh) trạng thái tĩnh mới nhất.
* **DAG B (`dag_refresh_facts`)**: Chạy 3 lần/ngày lúc `00:30`, `08:30`, `16:30 UTC`. 
  * *Quy trình:* Gọi API tỷ giá Frankfurter chỉ cho riêng ngày đang chạy (`execution_date`) $\rightarrow$ `dbt run Fact` (chiến lược `merge` incremental) $\rightarrow$ `dbt test Fact`.
  * Cơ chế `merge` của dbt dựa trên unique key (vd: `order_item_key`) sẽ tự động Insert dòng mới và Update dòng cũ, đảm bảo Idempotency (chạy lại bao nhiêu lần vẫn không trùng lặp) và tiết kiệm chi phí quét dữ liệu.

**Đặc biệt: Hệ thống thiết kế cơ chế Tự chữa lành (Self-Healing / Resilience)**
Trong trường hợp Airflow bị sập hoặc tắt trong nhiều tháng, khi bật lại, Data Engineer **không cần viết script chạy bù thủ công** nhờ 2 logic tự vá lỗi:
* **Với luồng Fact:** Dùng hàm nội suy `MAX(purchase_date) - 30 days` để nối đuôi dữ liệu. dbt tự quét ngược lại mốc thời gian cuối cùng nó dừng lại ở quá khứ, vét toàn bộ dữ liệu bị hụt và chèn vào kho.
* **Với luồng Dim (Khách hàng, Sản phẩm):** Không cần lọc theo ngày tháng. Khi chạy lại, hệ thống sẽ tự động quét và đối chiếu toàn bộ danh sách khách hàng cũng như sản phẩm ở nguồn để cập nhật trạng thái mới nhất vào kho dữ liệu, đảm bảo không bỏ sót bất kỳ thông tin thay đổi nào trong thời gian hệ thống bị dừng.

### 4.4. Xử lý Dữ liệu đến muộn (Late-Arriving Dimensions)

**Tình huống thực tế gây lỗi:**
* Luồng **Fact** (đơn hàng) đồng bộ 3 lần/ngày, còn luồng **Dim** (khách hàng) chỉ đồng bộ 1 lần vào ban đêm.
* Giả sử lúc 10:00 sáng, một khách hàng mới toanh thực hiện mua đơn hàng đầu tiên. 
* Đến 16:30 chiều, luồng Fact chạy và kéo đơn hàng này về. Tuy nhiên, thông tin chi tiết của vị khách này vẫn chưa được nạp vào bảng `dim_customers` (vì phải đợi đến 00:00 đêm luồng Dim mới chạy).

**Tại sao hệ thống sẽ bị sập nếu dùng Khóa ngoại vật lý (Physical FK Constraint)?**
Nếu thiết lập ràng buộc khóa ngoại cứng ở mức Database (ví dụ: cột `customer_key` của Fact bắt buộc phải tồn tại trong bảng Dim):
* Hệ quản trị cơ sở dữ liệu (PostgreSQL) sẽ lập tức chặn đứng giao dịch nạp dữ liệu vì vi phạm ràng buộc khóa ngoại (Foreign Key Violation).
* Luồng Fact (DAG Fact) sẽ bị **báo lỗi đỏ và sập hoàn toàn**, khiến toàn bộ dữ liệu đơn hàng mới trong ngày không thể lên được Dashboard.

**Giải pháp để không mất mát số liệu:**
1. **Bỏ khóa ngoại cứng:** Không khai báo ràng buộc Foreign Key vật lý trong Database. Chỉ giữ mối quan hệ này ở mặt logic trong code.
2. **Nạp dữ liệu an toàn:** Khi nạp dữ liệu vào Fact, hệ thống sử dụng phép `LEFT JOIN` (thay vì `INNER JOIN`) với bảng Dim để đảm bảo dù khách hàng chưa được sync, dòng đơn hàng (doanh thu) vẫn được ghi nhận đầy đủ vào bảng Fact.
3. **Mặc định hóa ID chưa map:** Sử dụng hàm `COALESCE(dim.customer_key, 'pending_refresh')` để đưa các mã khách hàng chưa tồn tại về trạng thái tạm thời là "Chờ đồng bộ" (Pending Refresh). 
4. **Kết quả:** Tổng doanh thu trên Dashboard luôn chính xác 100% (không bị mất mát số liệu). Chỉ riêng thông tin phân tích theo khu vực của đơn hàng đó sẽ tạm thời hiển thị là "Chờ đồng bộ". Vào ngày hôm sau, sau khi luồng Dim chạy lúc nửa đêm để nạp khách hàng mới, mối quan hệ sẽ tự động khớp lại hoàn chỉnh.

---

## 5. Mô Hình Dữ Liệu (Star Schema)

```
                      ┌───────────────────────┐
                      │     dim_customers     │
                      │───────────────────────│
                      │ customer_key       PK │
                      │ customer_unique_id    │
                      │ customer_state        │
                      └───────────┬───────────┘
                                  │ 1
       ┌──────────────────────────┼───────────────────────────┐
       │ N                        │ N                         │ N
┌──────▼──────────────┐     ┌─────▼───────────────┐     ┌─────▼───────────────┐
│      dim_date       │     │  fact_order_items   │     │ fact_order_payments │
│─────────────────────│     │─────────────────────│     │─────────────────────│
│ date_day         PK │◄────┤ purchase_date    FK │◄────┤ purchase_date    FK │
└─────────────────────┘     │ product_id       FK ├─┐   └─────────────────────┘
                            └─────────────────────┘ │ 1
                                                    │ N
                                                ┌───▼─────────────────┐
                                                │    dim_products     │
                                                │─────────────────────│
                                                │ product_id       PK │
                                                └─────────────────────┘
```

### 5.1. Bảng Sự Kiện (Fact Tables)

#### Bảng `fact_order_items`
* **Grain:** 1 dòng = 1 item sản phẩm trong đơn hàng (`order_id + order_item_id`).
* **Các trường chính:** `order_item_key` (PK), `order_id`, `customer_key` (FK SCD Type 2), `product_id` (FK), `purchase_date` (FK), `price_brl`, `freight_brl`, `price_usd`, `freight_usd`, `order_status`.

#### Bảng `fact_order_payments`
* **Grain:** 1 dòng = 1 phương thức thanh toán của đơn hàng (`order_id + payment_sequential`).
* **Các trường chính:** `order_payment_key` (PK), `order_id`, `customer_key` (FK), `payment_type`, `payment_installments`, `payment_value_brl`, `payment_value_usd`, `purchase_date`.

### 5.2. Bảng Chiều (Dimension Tables)
* **`dim_customers`**: Khóa chính `customer_key` (Surrogate Key). Quản lý thay đổi địa chỉ bằng **SCD Type 2** thông qua dbt snapshots (`dbt_valid_from`, `dbt_valid_to`).
* **`dim_products`**: Khóa chính `product_id`. Sử dụng **SCD Type 1 (Ghi đè)** để lưu bản dịch tiếng Anh mới nhất.
* **`dim_date`**: Khóa chính `date_day`. Hỗ trợ tính toán MTD và filter thời gian.
* **`dim_exchange_rate`**: Khóa chính `date_day`. Lưu trữ tỷ giá quy đổi `brl_to_usd_rate` sau khi điền fallback tỷ giá cuối tuần.

---

## 6. Chiến Lược Nạp Dữ Liệu & Chống Trùng Lặp (Ingest & Idempotency)

| Tầng dữ liệu | Cơ chế chống trùng lặp (Idempotency) |
|---|---|
| **Raw Layer** | • CSV tĩnh: Dùng cơ chế `TRUNCATE + LOAD` ghi đè bảng thô, chạy lại không tăng dòng.<br>• API tỷ giá: Sử dụng cú pháp `UPSERT` (`ON CONFLICT (date_day) DO UPDATE`) ghi đè tỷ giá nếu trùng ngày chạy. |
| **Warehouse Layer** | • Bảng Dim: `dim_products` build mới hoàn toàn (`table`). Riêng `dim_customers` dùng cơ chế `dbt snapshot` tự đối chiếu bản ghi để cập nhật thay đổi lịch sử.<br>• Bảng Fact: Cấu hình `materialized='incremental'` kết hợp chiến lược `merge` trên unique key (`order_item_key` / `order_payment_key`) và **Lookback Window 30 ngày** để chỉ xử lý/cập nhật dữ liệu mới phát sinh hoặc có thay đổi. |
| **BI Layer** | • Tách biệt 2 Fact table độc lập để tránh bẫy nhân dòng chéo (Fan-out) khi thực hiện aggregate tổng doanh thu và tổng thanh toán. |

### Kiểm chứng Idempotency (Evidence Script)
```sql
-- Bước 1: Đếm số dòng sau lần chạy 1
SELECT (SELECT COUNT(*) FROM fact_order_items) AS r1_items, (SELECT COUNT(*) FROM fact_order_payments) AS r1_payments;

-- Bước 2: Chạy lại pipeline dbt

-- Bước 3: Kiểm tra lại (Yêu cầu kết quả trùng khớp hoàn toàn với bước 1)
SELECT (SELECT COUNT(*) FROM fact_order_items) AS r2_items, (SELECT COUNT(*) FROM fact_order_payments) AS r2_payments;
```

---

## 7. Đảm Bảo Chất Lượng Dữ Liệu (Data Quality)

### 7.1. Các bài kiểm tra tự động (dbt Tests)
* **`fact_order_items`**: `unique` & `not_null` cho `order_item_key`; test `relationships` kiểm tra khóa ngoại trỏ sang `dim_products` và `dim_customers` (được cấu hình ở mức cảnh báo `warn` để tránh sập pipeline khi bị lệch giờ đồng bộ).
* **`fact_order_payments`**: `unique` & `not_null` cho `order_payment_key`.
* **Tỷ giá quy đổi**: `not_null` đối với trường `price_usd` và `payment_value_usd`.

### 7.2. Xử lý Lỗi và Cảnh báo
* **Mất tỷ giá:** Cấu hình dbt test bắt lỗi `price_usd IS NULL`. Hệ thống sẽ chặn push dữ liệu lên Dashboard nếu phát hiện lỗi tỷ giá chưa được fallback điền đầy đủ.
* **Sản phẩm mồ côi:** Test logic tự động cảnh báo nếu xuất hiện ID sản phẩm trong Fact không khớp với Dim.

---

## 8. Các Truy Vấn KPI Cho Dashboard (BI Queries)

### 8.1. Total Revenue & MTD (USD)
```sql
SELECT
    SUM(price_usd) AS total_revenue_usd,
    SUM(CASE WHEN purchase_date >= DATE_TRUNC('month', '2018-08-15'::date) THEN price_usd ELSE 0 END) AS mtd_revenue_usd
FROM fact_order_items
WHERE order_status NOT IN ('canceled', 'unavailable');
```

### 8.2. Doanh thu theo Product Category
```sql
SELECT f.product_category, SUM(f.price_usd) AS revenue_usd
FROM public_core.fact_order_items f
WHERE f.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1 ORDER BY 2 DESC;
```

### 8.3. Doanh thu theo Customer State (Region)
```sql
SELECT f.customer_state, SUM(f.price_usd) AS revenue_usd
FROM public_core.fact_order_items f
WHERE f.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1 ORDER BY 2 DESC;
```

### 8.4. Tỷ lệ đóng góp của Freight (Freight Ratio)
```sql
SELECT
    SUM(freight_usd) AS total_freight_usd,
    SUM(price_usd) AS total_revenue_usd,
    SUM(freight_usd) / NULLIF(SUM(price_usd), 0) * 100 AS freight_ratio_pct
FROM fact_order_items
WHERE order_status NOT IN ('canceled', 'unavailable');
```

### 8.5. Phân tích phương thức thanh toán & Trả góp
```sql
SELECT
    payment_type,
    SUM(payment_value_usd) AS total_payment_usd,
    AVG(payment_installments) AS avg_installments
FROM fact_order_payments
GROUP BY 1 ORDER BY 2 DESC;
```

### 8.6. Lifetime Repeat Buyer Rate
```sql
WITH customer_order_counts AS (
    SELECT customer_unique_id, COUNT(DISTINCT order_id) AS total_orders
    FROM fact_order_items
    WHERE order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1
)
SELECT
    COUNT(*) AS total_customers,
    COUNT(CASE WHEN total_orders > 1 THEN 1 END) AS repeat_buyers,
    COUNT(CASE WHEN total_orders > 1 THEN 1 END)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS repeat_buyer_pct
FROM customer_order_counts;
```

### 8.7. 90-Day Repeat Buyer Rate
```sql
WITH order_pairs AS (
    SELECT
        a.customer_unique_id,
        a.order_id,
        a.purchase_date AS current_purchase_date,
        MAX(b.purchase_date) AS last_purchase_date
    FROM fact_order_items a
    LEFT JOIN fact_order_items b 
      ON a.customer_unique_id = b.customer_unique_id 
     AND b.purchase_date < a.purchase_date
     AND b.order_status NOT IN ('canceled', 'unavailable')
    WHERE a.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY 1, 2, 3
),
labeled_orders AS (
    SELECT
        customer_unique_id,
        CASE WHEN last_purchase_date IS NOT NULL AND (current_purchase_date - last_purchase_date) <= 90 THEN 1 ELSE 0 END AS is_90d_repeat
    FROM order_pairs
)
SELECT
    COUNT(DISTINCT customer_unique_id)                         AS total_customers,
    COUNT(DISTINCT CASE WHEN is_90d_repeat = 1
        THEN customer_unique_id END)                           AS repeat_buyers_90d,
    COUNT(DISTINCT CASE WHEN is_90d_repeat = 1
        THEN customer_unique_id END)::FLOAT
        / NULLIF(COUNT(DISTINCT customer_unique_id), 0) * 100 AS repeat_rate_90d_pct
FROM labeled_orders;
```

*Lưu ý:* Giả định 90 ngày là chủ quan — được ghi nhận rõ trong Mục 9.1.

---

## 9. Rủi Ro Đã Biết, Sự Phân Vân & Giới Hạn Thiết Kế (Honest Assessment)

### 9.1. Những quyết định phân vân trong thiết kế (Design Dilemmas)
* **Ghi nhận doanh thu từ lúc `approved`:** Chúng tôi chọn tính doanh thu ngay khi đơn hàng được duyệt thanh toán (`approved`). Cách này giúp đội Sales thấy ngay kết quả chốt đơn trên Dashboard, nhưng có rủi ro: nếu đơn hàng bị hủy muộn sau đó (ví dụ sau 30 ngày), số liệu doanh thu của các tháng cũ trên Dashboard sẽ tự động bị giảm đi, gây lệch số liệu so với các báo cáo tài chính cố định đã chốt trước đó.
* **Xử lý Dòng tiền trả góp (Installments):** Khách mua trả góp (ví dụ đơn 12 triệu trả trong 12 tháng) sẽ làm dòng tiền thực tế chảy về công ty lắt nhắt mỗi tháng 1 triệu (dưới góc độ Kế toán). Tuy nhiên, chúng tôi giả định toàn bộ 12 triệu doanh thu được ghi nhận ngay lập tức vào ngày mua. Việc không chia nhỏ số tiền này ra thành nhiều tháng tiếp theo giúp hệ thống tập trung báo cáo chính xác tốc độ bán hàng (KPI Sales) thay vì đi theo dõi dòng tiền mặt thực tế (Cash Flow).
* **Revenue: Price vs Payment Value:** Chúng tôi đắn đo giữa việc dùng `price` trong `order_items` hay `payment_value` trong `order_payments`. Chọn `price` giúp chúng tôi chia được doanh thu theo Product Category (đúng yêu cầu Head of Sales), nhưng đánh đổi lại là nếu đơn hàng bị quỵt tiền hoặc có giảm giá chéo khác thì số doanh thu từ `price` có thể bị lệch so với dòng tiền thực thu.
* **Loại bỏ Geolocation:** Bảng này chứa tọa độ GPS rất chi tiết nhưng lại có quan hệ N-N qua `zip_code_prefix` khiến dữ liệu dễ bị phình dòng (fan-out). Chúng tôi đã phân vân giữa việc tạo chiều Dim riêng hay bỏ qua. Cuối cùng, chúng tôi chọn giải pháp an toàn là loại bỏ bảng này khỏi MVP và dùng `customer_state` có sẵn để báo cáo vùng miền, chấp nhận hy sinh độ chi tiết cấp GPS để bảo toàn tính toàn vẹn dữ liệu.
* **Đắn đo giữa SCD Type 1 và SCD Type 2 cho Customers:** Chúng tôi phân vân giữa việc chỉ giữ lại địa chỉ mới nhất (SCD Type 1) để viết câu lệnh SQL JOIN đơn giản, hay lưu vết lịch sử thay đổi địa chỉ (SCD Type 2). Cuối cùng, chúng tôi chọn SCD Type 2 để đảm bảo doanh thu trong quá khứ được phân bổ chính xác cho khu vực của khách hàng tại đúng thời điểm mua hàng, chấp nhận đánh đổi là câu lệnh SQL JOIN ở bảng Fact sẽ phức tạp hơn khi phải so khớp thêm dải thời gian (`BETWEEN valid_from AND valid_to`).
* **Giả định 90 ngày cho tỷ lệ khách mua lại (Repeat Buyer Rate):** Đề bài không định nghĩa cụ thể thế nào là khách "quay lại". Chúng tôi chọn mốc thời gian tối đa là 90 ngày giữa hai lần mua liên tiếp để tính tỷ lệ này. Lý do là vì nếu khoảng cách mua lại quá dài (ví dụ từ 1 đến 2 năm), chúng tôi nghĩ nó sẽ không còn phản ánh đúng hiệu quả của các chiến dịch giữ chân khách hàng ngắn hạn. Tuy nhiên, Olist là sàn đa ngành hàng nên chu kỳ mua lại thực tế sẽ rất khác biệt:
  * Hàng tiêu dùng nhanh (mỹ phẩm, thời trang): Khách mua lại sau 30-90 ngày là rất bình thường.
  * Hàng điện tử lớn (tủ lạnh, TV): Chu kỳ mua lại phải từ 1-2 năm, nên việc khách mua lại trong vòng 90 ngày là cực kỳ hiếm.
  * Do đó, con số 90 ngày chỉ mang tính chất giả định của chúng tôi và nếu chính xác thì chắc sẽ cần chi tiết hơn theo từng category hoặc thêm vài chỉ số về khoảng thời gian quay lại.
* **Xử lý Cập nhật trễ (Late-Arriving Updates):** Do dữ liệu Olist thiếu trường `updated_at` để track thời điểm một đơn hàng thay đổi trạng thái (ví dụ từ `shipped` sang `delivered`), chúng tôi buộc phải dùng kỹ thuật **Lookback Window 30 ngày** trong incremental models của dbt. Giả định rằng mọi sự thay đổi trạng thái đơn hàng đều hoàn tất trong vòng tối đa 30 ngày kể từ ngày mua. Nếu một đơn hàng bị "ngâm" quá 30 ngày mới cập nhật status, nó sẽ bị bỏ sót trong quá trình chạy hàng ngày (silent failure).

### 9.2. Những điểm chưa chắc chắn về dữ liệu (Data Uncertainties)

> [!NOTE]
> **Giới hạn kỹ thuật của SCD Type 2 đối với dữ liệu lịch sử tĩnh (Initial Load):** 
> Vì dữ liệu ban đầu được nạp từ file CSV tĩnh và dbt snapshot yêu cầu một `unique_key` duy nhất trong mỗi lần chạy, hệ thống buộc phải deduplicate thông tin khách hàng thô (lọc `rn = 1` lấy địa chỉ cuối cùng) trước khi đưa vào snapshot để tránh lỗi trùng lặp khóa chính. Do đó, đối với dữ liệu lịch sử quá khứ, bảng `dim_customers` chỉ lưu trữ 1 phiên bản hoạt động duy nhất (hoạt động giống SCD Type 1). Tuy nhiên, cơ chế snapshot SCD Type 2 đã được thiết lập sẵn sàng về mặt hạ tầng và sẽ tự động bắt đầu theo dõi lịch sử thay đổi địa chỉ của khách hàng khi có dữ liệu mới nạp vào hằng ngày thông qua Airflow trong tương lai.

* **Bản chất của Voucher và Mã giảm giá:** Chúng tôi giả định mọi mã giảm giá (Voucher) đều được lưu trữ đầy đủ như một hình thức thanh toán để tổng tiền hàng khớp với tổng tiền khách trả. Tuy nhiên, trong thực tế, nếu hệ thống nguồn trừ thẳng tiền ở giỏ hàng (ví dụ: món hàng 100k áp mã giảm 20k, khách chỉ trả 80k) và không ghi nhận 20k được giảm đó vào bảng thanh toán, doanh thu tính theo giá sản phẩm gốc sẽ luôn bị lệch (cao hơn) so với số tiền thực tế mà công ty thu về.
* **Tỷ giá Frankfurter cuối tuần:** Mặc dù chúng tôi đã dùng code để tự động lấy tỷ giá của ngày thứ Sáu gần nhất điền vào hai ngày cuối tuần (thứ Bảy và Chủ Nhật), chúng tôi vẫn chưa thể chắc chắn hoàn toàn về độ ổn định lâu dài của API Frankfurter miễn phí này. Trong tương lai, nếu nhà cung cấp API thay đổi cách trả về dữ liệu hoặc đột ngột ngừng hoạt động, luồng nạp tỷ giá của hệ thống sẽ bị lỗi.
* **Thiếu thông tin Hoàn tiền (Returns/Refunds):** Tập dữ liệu Olist không có bảng ghi nhận trả hàng. Chúng tôi buộc phải giả định các đơn `delivered` là thành công 100% mãi mãi. Đây là một lỗ hổng dữ liệu lớn của hệ thống nguồn mà chúng tôi không thể tự quyết định giải quyết được nếu không có dữ liệu bổ sung.

### 9.3. Giới hạn của dự án trong bài test (Limitations)
* **Giới hạn kiến thức nghiệp vụ tài chính (Domain Knowledge):** Do kiến thức chuyên môn về tài chính - kế toán và quản trị dòng tiền (Cash Flow) của chúng tôi còn hạn chế, các giả định về dòng tiền trong dự án (như việc xử lý đơn trả góp, cách ghi nhận doanh thu từ trạng thái `approved`, hay cách đối soát voucher) có thể chưa hoàn toàn chuẩn xác theo kế toán tài chính doanh nghiệp. Vì vậy, chúng tôi quyết định tập trung tối đa vào việc giải quyết các bài toán đo lường hiệu suất bán hàng (KPI Sales) thay vì dòng tiền như thế nào.
* **Giới hạn nguồn dữ liệu tĩnh (Static Data Source):** Do bộ dữ liệu Olist được cung cấp dưới dạng các file CSV tĩnh, luồng nạp dữ liệu (Ingestion) hiện tại chỉ đơn giản là đọc file tĩnh vào Database chứ chưa có hệ thống tự động đồng bộ dữ liệu thay đổi (CDC/Streaming) từ cơ sở dữ liệu thực tế (Production DB). Tuy nhiên, kiến trúc dbt ở các tầng tiếp theo đã được thiết kế sẵn sàng để xử lý dữ liệu gia tăng hàng ngày (Incremental) mà không cần sửa đổi code SQL khi có nguồn dữ liệu mới chảy vào.
* **Triển khai Airflow & Giám sát (Monitoring):** Do đây là dự án thử nghiệm chạy trên máy cá nhân, chúng tôi chỉ cấu hình Airflow chạy đơn giản thông qua Docker để vận hành luồng tự động. Hệ thống chưa tích hợp các công cụ giám sát tập trung logs hay hệ thống cảnh báo tức thời khi sập pipeline qua Email/Telegram... để kịp thời fix lỗi.
* **Giới hạn về Thiết kế Kiểm thử (Data Testing Limits):** Các bài kiểm tra chất lượng dữ liệu hiện tại mới chỉ dừng lại ở mức cơ bản của dbt test (như kiểm tra trùng lặp khóa chính, cột bị rỗng). Trên thực tế, để đảm bảo hệ thống vận hành trơn tru và chính xác tuyệt đối, ta cần thiết kế thêm nhiều kịch bản kiểm thử kỹ càng và sâu sắc hơn. Do bản thân chúng tôi chưa có nhiều kinh nghiệm thực tế trong việc thiết kế các bộ test dữ liệu nâng cao, đây là một giới hạn lớn trong dự án này.
* **Loại bỏ các bảng phụ phức tạp (Reviews và Geolocation) khỏi phiên bản đầu tiên (MVP):**
  * *Bảng Đánh giá (`order_reviews`):* Bảng này bị trùng lặp nhiều mã đánh giá và một đơn hàng lại có thể có nhiều lượt review. Việc làm sạch dữ liệu này cần nhiều thời gian thiết kế nâng cao, nên chúng tôi tạm thời loại ra để tập trung vào các chỉ số doanh số cốt lõi.
  * *Bảng Tọa độ (`geolocation`):* Bảng này chứa hàng triệu dòng tọa độ GPS quá chi tiết và có quan hệ phức tạp dễ làm phình to dữ liệu khi kết nối. Chúng tôi quyết định bỏ qua bảng này để bảo vệ tính chính xác của số liệu, thay vào đó chỉ dùng thông tin Bang (`customer_state`) có sẵn để vẽ bản đồ vùng miền trên Power BI.

---

## 10. Kế hoạch Mở rộng (Scale-up Plan) khi Dữ liệu tăng gấp rất nhiều lần

Nếu dữ liệu thực tế tăng lên hàng chục hoặc hàng trăm triệu dòng, máy tính chạy PostgreSQL hiện tại chắc chắn sẽ bị quá tải. Để hệ thống sống sót và chạy mượt mà, chúng tôi sẽ nghiên cứu và nâng cấp như sau:

1. **Đổi định dạng lưu trữ sang Parquet (Lưu theo cột):**
   Thay vì lưu dữ liệu theo dạng từng dòng (row) như cơ sở dữ liệu hiện tại, ta sẽ lưu trữ trên Cloud dưới định dạng file Parquet (lưu theo cột). Việc này cực kỳ quan trọng vì khi hệ thống cơ sở dữ liệu nhận lệnh truy vấn từ các báo cáo, nó chỉ cần mở và quét đúng các cột cần tính (ví dụ cột `price`) và bỏ qua toàn bộ phần còn lại. Lợi ích là tốc độ truy vấn cực nhanh và **tiết kiệm chi phí quét dữ liệu (I/O)** một cách triệt để.
2. **Chuyển nhà lên Cloud Data Warehouse (BigQuery / Snowflake):** 
   Dữ liệu phình to thì không thể dùng 1 máy tính đơn lẻ để gánh. Chuyển lên Cloud giúp hệ thống tự động chia nhỏ công việc ra cho hàng chục máy chủ xử lý cùng lúc, chạy bao nhiêu tính tiền bấy nhiêu.
3. **Phân chi dữ liệu (Partitioning) và Phân cụm (Clustering):**
   * **Partition theo thời gian:** Thay vì để chung 100 triệu dòng vào 1 cục, ta sẽ chia bảng Fact thành từng phần theo *tháng đặt hàng*. Khi Dashboard cần xem báo cáo tháng nào, Database chỉ mở đúng dữ liệu tháng đó ra đọc, giúp giảm lượng lớn dữ liệu thừa phải quét.
   * **Phân cụm (Clustering) theo nhóm:** Với công nghệ Cloud mới, ta sẽ thiết lập Clustering cho các cột hay dùng để lọc (như `product_id`, `customer_state`). Hệ thống sẽ tự động sắp xếp các dữ liệu giống nhau nằm sát cạnh nhau. Khi báo cáo cần tính doanh thu theo một tỉnh cụ thể, nó sẽ nhặt được ngay một cục dữ liệu thay vì phải đi gom nhặt từng dòng rời rạc ở khắp nơi.
4. **Giữ vững tư duy nạp gia tăng (dbt Incremental):**
   Tuyệt đối không chạy tính toán lại từ đầu (Full Refresh) hàng ngày. Code dbt hiện tại đã được thiết kế sẵn chế độ Incremental, mỗi đêm nó chỉ nhặt đúng dữ liệu mới của ngày hôm đó để xử lý và cộng dồn vào bảng chính.
5. **Nâng cấp công cụ chạy lịch (Airflow):**
   Thay vì chạy Airflow đơn giản trên máy cá nhân, ta có thể dùng các dịch vụ Cloud (như Cloud Composer) để chạy nhiều luồng dữ liệu cùng lúc, và tự động gửi tin nhắn cảnh báo khi đường ống bị lỗi.
6. **Mô hình One Big Table (OBT) cho Data Mart (Tầng Báo Cáo):**
   Mặc dù hệ thống lõi vẫn sử dụng Star Schema (để chuẩn hóa dữ liệu), nhưng khi đưa lên báo cáo, ta có thể xây thêm tầng Data Mart dạng One Big Table (OBT). Thay vì để BI Tools tự chắp nối (JOIN) nhiều bảng, dbt sẽ gom trước bảng Fact trung tâm với các bảng Dim liên quan thành một bảng phẳng (flattened table) cho riêng từng chủ đề báo cáo. Đây là bài toán **đánh đổi (Trade-off): Storage vs Compute**. Trên Cloud, chi phí lưu trữ (Storage) rất rẻ, nên ta chấp nhận lưu dữ liệu bị lặp lại. Đổi lại, các BI Tools không bao giờ phải thực hiện lệnh `JOIN` đắt đỏ nữa, giúp tốc độ tải Dashboard cực nhanh và tiết kiệm chi phí tính toán (Compute) mỗi khi người dùng xem báo cáo.

---

## Phụ Lục — Giả Định Tổng Hợp (Assumption Registry)

| # | Giả định | Lý do | Cần kiểm chứng |
|---|---|---|---|
| A1 | Revenue = `order_items.price`, không bao gồm freight | Bảng `order_payments` chỉ ở grain đơn hàng (order-level) nên không biết số tiền cụ thể của từng sản phẩm. Chỉ có `order_items` ở grain item-level để phân rã doanh thu theo Category. | Yes — query 3.3 |
| A2 | Order date = `order_purchase_timestamp` | Thời điểm chốt giao dịch | No |
| A3 | Tỷ giá lấy theo ngày mua | Phản ánh quyết định mua | No |
| A4 | Cuối tuần dùng tỷ giá thứ 6 (fallback) | Market nghỉ cuối tuần | Yes — check API |
| A5 | Repeat buyer dùng `customer_unique_id` | `customer_id` là per-order | Yes — query 3.1 |
| A6 | `customer_state` làm Region (bỏ city, geolocation) | City gõ sai chính tả nhiều, bảng geolocation làm nhân bản dòng dữ liệu khi JOIN (hiện tượng fan-out) | Yes — query 3.5 |
| A7 | Loại `canceled` + `unavailable` khỏi dashboard | Tránh doanh thu ảo | Quyết định thiết kế |
| A8 | Thuế đã bao gồm trong `price` (Gross Sales) | Luật thuế Brazil phức tạp | Assumption only |
| A9 | `payment_type = 'not_defined'` → nhóm 'Unknown' | Không drop dòng, giữ doanh thu | Yes — check count |
| A10 | Đơn hàng `delivered` là hoàn tất 100% | Olist không có dữ liệu Returns/Refunds | Assumption only |
| A11 | Tính cả Lifetime Repeat Rate (chỉ số tích lũy) và Monthly Active Repeat Rate (chỉ số thực tế) | Tránh việc chỉ số tự động tăng theo thời gian, đo lường chính xác retention | Yes — check BI query 8.6 |
| A12 | Dùng Lookback Window 30 ngày cho dbt incremental (Fact tables) | Olist thiếu trường `updated_at`. Giả định mọi cập nhật trạng thái đơn hoàn tất trong 30 ngày từ lúc mua. | Assumption only |
