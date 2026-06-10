# Runbook — Lab Day 10 (Incident Response Playbook)

Tài liệu hướng dẫn xử lý sự cố chất lượng dữ liệu của hệ thống tri thức IT & CS Support.

---

## Symptom (Triệu chứng)

- **Người dùng / Agent gặp lỗi nghiệp vụ:**
  - Agent trả lời sai cửa sổ hoàn tiền là **14 ngày** thay vì **7 ngày**.
  - Agent hướng dẫn nhân viên mới được nghỉ **10 ngày phép** năm thay vì **12 ngày phép**.
  - Agent không tìm thấy thông tin hướng dẫn SLA xử lý sự cố P1 mới nhất.
  - Người dùng phàn nàn thông tin trả lời bị cũ (stale).

---

## Detection (Phát hiện)

Sự cố được phát hiện thông qua các kênh giám sát sau:
1. **Freshness Alert:** Cron job giám sát báo động đỏ `freshness_check=FAIL` hoặc `reason=freshness_sla_exceeded` trên slack channel `#incident-p1-alerts`.
2. **Pipeline Validation Failure:** Pipeline bị dừng đột ngột với log `PIPELINE_HALT` và mã thoát (exit code) 2 do một hoặc nhiều Expectation mức `halt` bị vi phạm (ví dụ: `refund_no_stale_14d_window` hoặc `no_future_effective_date`).
3. **Retrieval Evaluation Regression:** Kết quả chạy đánh giá định kỳ báo `hits_forbidden=yes` hoặc `top1_doc_matches=false` trên tập câu hỏi golden.

---

## Diagnosis (Chẩn đoán)

Khi nhận được cảnh báo, kỹ sư trực ca thực hiện chẩn đoán theo các bước sau:

| Bước | Hành động | Kết quả mong đợi / Chỉ số cần kiểm tra |
|------|-----------|----------------------------------------|
| **1** | Kiểm tra file manifest mới nhất: `artifacts/manifests/manifest_<run_id>.json` | Xác định `run_id`, kiểm tra xem các chỉ số `raw_records`, `cleaned_records`, `quarantine_records` có gì bất thường không (vd: cleaned_records giảm đột ngột về 0). |
| **2** | Mở tệp cô lập dữ liệu: `artifacts/quarantine/quarantine_<run_id>.csv` | Đọc cột `reason` để xem dữ liệu bị lỗi gì: `stale_hr_policy_effective_date`, `pydantic_schema_validation_failed`, `unknown_doc_id` hay `duplicate_chunk_text`. |
| **3** | Chạy kiểm tra retrieval: `python eval_retrieval.py` | Xem tệp kết quả `artifacts/eval/before_after_eval.csv` xem cột `hits_forbidden` và `top1_doc_expected` để khoanh vùng tài liệu bị lấy sai hoặc chứa mồi cũ. |
| **4** | Kiểm tra nhật ký pipeline: `artifacts/logs/run_<run_id>.log` | Lọc các dòng `expectation[...] FAIL` để biết rule nào chặn pipeline. |

---

## Mitigation (Khắc phục tạm thời)

1. **Khôi phục dữ liệu sạch (Rerun standard pipeline):**
   - Nếu lỗi do chưa áp dụng rule sửa đổi hoặc bỏ qua bước validate trong lúc thử nghiệm, chạy lại luồng chuẩn:
     ```bash
     python etl_pipeline.py run
     ```
   - Điều này sẽ tự động chạy transform, validate, upsert dữ liệu sạch và **prune (xóa)** toàn bộ vector ID lỗi thời khỏi ChromaDB.
2. **Rollback về phiên bản trước (Data Rollback):**
   - Nếu tệp raw xuất nguồn bị lỗi nghiêm trọng không thể sửa ngay, tải lại tệp raw của phiên bản tốt gần nhất và chạy lại pipeline với tệp raw đó để ghi đè vector store.
3. **Treo thông báo bảo trì (UI Alert):**
   - Nếu việc sửa dữ liệu mất hơn 30 phút, bật banner cảnh báo trên chatbot UI: *"Dữ liệu chính sách đang được cập nhật, thông tin phản hồi có thể bị chậm trễ hoặc chưa cập nhật."*

---

## Prevention (Phòng ngừa lâu dài)

1. **Chặn lỗi tại nguồn (Data Contract Enforcement):** Yêu cầu đội ngũ xuất bản tài liệu tuân thủ nghiêm ngặt schema và format ngày tháng trong contract.
2. **Tích hợp CI/CD:** Tự động chạy `grading_run.py` và `eval_retrieval.py` trong quy trình CI trước khi cập nhật dữ liệu lên môi trường Production.
3. **Tối ưu hóa Freshness SLA:** Thiết lập trigger tự động (Sensor) để chạy pipeline ngay khi có file PDF mới xuất hiện trong thư mục chia sẻ thay vì chạy định kỳ (Batch Cron) giúp giảm tuổi của dữ liệu.
