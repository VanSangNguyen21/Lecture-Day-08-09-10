# Quality Report — Lab Day 10 (Nhóm)

**run_id:** `run-standard`  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (Corrupted Run) | Sau (Standard Run) | Ghi chú |
|--------|-------|-----|---------|
| **raw_records** | 10 | 10 | Tổng số dòng xuất nguồn |
| **cleaned_records** | 6 | 6 | Số bản ghi sạch được chèn vào DB |
| **quarantine_records** | 4 | 4 | Số bản ghi bẩn bị cô lập |
| **Expectation halt?** | FAIL (Halt skipped) | PASS (No halt) | Trạng thái dừng của suite |

---

## 2. Before / After Retrieval

### Câu hỏi then chốt: Refund window (`q_refund_window`)
- **Trước (Corrupted Run - Không sửa lỗi refund):**
  - `contains_expected`: **yes**
  - `hits_forbidden`: **yes** (Lỗi nghiêm trọng: chatbot lấy được cả chunk chứa thông tin cũ *"14 ngày làm việc"*)
  - **Preview:** *"Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày làm việc kể từ xác nhận đơn (ghi chú: bản sync cũ policy-v3 — lỗi migration)."*
- **Sau (Standard Run - Có sửa lỗi refund):**
  - `contains_expected`: **yes**
  - `hits_forbidden`: **no** (Thành công: thông tin cũ 14 ngày đã được chuẩn hóa hoặc prune hoàn toàn)
  - **Preview:** *"Yêu cầu hoàn tiền được chấp nhận trong vòng 7 ngày làm việc kể từ xác nhận đơn (ghi chú: bản sync cũ policy-v3 — lỗi migration). [cleaned: stale_refund_window]"*

### Merit: Versioning HR — nghỉ phép năm (`q_leave_version`)
- **Trước (Corrupted/Stale Index):**
  - `contains_expected`: **yes**
  - `hits_forbidden`: **yes** (Chatbot lấy ra bản ghi cũ năm 2025: *"được 10 ngày phép năm"*)
- **Sau (Standard Run - Lọc theo ngày hiệu lực động):**
  - `contains_expected`: **yes**
  - `hits_forbidden`: **no** (Không chứa mồi cũ 10 ngày phép năm)
  - `top1_doc_expected`: **yes** (Lấy đúng bản ghi từ `hr_leave_policy` quy định 12 ngày phép)
  - **Preview:** *"Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026."*

---

## 3. Freshness & Monitor

- Kết quả `freshness_check` trả về **FAIL** với chi tiết: `{"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 1464.5, "sla_hours": 24.0}`.
- **Giải thích:** Đây là kết quả đúng mong đợi vì tệp CSV xuất bản nguồn mẫu (`policy_export_dirty.csv`) có watermark xuất từ ngày `2026-04-10`, so với clock hiện tại đã quá thời hạn SLA 24 giờ. Trong thực tế, sự cố này sẽ kích hoạt alert cảnh báo dữ liệu cũ để đội vận hành kiểm tra Ingestion.

---

## 4. Corruption Inject (Sprint 3)

- **Cách thực hiện:** Chạy pipeline với các cờ đặc biệt:
  ```bash
  python etl_pipeline.py run --run-id run-corrupted --no-refund-fix --skip-validate
  ```
- **Hành vi phát hiện:**
  - `expectation[refund_no_stale_14d_window]` lập tức chuyển sang **FAIL (halt)**.
  - Tuy nhiên, do có cờ `--skip-validate`, pipeline không thoát dừng mà vẫn tiến hành nạp (embed) dữ liệu lỗi vào database.
  - Khi chạy `eval_retrieval.py`, cột `hits_forbidden` của câu hỏi `q_refund_window` chuyển sang **yes**, làm lộ rõ lỗ hổng dữ liệu bẩn lọt vào production.

---

## 5. Hạn chế & việc chưa làm

- Hiện tại pipeline mới chỉ chạy bằng tay thông qua CLI. Cần tích hợp công cụ lập lịch (Scheduler) như Airflow hoặc Prefect để tự động hóa hoàn toàn luồng.
- Bộ câu hỏi kiểm tra retrieval (`test_questions.json`) còn khá mỏng (4 câu). Cần mở rộng bộ test suite lên ít nhất 15-20 câu để bao phủ nhiều góc tối của RAG.
