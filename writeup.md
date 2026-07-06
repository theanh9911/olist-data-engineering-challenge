# Project Write-up

---

## 1. Phát Hiện Thú Vị Về Dữ Liệu (Data Insights & Findings)

Trong quá trình phân tích và xây dựng pipeline, chúng tôi phát hiện một số đặc điểm nghiệp vụ quan trọng của Olist:

1. **Sai lệch kế toán trong dữ liệu gốc:**
    * Có đúng **249 đơn hàng (0.25%)** bị lệch nhiều hơn 1.00 BRL khi so sánh **tổng tiền hàng hóa cộng dồn** (SUM của `price` + `freight_value` của tất cả sản phẩm trong đơn) với **tổng tiền khách thực tế thanh toán** (`payment_value`). 
    * **Liên hệ Thiết kế & Nghiệp vụ:** Sự lệch này đã được dự báo từ đầu tại **[Mục 1.1 của Tài liệu thiết kế (design_document_final.md)](design_document_final.md#L9-L29)**. Bảng `order_items` phản ánh hóa đơn gốc của Người bán (Sellers) (chứa phí ship `freight_value` riêng cho từng sản phẩm), trong khi bảng `order_payments` phản ánh dòng tiền thực tế chạy qua Cổng thanh toán (Buyers & Gateway).
   * **Các nguyên nhân nghiệp vụ giả định (Working Hypotheses):** Sự sai lệch này có thể do một vài nguyên nhân như sau:
     - *Phí trả góp & Lãi suất thẻ tín dụng:* Khi khách chọn trả góp nhiều kỳ (`payment_installments > 1`), ngân hàng hoặc cổng thanh toán (gateway) có thể tính thêm lãi gộp vào `payment_value`, làm nó cao hơn giá trị gốc của hàng hóa.
     - *Mã giảm giá/Voucher bù tiền của sàn:* Khách hàng sử dụng voucher tích lũy hoặc chương trình khuyến mãi do sàn tài trợ có thể làm dòng tiền thực trả (`payment_value`) ít hơn, nhưng người bán vẫn ghi nhận hóa đơn theo giá trị món hàng gốc.
     - *Hoàn tiền một phần (Partial Refunds) hoặc phát sinh tranh chấp sau giao dịch.*
    * Do đó, hệ thống của chúng tôi đã xử lý cảnh báo dạng `warn` để đảm bảo tính trung thực tài chính, không ép buộc dữ liệu khớp nhân tạo.
2. **Kỳ nghỉ tài chính của Frankfurter API:**
   * Tỷ giá BRL $\rightarrow$ USD không được công bố vào cuối tuần hoặc ngày lễ (ví dụ Tết Dương Lịch 1-3/01/2016). 
   * Cơ chế **Backward-fill + Forward-fill** trong dbt đã giải quyết triệt để vấn đề này, đảm bảo không một giao dịch nào trong lịch sử bị NULL tỷ giá quy đổi.
3. **Ép kiểu dữ liệu bẩn:**
   * Một số trường kích thước sản phẩm trong file CSV thô được biểu diễn dưới dạng số thực kèm chữ (ví dụ `"40.0"`). Việc sử dụng double-casting (`::DECIMAL::INTEGER`) ở tầng Staging đã xử lý an toàn lỗi này.
4. **Đỉnh doanh thu kỷ lục ngày 24/11/2017 (Black Friday 2017):**
   * Ngày Black Friday 24/11/2017 ghi nhận mức doanh thu ngày cao nhất lịch sử toàn bộ dữ liệu là **`47,241.76 USD`** (tiền hàng thuần).
   - *Lý do giữ ngôi vương:* Olist tăng trưởng bùng nổ trong năm 2017 nên doanh số vượt trội so với giai đoạn thô sơ năm 2016. Đặc biệt, dữ liệu bị cắt (cut-off) vào tháng 10/2018 nên không ghi nhận sự kiện Black Friday 2018 (vốn được kỳ vọng sẽ lớn hơn nhiều do baseline năm 2018 cao hơn). Do đó, ngày 24/11/2017 trở thành đỉnh doanh thu ngày cao nhất và duy nhất trong toàn bộ lịch sử dữ liệu.

---

## 2. Chứng Minh Tính Bất Biến (Idempotency Proof)

Hệ thống đảm bảo tính bất biến (**Idempotency** — chạy lại hoặc chạy bù bao nhiêu lần cũng ra một kết quả duy nhất) ở cả 3 tầng nhờ các cơ chế thiết kế sau:

*   **Tầng Ingestion (CSV & API):**
    *   *Dữ liệu tĩnh (CSV):* Sử dụng chiến lược `TRUNCATE + INSERT` (hoặc `DROP + CREATE + COPY`) để ghi đè hoàn toàn dữ liệu thô cũ, ngăn ngừa tích lũy trùng lặp khi chạy lại.
    *   *Dữ liệu động (Exchange Rates API):* Script nạp tỷ giá trong Airflow được tham số hóa theo ngày chạy của DAG (`execution_date` / `ds`). Khi nạp vào database, sử dụng cú pháp **`UPSERT (INSERT ON CONFLICT DO UPDATE)`** dựa trên trường khóa chính `date_day`. Do đó, nếu một ngày chạy của DAG bị lỗi và được kích hoạt lại (retry/backfill), dữ liệu tỷ giá của ngày đó sẽ được cập nhật/ghi đè chứ không bao giờ bị nhân bản dòng.
*   **Tầng Biến Đổi Dữ Liệu (dbt):**
    *   *Bảng chiều (Dimensions):* Các bảng chiều được dbt build dạng `table` (materialized='table') giúp tự động tạo mới hoàn toàn bảng sạch sau mỗi lần chạy.
    *   *Bảng sự kiện (Fact Tables):* Hai bảng `fact_order_items` và `fact_order_payments` được cấu hình dạng **`incremental`** với cơ chế **`merge`** dựa trên khóa chính độc nhất (`unique_key` là `order_item_key` và `order_payment_key`). Khi Airflow chạy lệnh `dbt run` cho các ngày chạy mới hoặc chạy bù (backfill), dbt thực hiện so khớp và ghi đè các dòng đã tồn tại, chỉ insert các dòng mới. Điều này ngăn ngừa tuyệt đối lỗi trùng dòng ở tầng Gold.

### Hình ảnh chứng minh chạy dbt snapshot và dbt run qua các lần chạy (Idempotency):

**1. dbt snapshot thành công:**
![dbt snapshot thành công](evidence/dbt_snapshot.jpg)

**2. dbt run lần 1 thành công:**
![dbt run lần 1 thành công](evidence/dbt_run_1.jpg)

**3. dbt run lần 2 thành công (Idempotency):**
![dbt run lần 2 thành công (Idempotency)](evidence/dbt_run_2.jpg)

---

## 3. Bằng Chứng Vượt Qua Kiểm Thử DQ (Data Quality Results)

Cả hai luồng công việc trên Airflow đã chạy thành công tốt đẹp, vượt qua toàn bộ các bài kiểm thử chất lượng dữ liệu tự động.

### 3.1. Luồng Refresh Tự Động Trên Airflow

**1. Luồng refresh Dimensions (dim) chạy thành công:**
![Airflow DAG refresh Dimensions](evidence/airflow_dag_dim_3.jpg)
*Hình 1: Airflow DAG refresh_dimensions chạy thành công hàng ngày, tự động nạp tỷ giá và đồng bộ hóa các bảng chiều (Products, Customers, Date).*

**2. Luồng refresh Facts (fact) chạy thành công:**
![Airflow DAG refresh Facts](evidence/airflow_dag_fact_3.jpg)
*Hình 2: Airflow DAG refresh_facts chạy thành công 3 lần/ngày để cập nhật các giao dịch mua sắm mới nhất.*

### 3.2. Kết Quả Kiểm Thử Chất Lượng Dữ Liệu (dbt test)
![dbt test thành công](evidence/dbt_test.jpg)
*Hình 3: Kết quả chạy dbt test xác thực các ràng buộc dữ liệu quan trọng.*

**Chi tiết kết quả kiểm thử:**
*   **Luồng Dimension (`dag_refresh_dimensions`):** Vượt qua **11/11 bài kiểm thử (PASS = 11)**, xác thực tính duy nhất (Unique) và không rỗng (Not Null) của các khóa chính trên bảng chiều.
*   **Luồng Facts (`dag_refresh_facts`):** Hoàn thành **12/12 bài kiểm thử (PASS = 11, WARN = 1)**.
    *   Bài test đối soát chéo `reconcile_revenue` trả về cảnh báo `WARN` cho **249 đơn hàng bị lệch tài chính trong dữ liệu gốc** (như đã phân tích tại Mục 1). Việc thiết lập cảnh báo này thay vì báo lỗi đỏ giúp hệ thống dbt tiếp tục chạy mượt mà mà vẫn cảnh báo trung thực cho đội vận hành về lỗi dữ liệu đầu vào.

---

## 4. Hướng Dẫn Xem Báo Cáo & Dashboard

1. **Dashboard Tương Tác:** Mở tệp tin **`reports/Olist_Sales_Dashboard.pbix`** bằng Power BI Desktop. Dữ liệu đã được cache sẵn đầy đủ thông tin MTD, Repeat Buyers, tỷ giá USD và doanh thu theo vùng miền.
2. **Hình ảnh chứng minh:** Toàn bộ ảnh chụp màn hình DAGs chạy thành công và báo cáo kiểm thử được lưu trữ tại thư mục **`evidence/`** của dự án và được hiển thị chi tiết trong báo cáo này.

### Hình ảnh mô hình mối quan hệ Star Schema (BI Data Model):
![Power BI Data Model Relationship View](evidence/bi_data_model.jpg)

### Hình ảnh tổng quan của Dashboard hoàn chỉnh:
![Tổng quan Dashboard bán hàng Olist](evidence/dashboard_overall.jpg)

---

## 5. Bằng Chứng Đối Soát Số Liệu & Tính Bất Biến (Reconciliation & Idempotency Proof)

Để chứng minh hệ thống hoạt động tuyệt đối chính xác (không chỉ nói "chắc là đúng"), dưới đây là số liệu đối chiếu thực tế giữa tầng Raw (tải từ file CSV) và tầng Gold Fact (sau dbt transformations):

### 5.1. Bảng số liệu đối soát doanh thu & chi phí (Reconciliation Figures)

### Hình ảnh minh chứng đối soát khớp số liệu trực tiếp trên database (Lần 1 và Lần 2):

**Lần chạy 1:**
![Đối soát số liệu lần chạy 1](evidence/reconciliation_proof_1.jpg)

**Lần chạy 2 (Số dòng giữ nguyên):**
![Đối soát số liệu lần chạy 2 (Số dòng giữ nguyên)](evidence/reconciliation_proof_2.jpg)

**Chứng minh đối soát tự động qua Airflow DAG:**
![Bằng chứng đối soát trên Airflow](evidence/reconciliation_proof_dag_3.jpg)


| Chỉ số đối soát | Dữ liệu thô từ CSV gốc (`raw`) | Bảng Gold Fact (`public_core`) | Kết quả đối soát |
| :--- | :---: | :---: | :---: |
| **Tổng tiền hàng (Sum Price)** | `13,591,643.70 BRL` | `13,591,643.70 BRL` | **Khớp 100% (Lệch 0.00 BRL)** |
| **Tổng phí ship (Sum Freight)** | `2,251,909.54 BRL` | `2,251,909.54 BRL` | **Khớp 100% (Lệch 0.00 BRL)** |
| **Tổng thanh toán (Sum Payment)** | `16,008,872.12 BRL` | `16,008,872.12 BRL` | **Khớp 100% (Lệch 0.00 BRL)** |

*Lưu ý:* Tổng đơn hàng trong hệ thống gốc là `99,441` đơn. Sau khi lọc bỏ các đơn `canceled` và `unavailable` để ghi nhận doanh thu cho bộ phận Sales, số lượng đơn hàng hợp lệ phục vụ báo cáo là `98,207` đơn.

### 5.2. SQL Queries đối soát trực tiếp trên Database
Hội đồng tuyển dụng hoặc giám khảo có thể chạy trực tiếp các câu lệnh sau trên PostgreSQL để tự động đối chiếu số liệu:

**Query 1: Đối soát tiền hàng (`price` và `freight`):**
```sql
SELECT 
    (SELECT SUM(price::numeric) FROM raw.order_items) AS raw_price,
    (SELECT SUM(price_brl) FROM public_core.fact_order_items) AS gold_price,
    (SELECT SUM(freight_value::numeric) FROM raw.order_items) AS raw_freight,
    (SELECT SUM(freight_brl) FROM public_core.fact_order_items) AS gold_freight;
```

**Query 2: Đối soát tiền thanh toán (`payment_value`):**
```sql
SELECT 
    (SELECT SUM(payment_value::numeric) FROM raw.order_payments) AS raw_payment,
    (SELECT SUM(payment_value_brl) FROM public_core.fact_order_payments) AS gold_payment;
```

### 5.3. Bằng chứng kiểm tra trùng lặp và phình dòng (Idempotency & Duplicate Proof)
Khi chạy lại toàn bộ script nạp Python hoặc chạy lệnh `dbt run` nhiều lần, số lượng dòng dữ liệu hoàn toàn không thay đổi:

* **Số lượng dòng trong `fact_order_items`:** Luôn cố định ở **`112,650` dòng** (bằng đúng số dòng trong file `olist_order_items_dataset.csv` gốc).
* **Số lượng dòng trong `fact_order_payments`:** Luôn cố định ở **`103,886` dòng** (bằng đúng số dòng trong file `olist_order_payments_dataset.csv` gốc).

*Chứng minh bằng SQL (trả về 0 dòng nếu không bị trùng lặp khóa chính):*
```sql
-- Kiểm tra trùng lặp khóa chính của bảng items
SELECT order_item_key, COUNT(*)
FROM public_core.fact_order_items
GROUP BY 1 HAVING COUNT(*) > 1;

-- Kiểm tra trùng lặp khóa chính của bảng payments
SELECT order_payment_key, COUNT(*)
FROM public_core.fact_order_payments
GROUP BY 1 HAVING COUNT(*) > 1;
```

---

## 6. Tổng Quan Dashboard & Phân Tích Nghiệp Vụ (Dashboard Overview & Business Insights)

Báo cáo **Olist Sales Performance Dashboard** (lưu tại [Olist_Sales_Dashboard.pbix](file:///d:/H/TC-Data-Test/reports/Olist_Sales_Dashboard.pbix)) được thiết kế theo bố cục Grid-based 16:9 chuyên nghiệp, sử dụng tông màu Xanh Navy đậm (`#0A2540`) sạch sẽ.

### 6.1. Số Liệu Sơ Bộ & Giải Trình Tài Chính (Financial Summary)
*   **Doanh thu hàng hóa (Revenue):** **`4.02M USD`** (98K đơn hàng hợp lệ, AOV `40.95 USD`, 95K khách hàng thực tế).
*   **Tổng thanh toán (Payments):** **`4.77M USD`**.
    *   *Giải trình độ lệch (Hesitation in Design Doc):* Tổng thanh toán cao hơn tổng doanh thu hàng hóa do bao gồm **Phí vận chuyển** (`2.25M BRL` ~ `0.7M USD`), **lãi suất trả góp** phát sinh qua cổng thanh toán, và các **giao dịch đơn hàng hủy** trước khi hoàn tiền.
*   **Tỷ lệ quay lại mua hàng (Retention):** Tỷ lệ mua lại trọn đời là **`3.03%`**, quay lại trong 90 ngày là **`1.23%`**. Đây là tỷ lệ thấp đặc thù của mô hình Olist (khách hàng mua qua các sàn lớn như Mercado Livre nên không nhận diện được thương hiệu Olist).

### 6.2. Đối Chiếu Đáp Ứng & Trả Lời Trực Tiếp Cho Head of Sales (Business Q&A)
Dưới đây là các câu trả lời trực tiếp bằng số liệu thực tế được Dashboard chứng minh để trả lời các câu hỏi nghiệp vụ của Trưởng bộ phận Kinh doanh (Head of Sales):

1.  **Doanh thu theo ngày (Daily Revenue):** Dao động trung bình ở mức `5K - 10K USD/ngày`. Đạt đỉnh doanh số lịch sử đột biến ở mức **`41K USD`** vào ngày Black Friday (24/11/2017) (chiếm hơn 13% doanh thu toàn tháng chỉ trong 1 ngày).
2.  **Doanh thu theo Danh mục sản phẩm (Category):** Dẫn đầu lũy kế là **Sức khỏe & Làm đẹp (health_beauty)** đạt **`0.37M USD`**. 
    *   *Ví dụ thực nghiệm:* Khi lọc riêng tháng 11/2017, danh mục **Đồng hồ & Quà tặng (watches_gifts)** vọt lên vị trí số 1 (`30K USD`) và **Đồ chơi (toys)** vọt lên vị trí số 5 (`20K USD`) do chuẩn bị cho mùa quà tặng Giáng Sinh.
3.  **Doanh thu theo Khu vực khách hàng (Region):** Khách hàng tại bang **São Paulo (SP)** chiếm vị trí số một với **`1.53M USD`** (hơn 38% doanh số toàn sàn). Cụm 3 bang vùng Đông Nam (SP, RJ, MG) chiếm tới 64% doanh thu.
4.  **Sản phẩm bán chạy nhất (Top Selling Products):** Sản phẩm đứng đầu bảng xếp hạng là mã băm `bb50f2e236e5eea0100680137654686c` thuộc nhóm hàng `health_beauty` mang về doanh số **`18,592.27 USD`**.
5.  **Doanh thu lũy kế trong tháng (MTD Revenue):** Hoạt động linh hoạt theo mốc thời gian được chọn trên thanh trượt Slicer.
    *   *Ví dụ thực nghiệm 1 (Lọc 1 tháng):* Khi lọc riêng tháng 11/2017 (từ 01/11 đến 30/11/2017), thẻ MTD hiển thị chính xác tổng doanh thu lũy kế của tháng đó đạt **`308.81K USD`** (khớp 100% với tổng doanh thu tháng).
    *   *Ví dụ thực nghiệm 2 (Lọc nhiều tháng):* Khi lọc khoảng thời gian từ 01/06/2018 đến 31/07/2018 (hai tháng), thẻ MTD hiển thị chính xác **`229.78K USD`** – bằng đúng doanh thu lũy kế của riêng tháng cuối cùng trong kỳ lọc (Tháng 7/2018) theo đúng logic chuyển dịch ngữ cảnh (Filter Context Transition) của Power BI.
6.  **Tỷ lệ phần trăm khách hàng quay lại mua hàng (Repeat Buyers):** Tỷ lệ khách hàng quay lại mua hàng trọn đời (Repeat Buyer Rate) là **`3.03%`**, và tỷ lệ quay lại trong vòng 90 ngày là **`1.23%`**.
7.  **Quy đổi ngoại tệ sang USD theo ngày đặt hàng:** Được giải quyết triệt để ngay ở tầng dữ liệu dbt. Toàn bộ doanh thu hàng hóa trên Dashboard được tính bằng cách cộng dồn cột `price_usd` (được nhân chéo tỷ giá Frankfurter BRL $\rightarrow$ USD đúng vào ngày mua của từng giao dịch).

### 6.3. Các Insights Nghiệp Vụ Khám Phá Từ Dữ Liệu (Key Business Insights)
*   **Hiệu ứng tập trung địa lý & Điểm nghẽn Logistics (Case Study đối soát SP vs AC/AM/CE):** 
    Dữ liệu đối soát trọn đời (`01/01/2016 - 31/12/2018`) giữa bang trung tâm **São Paulo (SP)** và nhóm bang vùng xa **AC, AM, CE** (Miền Bắc/Đông Bắc) cho thấy mối tương quan chặt chẽ giữa Logistics và hành vi tiêu dùng:
    - *Gánh nặng chi phí logistics:* Tỷ lệ Payments / Revenue của nhóm bang vùng xa là **`123.5%`** (khách hàng phải trả thêm 23.5% chi phí ngoài tiền hàng), trong khi ở SP chỉ là **`116.3%`** (chênh lệch **7.2%** "thuế khoảng cách" do phí ship cao).
    - *Giá trị đơn hàng trung bình (AOV):* AOV ở vùng xa đạt **`51.10 USD`**, cao hơn **37.1%** so với SP (`37.26 USD`). Khách hàng vùng xa chủ động gom nhiều món hoặc mua hàng giá trị cao để bõ tiền ship đắt, trong khi khách hàng SP thường đặt các đơn nhỏ lẻ, ngẫu hứng.
    - *Tác động giữ chân (Retention):* Tỷ lệ mua lại trọn đời ở SP là **`3.13%`** và 90 ngày là **`1.34%`**, **gấp 1.7 lần** so với nhóm vùng xa (AC, AM, CE lần lượt chỉ đạt **`1.84%`** và **`0.79%`**). Điều này chứng minh hiệu quả logistics (ship nhanh, rẻ) tỷ lệ thuận trực tiếp với lòng trung thành khách hàng.
*   **Hành vi quay lại mua hàng cực kỳ thấp (Retention):** Tỷ lệ quay lại trọn đời toàn sàn chỉ `3.03%` và 90 ngày chỉ `1.23%`. Lý do là mô hình Olist hoạt động như một cổng kết nối trung gian (khách hàng mua qua các sàn lớn như Mercado Livre nên không biết đến Olist).
*   **Hiệu ứng Black Friday & Giới hạn dữ liệu (Data Limitation):** 
    - *Lịch thực tế:* Black Friday được tổ chức vào ngày Thứ Sáu ngay sau ngày Lễ Tạ Ơn (Thanksgiving) của Mỹ (Thứ Năm thứ tư của tháng 11). Trong năm 2017, Lễ Tạ Ơn là ngày 23/11, vì vậy Black Friday diễn ra chính xác vào ngày **Thứ Sáu, 24/11/2017**.
    - *Số liệu diễn biến tuần lễ:* 
      + Trước sự kiện (Thứ Tư, 22/11): Đáy doanh số tuần đạt **`8K USD`**.
      + Bắt đầu tăng nhẹ (Thứ Năm, 23/11): Đạt **`13K USD`** khi các chiến dịch khuyến mãi sớm được kích hoạt.
      + Bùng nổ cực đại (Thứ Sáu, 24/11 - Black Friday): Doanh thu vọt thẳng đứng lên đỉnh kỷ lục **`41K USD`** (gấp **5.1 lần** so với ngày thứ Tư), chiếm **13.3%** tổng doanh số cả tháng 11/2017 (`308.81K USD`) chỉ trong 24 giờ.
      + Hạ nhiệt (Thứ Bảy - Chủ Nhật, 25-26/11): Giữ nhiệt ở mức **`19K USD`** và **`14K USD`** nhờ hiệu ứng kéo dài Cyber Weekend.
    - *Giới hạn dữ liệu:* Do dữ liệu Olist bị giới hạn (từ tháng 09/2016 đến tháng 10/2018), tháng 11/2017 là sự kiện Black Friday duy nhất có dữ liệu hoàn chỉnh (tháng 11/2016 dữ liệu quá sơ khai, tháng 11/2018 dữ liệu đã bị ngắt). Đây là điểm dữ liệu đơn lẻ (single data point) nên chưa thể khẳng định đây là "xu hướng chu kỳ lặp lại hàng năm" dưới góc độ thống kê chặt chẽ, dù nó phản ánh sức bật doanh thu cực tốt của sự kiện đối với Olist.
*   **Sự thay đổi ngành hàng theo mùa (Seasonal Shifts):** Cơ cấu ngành hàng thay đổi rất rõ rệt khi có các sự kiện văn hóa/thể thao hoặc lễ hội:
    *   *Ví dụ 1 (Mùa Giáng Sinh - 11/2017):* Danh mục **Đồng hồ & Quà tặng (watches_gifts)** vọt lên vị trí số 1 (`30K USD`) và **Đồ chơi (toys)** vọt lên vị trí số 5 (`20K USD`) thay thế cho nhóm Sức khỏe làm đẹp thường ngày.
    *   *Ví dụ 2 (Kỳ World Cup - Tháng 6-7/2018):* Đây là minh chứng hoàn hảo về hành vi mua sắm bộc phát (Impulse Buying) theo sự kiện quốc gia. Khi so sánh số liệu toàn sàn (All) với riêng ngành hàng **Thể thao & Dã ngoại (sports_leisure)** trong giai đoạn diễn ra World Cup (01/06/2018 - 31/07/2018):
        - *Về doanh số:* Ngành hàng Sports đạt **`26.52K USD`** doanh thu (chiếm 5.8% tổng doanh thu **`458.68K USD`** của toàn sàn) với **`790 đơn hàng`** (chiếm 6.6% tổng số đơn **`12K`** của toàn sàn).
        - *Về giá trị đơn hàng (AOV):* AOV của riêng nhóm Sports giảm xuống chỉ còn **`33.57 USD`**, thấp hơn **9.4%** so với AOV trung bình toàn sàn cùng kỳ (**`37.06 USD`**). Điều này chứng minh khách hàng tập trung mua sắm các sản phẩm cổ vũ nhỏ lẻ, giá trị thấp (như cờ, áo thun cổ vũ...) thay vì các dụng cụ thể thao đắt tiền. Sản phẩm bán chạy nhất là mã sản phẩm thể thao `dd113cb02b2af9c8e5787e8f1f0722f6` đạt **`1,085.42 USD`**.
        - *Về giữ chân (Retention):* Tỷ lệ mua lại trọn đời của nhóm khách mua Sports chỉ đạt **`2.53%`** (thấp hơn nhiều mức trung bình **`3.86%`** toàn sàn), và tỷ lệ mua lại ngắn hạn 90 ngày giảm xuống chỉ còn **`0.25%`** (so với trung bình **`0.58%`** toàn sàn). Điều này chứng minh hành vi mua sắm hàng cổ vũ World Cup mang tính chất nhất thời, cơ hội và khách hàng không có nhu cầu quay lại mua sắm sau khi giải đấu kết thúc.



### 6.4. Tối Ưu Hóa Thiết Kế Mô Hình Dữ Liệu (Góc Nhìn Data Engineer)
*   **Push-down FX Conversion:** Tính toán quy đổi tỷ giá sang USD ngay từ tầng dbt giúp Power BI chỉ cần thực hiện hàm `SUM` đơn giản, giúp Dashboard tải nhanh tức thì (sub-second).
*   **Late-Arriving Fallback (`pending_refresh`):** Gán khóa tạm thời cho khách hàng trễ giúp pipeline Fact chạy mượt mà 3 lần/ngày mà không bị lỗi ràng buộc dữ liệu, đồng thời DAX tự động lọc bỏ khóa này để giữ sạch số lượng khách hàng hoạt động trên báo cáo.
*   **Star Schema độc lập:** Tách riêng `fact_order_items` và `fact_order_payments` liên kết qua Dimension chung để tránh phình dòng (Fan-out) và triệt tiêu lỗi tham chiếu vòng (Circular Dependency).

