# Olist Sales Analytics Platform — Data Engineering Challenge

Dự án này là lời giải hoàn chỉnh cho thử thách **Data Engineering Challenge — Olist Sales Analytics**, xây dựng một kho dữ liệu (Data Warehouse) 3 tầng chuẩn chỉnh (Bronze, Silver, Gold) tích hợp tỷ giá ngoại tệ USD từ Frankfurter API và điều phối qua Apache Airflow.

---

## 1. Kiến trúc hệ thống & Mô hình hóa

Hệ thống được thiết kế theo mô hình **Star Schema** tối ưu hóa hiệu suất truy vấn BI, chia làm 3 tầng:
1. **Raw (Bronze):** Nạp thô dữ liệu từ 8 file CSV Olist và tỷ giá Frankfurter API.
2. **Staging (Silver):** Làm sạch dữ liệu, ép kiểu, xử lý translation (Bồ Đào Nha → Anh).
3. **Core (Gold):** Gồm 2 bảng Fact độc lập chống nhân dòng (`fact_order_items`, `fact_order_payments`) và 4 bảng Dimension (`dim_products`, `dim_customers` với SCD Type 2, `dim_date`, `dim_exchange_rates` hỗ trợ Forward-fill tỷ giá).

*Chi tiết kiến trúc và phân tích nghiệp vụ xem tại: [design_document_final.md](design_document_final.md)*

---

## 2. Cấu trúc thư mục

```
TC-Data-Test/
├── README.md                           # Hướng dẫn này
├── design_document_final.md            # Tài liệu thiết kế kiến trúc hệ thống
├── challenge_requirements.md           # Tóm tắt đề bài & yêu cầu
├── docker-compose.yml                  # Dựng Postgres 15 + Airflow (LocalExecutor)
│
├── ingestion/                          # Extract & Load (Python + uv)
│   ├── pyproject.toml                  # uv project configuration
│   ├── uv.lock                         # Dependencies lockfile
│   └── src/
│       ├── load_csv.py                 # Ingest Olist CSVs (TRUNCATE + INSERT)
│       └── fetch_exchange_rates.py     # Ingest Frankfurter rates (UPSERT)
│
├── dbt_project/                        # Transformation & DQ (dbt)
│   ├── dbt_project.yml                 # Cấu hình dbt
│   ├── profiles.yml                    # Kết nối database Postgres
│   ├── snapshots/                      # snap_customers.sql (SCD Type 2)
│   ├── models/                         # Staging & Core models
│   └── tests/                          # Custom tests (Reconciliation & Fan-out)
│
├── airflow/                            # Orchestration (Airflow)
│   ├── Dockerfile                      # Airflow image tích hợp dbt + uv packages
│   └── dags/                           # 2 DAGs quản lý tiến trình tự động
│
├── reports/                            # Power BI Dashboard file (.pbix)
├── data/                               # Chứa 8 file CSV thô (tải bằng script)
├── evidence/                           # Screenshots chứng minh kết quả DQ + DAGs
└── scripts/
    ├── download_data.py                # Tự động tải dataset từ Kaggle
    ├── init_db.sql                     # Khởi tạo schemas cho Postgres
    └── setup.ps1                       # Script khởi tạo 1 lệnh duy nhất trên Windows
```

---

## 3. Hướng dẫn chạy dự án nhanh (Quick Start)

### Yêu cầu tối thiểu:
1. **Docker Desktop** (Đang chạy).
2. **uv** (Python package manager). *Cài nhanh qua PowerShell: `pip install uv`*
3. **Power BI Desktop** (Để xem báo cáo tương tác).

### Khởi chạy tự động bằng PowerShell (Khuyên dùng)
Mở PowerShell ở thư mục gốc của dự án và chạy:
```powershell
.\scripts\setup.ps1
```
*Script này sẽ tự động: copy `.env.example` -> `.env`, tạo Python venv, tải dataset Olist về thư mục `data/`, và dựng Docker container Postgres + Airflow.*

---

## 4. Vận hành thủ công & Kiểm thử

### Bước 1: Thu thập dữ liệu (Ingestion)
Nạp 8 file CSV Olist và backfill tỷ giá Frankfurter API 2 năm (2016-2018):
```bash
cd ingestion
# Kích hoạt venv
.venv\Scripts\activate

# Ingest CSVs
uv run python src/load_csv.py

# Backfill tỷ giá (1 API call duy nhất lấy 2 năm)
uv run python src/fetch_exchange_rates.py --backfill
```

### Bước 2: Chạy dbt (Transformation & Kiểm thử DQ)
```bash
cd ../dbt_project
# Tải các gói thư viện dbt-utils
dbt deps

# Chạy snapshot cho chiều SCD Type 2 Customers
dbt snapshot

# Build toàn bộ mô hình Star Schema
dbt run

# Chạy tất cả các bài kiểm tra chất lượng dữ liệu tự động
dbt test
```

---

## 5. Kết nối & Thiết kế Dashboard trên Power BI

Vì file báo cáo Power BI (`.pbix`) là định dạng nhị phân, bạn cần mở Power BI Desktop trên máy cá nhân để kết nối trực tiếp đến Data Warehouse PostgreSQL đang chạy trong Docker container theo các bước sau:

### 1. Thiết lập kết nối PostgreSQL Database:
* Mở **Power BI Desktop**.
* Chọn **Get Data** $\rightarrow$ **PostgreSQL database**.
* Điền thông tin cấu hình kết nối:
  * **Server:** `localhost:5432`
  * **Database:** `olist_warehouse`
  * **Data Connectivity mode:** Chọn **Import** (để Power BI tải và nén dữ liệu giúp tối ưu hóa hiệu năng).
* Tại màn hình thông tin đăng nhập, chọn tab **Database** và điền:
  * **User:** `olist_admin`
  * **Password:** `olist_secret_2024`

### 2. Các bảng cần Import (Schema `public_core`):
Nhấn chọn import các bảng thuộc tầng Gold (đã được dbt làm sạch và chuẩn hóa):
* `fact_order_items`
* `fact_order_payments`
* `dim_customers`
* `dim_products`
* `dim_date`
* `dim_exchange_rates`

### 2. Airflow UI (Orchestrator):
* URL: `http://localhost:8080` (User: `admin` / Password: `admin`).
* Có 2 DAGs chạy tự động:
  - **`dag_refresh_dimensions`** (Chạy lúc 00:00 UTC): Refresh danh mục sản phẩm, khách hàng, chạy snapshot SCD Type 2.
  - **`dag_refresh_facts`** (Chạy 3 lần/ngày): Lấy tỷ giá ngày mới nhất, load đơn hàng tăng dần (incremental) và chạy test đối soát doanh thu.

---

## 6. Chứng minh tính Idempotency & Đối soát DQ

* **Idempotency:** Bạn có thể chạy lệnh `dbt run` hoặc các script ingestion bao nhiêu lần tùy ý. Số lượng dòng và dữ liệu doanh thu trong `fact_order_items` sẽ không bao giờ bị nhân bản hoặc sai lệch.
* **Đối soát chéo:** Bài kiểm thử `reconcile_revenue` tự động so sánh doanh thu dựa trên tiền hàng (`fact_order_items.price + freight`) với tổng tiền thanh toán (`fact_order_payments.payment_value`) của từng đơn hàng. Bất kỳ đơn hàng nào có chênh lệch > 1 BRL sẽ làm bài test fail ngay lập tức để cảnh báo.
* *Các hình ảnh chứng minh cụ thể được ghi nhận tại file: `writeup.md`*
