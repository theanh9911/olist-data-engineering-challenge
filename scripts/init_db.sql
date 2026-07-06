-- ============================================================
-- Init script: Tạo schemas cho Data Warehouse
-- Chạy tự động khi PostgreSQL container khởi tạo lần đầu
-- ============================================================

-- Schema cho dữ liệu thô (Bronze layer)
CREATE SCHEMA IF NOT EXISTS raw;

-- Schema cho dbt staging models (Silver layer)
CREATE SCHEMA IF NOT EXISTS staging;

-- Schema cho dbt core models — Star Schema (Gold layer)
CREATE SCHEMA IF NOT EXISTS core;

-- Schema cho dbt snapshots (SCD Type 2)
CREATE SCHEMA IF NOT EXISTS snapshots;
