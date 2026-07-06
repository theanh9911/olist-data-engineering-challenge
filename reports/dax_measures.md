# DAX Measures — Olist Sales Dashboard

Tài liệu này chứa toàn bộ các công thức DAX chuẩn đã được hiệu chỉnh theo đúng tên bảng vật lý thực tế trong Power BI của bạn (tiền tố `public_core`).

---

## 1. Doanh thu gốc (Total Revenue USD)
*   **Mô tả:** Tổng doanh thu dựa trên tiền hàng (loại trừ phí vận chuyển) và lọc bỏ các đơn hàng bị hủy (`canceled`) hoặc không khả dụng (`unavailable`).
*   **Định dạng:** Currency (`$ Decimal number`)

```dax
Total Revenue USD = 
CALCULATE(
    SUM('public_core fact_order_items'[price_usd]),
    'public_core fact_order_items'[order_status] <> "canceled" && 
    'public_core fact_order_items'[order_status] <> "unavailable"
)
```

---

## 2. Doanh thu lũy kế trong tháng (MTD Revenue USD)
*   **Mô tả:** Doanh thu tích lũy từ đầu tháng đến ngày hiện tại (Month-to-Date).
*   **Định dạng:** Currency (`$ Decimal number`)

```dax
MTD Revenue USD = 
TOTALMTD(
    [Total Revenue USD],
    'public_core dim_date'[date_day]
)
```

---

## 3. Tổng số khách hàng thực tế (Total Customers)
*   **Mô tả:** Đếm số lượng khách hàng duy nhất (loại bỏ các bản ghi đơn hàng chờ đồng bộ mang mã `'pending_refresh'`).
*   **Định dạng:** Whole number (`1,234`)

```dax
Total Customers = 
CALCULATE(
    DISTINCTCOUNT('public_core fact_order_items'[customer_unique_id]),
    'public_core fact_order_items'[customer_unique_id] <> "pending_refresh",
    'public_core fact_order_items'[order_status] <> "canceled" && 
    'public_core fact_order_items'[order_status] <> "unavailable"
)
```

---

## 4. Tỷ lệ khách mua lại trọn đời (Repeat Buyer Rate)
*   **Mô tả:** Tỷ lệ phần trăm khách hàng có giao dịch trong kỳ đã từng mua hàng từ 2 lần trở lên trong lịch sử trọn đời (lifetime).
*   **Định dạng:** Percentage (`%`)

```dax
Repeat Buyer Rate = 
VAR ActiveCustomers = VALUES('public_core fact_order_items'[customer_unique_id])
VAR CustomerOrderCounts = 
    ADDCOLUMNS(
        ActiveCustomers,
        "OrderCount", 
            CALCULATE(
                DISTINCTCOUNT('public_core fact_order_items'[order_id]), 
                ALL('public_core dim_date'), -- Loại bỏ bộ lọc ngày để tính đơn trọn đời
                'public_core fact_order_items'[order_status] <> "canceled" && 
                'public_core fact_order_items'[order_status] <> "unavailable"
            )
    )
VAR CustomersWithMultipleOrders = 
    FILTER(
        CustomerOrderCounts,
        [customer_unique_id] <> "pending_refresh" && 
        [customer_unique_id] <> BLANK() && 
        [OrderCount] >= 2
    )
VAR TotalRealCustomers = 
    FILTER(
        CustomerOrderCounts,
        [customer_unique_id] <> "pending_refresh" && 
        [customer_unique_id] <> BLANK()
    )
VAR RepeatBuyersCount = COUNTROWS(CustomersWithMultipleOrders)
VAR TotalCustomersCount = COUNTROWS(TotalRealCustomers)
RETURN
    DIVIDE(RepeatBuyersCount, TotalCustomersCount, 0)
```

---

## 5. Tỷ lệ quay lại mua hàng trong 90 ngày (90-Day Repeat Rate)
*   **Mô tả:** Tỷ lệ phần trăm khách hàng trong kỳ có khoảng cách giữa hai đơn hàng liên tiếp tối đa là 90 ngày trong lịch sử trọn đời (lifetime).
*   **Định dạng:** Percentage (`%`)

```dax
90-Day Repeat Rate = 
VAR ActiveCustomers = 
    FILTER(
        VALUES('public_core fact_order_items'[customer_unique_id]),
        [customer_unique_id] <> "pending_refresh" && 
        [customer_unique_id] <> BLANK()
    )
VAR CustomersWith90DayRepeat = 
    FILTER(
        ActiveCustomers,
        VAR CurrentCustomer = [customer_unique_id]
        VAR OrderDates = 
            CALCULATETABLE(
                VALUES('public_core fact_order_items'[purchase_date]),
                'public_core fact_order_items'[customer_unique_id] = CurrentCustomer,
                ALL('public_core dim_date'), -- Loại bỏ bộ lọc ngày để lấy các mốc mua lịch sử
                'public_core fact_order_items'[order_status] <> "canceled" && 
                'public_core fact_order_items'[order_status] <> "unavailable"
            )
        VAR HasRepeat = 
            SUMX(
                OrderDates,
                VAR CurrentDate = [purchase_date]
                VAR PreviousDate = 
                    MAXX(
                        FILTER(OrderDates, [purchase_date] < CurrentDate),
                        [purchase_date]
                    )
                RETURN
                    IF(NOT ISBLANK(PreviousDate) && (CurrentDate - PreviousDate) <= 90, 1, 0)
            )
        RETURN
            HasRepeat > 0
    )
VAR TotalCustomersCount = COUNTROWS(ActiveCustomers)
VAR RepeatBuyersCount = COUNTROWS(CustomersWith90DayRepeat)
RETURN
    DIVIDE(RepeatBuyersCount, TotalCustomersCount, 0)
```

---

## 6. Các Thước Đo Nâng Cao (Advanced E-Commerce Metrics)

### 🔹 Tổng số đơn hàng thành công (Total Orders)
*   **Mô tả:** Đếm số lượng mã đơn hàng duy nhất, loại bỏ đơn hàng bị hủy hoặc không khả dụng.
*   **Định dạng:** Whole number (`1,234`)

```dax
Total Orders = 
CALCULATE(
    DISTINCTCOUNT('public_core fact_order_items'[order_id]),
    'public_core fact_order_items'[order_status] <> "canceled" && 
    'public_core fact_order_items'[order_status] <> "unavailable"
)
```

### 🔹 Giá trị đơn hàng trung bình (AOV - Average Order Value)
*   **Mô tả:** Giá trị trung bình của mỗi đơn hàng bán ra (USD).
*   **Định dạng:** Currency (`$ Decimal number`)

```dax
Average Order Value USD = 
DIVIDE(
    [Total Revenue USD],
    [Total Orders],
    0
)
```

### 🔹 Tổng tiền thanh toán (Total Payments USD)
*   **Mô tả:** Tổng số tiền khách hàng đã thanh toán (dùng cho biểu đồ cơ cấu phương thức thanh toán).
*   **Định dạng:** Currency (`$ Decimal number`)

```dax
Total Payments USD = 
SUM('public_core fact_order_payments'[payment_value_usd])
```

