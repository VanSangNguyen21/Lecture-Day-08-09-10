# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Văn Sáng  
**Vai trò:** Ingestion & Quality Gate Owner  
**Ngày nộp:** 2026-06-10  

---

## 1. Tôi phụ trách phần nào?

Trong Lab Day 10 này, tôi chịu trách nhiệm chính về phần **Ingestion** và xây dựng **Quality Gate (Pydantic & Expectations)** cho toàn bộ pipeline. 

**Cụ thể các tệp tôi đã chỉnh sửa và thiết kế bao gồm:**
- [etl_pipeline.py](file:///C:/ai_vinuni/code_vinuni/Lecture-Day-08-09-10/day10/lab/etl_pipeline.py): Sửa lỗi hiển thị Unicode trên Windows terminal khi in ký tự arrow và thiết kế các tham số điều hướng.
- [transform/cleaning_rules.py](file:///C:/ai_vinuni/code_vinuni/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py): Tích hợp mô hình Pydantic `CleanedRow` để xác thực dữ liệu chặt chẽ ở layer transform; triển khai rule băm `chunk_id` ổn định; lọc bỏ chính sách nghỉ phép cũ dựa trên ngày hiệu lực động (đọc từ contract).
- [quality/expectations.py](file:///C:/ai_vinuni/code_vinuni/Lecture-Day-08-09-10/day10/lab/quality/expectations.py): Thêm các expectation kiểm tra rò rỉ email cá nhân bên ngoài (`no_unmasked_external_emails`) và phát hiện ngày hiệu lực ở tương lai xa (`no_future_effective_date`).
- [contracts/data_contract.yaml](file:///C:/ai_vinuni/code_vinuni/Lecture-Day-08-09-10/day10/lab/contracts/data_contract.yaml): Điền metadata, cấu hình alert channel và định nghĩa các expectation mới.

Tôi đã làm việc chặt chẽ với các thành viên khác chịu trách nhiệm về embedding để thống nhất cấu trúc đầu ra của cleaned rows khớp với schema của collection ChromaDB.

---

## 2. Một quyết định kỹ thuật

Quyết định kỹ thuật quan trọng nhất của tôi là **tích hợp Pydantic Model (`CleanedRow`) trực tiếp làm chốt chặn (validation gate) trong quá trình biến đổi dữ liệu**. 
Thay vì chỉ dùng các câu lệnh `if-else` thông thường dễ bỏ sót lỗi, Pydantic tự động chuyển đổi kiểu dữ liệu (coercion) một cách an toàn (như chuỗi ngày tháng thành thực thể `date`, ISO string thành `datetime`) đồng thời áp các ràng buộc nghiêm ngặt (như `min_length=8` cho `chunk_text`). 

Nếu bản ghi không thỏa mãn bất kỳ trường nào trong schema, bản ghi đó sẽ bị ném ngoại lệ và lập tức đẩy vào file cô lập `quarantine_<run_id>.csv` kèm chi tiết lỗi (`pydantic_schema_validation_failed`). Quyết định này giúp nâng cao độ tin cậy của dữ liệu nạp vào Vector Store, giảm thiểu rủi ro lỗi runtime ở các layer phía sau.

---

## 3. Một lỗi hoặc anomaly đã xử lý

Khi chạy thử nghiệm pipeline trên hệ điều hành Windows, tôi đã gặp phải lỗi nghiêm trọng **`UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`** dẫn đến crash pipeline và exit code 1.

**Triệu chứng:** Pipeline nạp và làm sạch thành công, nhưng bị crash ở bước log kết quả khi phát hiện validation skip:
```
File "etl_pipeline.py", line 61, in log; print(msg)
UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'
```

**Nguyên nhân:** Ký tự unicode mũi tên (`→`) trong dòng log thông báo bỏ qua validate không được Windows terminal mặc định (cp1252) hỗ trợ mã hóa trực tiếp.

**Cách xử lý:** Tôi đã sửa đổi trực tiếp tệp `etl_pipeline.py` tại dòng 91, thay thế ký tự unicode `→` thành ký tự ASCII `->`. Sau khi sửa đổi, pipeline chạy mượt mà trên môi trường Windows mà không bị ngắt quãng nửa chừng.

---

## 4. Bằng chứng trước / sau

Với `run_id` là `run-standard`, tôi đã chạy thử nghiệm đánh giá retrieval trên bộ câu hỏi golden.

Dưới đây là trích dẫn kết quả từ tệp `before_after_eval.csv` cho thấy hiệu năng truy xuất cải thiện rõ rệt:

**Trước (khi chạy corrupted run - mồi cũ 14 ngày còn trong database):**
```csv
q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày...,yes,yes,,3
```
*(Lỗi: `hits_forbidden=yes` do lấy ra thông tin stale 14 ngày làm việc)*

**Sau (khi chạy standard run - đã sửa lỗi hoàn tiền và prune index):**
```csv
q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,Yêu cầu được gửi trong vòng 7 ngày làm việc...,yes,no,,3
```
*(Thành công: `hits_forbidden=no` và chatbot hướng dẫn đúng 7 ngày làm việc)*

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ viết một script tự động **Data Contract Linter**. Công cụ này sẽ đọc trực tiếp tệp `contracts/data_contract.yaml` để tự động tạo ra lớp Pydantic `CleanedRow` và tệp cấu hình Great Expectations động. Điều này giúp loại bỏ hoàn toàn việc viết mã kiểm thử thủ công và đảm bảo code logic luôn đồng bộ 100% với tài liệu hợp đồng dữ liệu.
