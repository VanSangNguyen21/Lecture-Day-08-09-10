# Data Contract — Lab Day 10

Đây là tài liệu đặc tả Data Contract cho bộ dữ liệu `kb_chunk_export` phục vụ hệ thống IT & CS Support Agent.

---

## 1. Nguồn dữ liệu (Source Map)

| Nguồn | Phương thức Ingest | Failure Mode chính | Metric / Alert |
|-------|-------------------|-------------------|----------------|
| **Jira IT Support / PDF Source** | Batch File Reader | Định dạng tệp tin không hợp lệ, hỏng font, thiếu ngày hiệu lực. | `missing_effective_date`, `invalid_effective_date_format` (Alert qua email/slack) |
| **HR Portal DB** | DB Extraction Script | Xung đột phiên bản chính sách cũ (10 ngày phép) và mới (12 ngày phép). | `stale_hr_policy_effective_date` (Quarantine count > 0 -> Warn) |
| **CS Billing Portal API** | REST API Call | Cửa sổ hoàn tiền bị cũ (stale 14 ngày thay vì 7 ngày của v4). | `refund_no_stale_14d_window` (Halt ngay lập tức nếu lọt vào cleaned) |

---

## 2. Schema Cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú / Ràng buộc |
|-----|------|----------|-------------------|
| **chunk_id** | string | Có | Định dạng: `{doc_id}_{seq}_{hash}`. Độ dài 16 ký tự băm. |
| **doc_id** | string | Có | Phải thuộc Allowlist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`. |
| **chunk_text** | string | Có | Độ dài tối thiểu 8 ký tự. Được chuẩn hóa khoảng trắng và ẩn thông tin nhạy cảm (PII). |
| **effective_date** | date | Có | Định dạng YYYY-MM-DD. Không được lớn hơn `2027-12-31`. |
| **exported_at** | datetime | Có | Định dạng ISO 8601 đầy đủ (nạp qua Pydantic validation). |

---

## 3. Quy tắc Quarantine vs Drop

- **Quarantine (Cô lập):**
  - Mọi bản ghi vi phạm cấu trúc hoặc nghiệp vụ (lỗi kiểu dữ liệu, sai format ngày, doc_id không nằm trong allowlist, text trống) sẽ được chuyển vào thư mục `artifacts/quarantine/` dưới dạng CSV để kiểm toán thủ công.
  - Các bản ghi trùng lặp nội dung (`duplicate_chunk_text`) được cô lập để giữ tính duy nhất cho vector store.
  - Các bản ghi không khớp nội dung với nhãn tài liệu (`refund_policy_content_mismatch`, `sla_policy_content_mismatch`) sẽ bị cô lập.
- **Drop (Bỏ qua):**
  - Không âm thầm drop dữ liệu nghiệp vụ quan trọng. Mọi lỗi đều có lineage và lý do cụ thể trong cột `reason` của file quarantine.
- **Approval:** Các bản ghi trong quarantine muốn nạp lại phải được sửa đổi trực tiếp ở tệp nguồn hoặc phê duyệt bởi **Data Owner** (`AI-IT-Support-Team`).

---

## 4. Phiên bản & Canonical

- **Policy Refund:**
  - Source of Truth: `data/docs/policy_refund_v4.txt` (Phiên bản 4, hiệu lực từ `2026-02-01`).
  - Cửa sổ hoàn tiền chuẩn: **7 ngày làm việc**. Mọi bản ghi chứa "14 ngày làm việc" (lỗi migration từ v3) sẽ được tự động sửa đổi hoặc bị halt nếu không sửa được.
- **HR Leave Policy:**
  - Source of Truth: `data/docs/hr_leave_policy.txt` (Hiệu lực từ `2026-01-01`).
  - Phiên bản mới: **12 ngày phép** cho nhân viên dưới 3 năm kinh nghiệm.
  - Phiên bản cũ (2025): **10 ngày phép** (bị lọc bỏ thông qua quy tắc lọc ngày hiệu lực động dựa trên `hr_leave_min_effective_date` trong `data_contract.yaml`).
