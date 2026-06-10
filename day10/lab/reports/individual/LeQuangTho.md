# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Lê Quang Thọ  
**Mã số sinh viên:** 2A202600597  
**Vai trò:** Embed & Idempotency Owner  
**Ngày nộp:** 2026-06-10  

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**
- [etl_pipeline.py](day10/lab/etl_pipeline.py): Tôi chịu trách nhiệm chính về hàm `cmd_embed_internal`, nơi thực hiện nạp dữ liệu từ CSV đã làm sạch vào ChromaDB.
- [eval_retrieval.py](day10/lab/eval_retrieval.py): Tôi thiết kế và chạy script đánh giá để so sánh hiệu năng truy xuất (retrieval) giữa các kịch bản dữ liệu "bẩn" và "sạch".

**Kết nối với thành viên khác:**
Tôi làm việc chặt chẽ với **Nguyen Van Sang** (Ingestion Owner) để đảm bảo `run_id` và `chunk_id` được truyền nhất quán từ file manifest vào metadata của Vector Store. Tôi cũng cung cấp kết quả từ file `before_after_eval.csv` cho đội Docs để hoàn thiện báo cáo chất lượng.

**Bằng chứng (commit / comment trong code):**
Trong `etl_pipeline.py`, tôi đã triển khai logic `col.upsert` và đặc biệt là đoạn code `col.delete(ids=drop)` để thực hiện chiến lược "Publish Boundary Pruning", đảm bảo xóa sạch các vector lỗi thời.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Quyết định kỹ thuật quan trọng nhất của tôi là áp dụng chiến lược **"Publish Boundary Pruning"** thay vì chỉ đơn thuần là nạp thêm dữ liệu (Append-only). 

Trong thực tế, khi một tài liệu bị xóa hoặc thay đổi nội dung (ví dụ: đổi từ 14 ngày hoàn tiền sang 7 ngày), nếu chúng ta chỉ dùng `upsert`, những vector cũ có `chunk_id` không đổi sẽ được cập nhật, nhưng những vector "rác" (do thay đổi cấu trúc chunking hoặc tài liệu bị gỡ bỏ hoàn toàn) vẫn sẽ tồn tại trong database. Điều này tạo ra các "mồi bẩn" khiến RAG retrieval trả về kết quả sai lệch. 

Bằng cách so sánh tập hợp `chunk_id` hiện tại trong collection với tập hợp `chunk_id` mới nạp vào, tôi thực hiện lệnh xóa (`delete`) các ID không còn xuất hiện. Điều này biến Vector Store thành một "Index Snapshot" sạch hoàn toàn sau mỗi lượt chạy pipeline, đảm bảo tính **Idempotency** (chạy lại nhiều lần vẫn cho kết quả nhất quán).

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Trong quá trình chạy Sprint 3 (Inject Corruption), tôi đã phát hiện một hiện tượng bất thường: mặc dù đã chạy pipeline mới với dữ liệu sạch, kết quả truy vấn câu hỏi `q_refund_window` vẫn đôi khi trả về thông tin cũ "14 ngày làm việc".

**Triệu chứng:** Kết quả `eval_retrieval.py` báo `hits_forbidden=yes` mặc dù `cleaned_run-standard.csv` đã chứa thông tin 7 ngày.

**Nguyên nhân:** Qua kiểm tra log `embed_upsert`, tôi nhận ra rằng nếu không xóa các vector cũ, ChromaDB sẽ giữ lại cả hai phiên bản nếu `chunk_id` bị thay đổi (do nội dung text thay đổi làm thay đổi giá trị hash trong ID). Hệ thống lấy Top-3 kết quả nên cả thông tin cũ và mới đều lọt vào context.

**Cách xử lý:** Tôi đã bổ sung logic `embed_prune_removed` vào hàm `cmd_embed_internal`. Sau khi áp dụng, log ghi nhận `embed_prune_removed=2` (xóa 2 vector cũ lạc hậu). Kết quả eval sau đó chuyển ngay sang `hits_forbidden=no`, xác nhận lỗi đã được triệt tiêu hoàn toàn.

---

## 4. Bằng chứng trước / sau (80–120 từ)

Dưới đây là bằng chứng từ tệp `before_after_eval.csv` (với `run_id=run-standard`):

**Trước (kịch bản inject lỗi - corrupted run):**
```csv
q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,Yêu cầu hoàn tiền được chấp nhận trong vòng 14 ngày...,yes,yes,,3
```
*(Kết quả: Lấy trúng chunk bẩn 14 ngày, `hits_forbidden=yes`)*

**Sau (kịch bản chuẩn - standard run + pruning):**
```csv
q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền...,policy_refund_v4,Yêu cầu được gửi trong vòng 7 ngày làm việc...,yes,no,,3
```
*(Kết quả: Chỉ lấy chunk sạch 7 ngày, `hits_forbidden=no`, `contains_expected=yes`)*

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ tích hợp **Dynamic Metadata Filtering** vào script đánh giá. Hiện tại chúng ta mới chỉ đánh giá trên toàn bộ collection; việc lọc theo `run_id` hoặc `effective_date` ngay trong câu lệnh `col.query` sẽ giúp kiểm tra xem hệ thống có khả năng đa phiên bản (Multi-versioning) mà không cần xóa vật lý dữ liệu cũ hay không.
