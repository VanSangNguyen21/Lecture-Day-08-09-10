# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** AI-IT-Support-Team  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Nguyen Van Sang | Ingestion, Cleaning & Quality Owner | sang.nv@company.internal |
| Le Quang Tho | Embed, Idempotency, Monitoring & Docs Owner | tho.lq@company.internal |

**Ngày nộp:** 2026-06-10  
**Repo:** https://github.com/VanSangNguyen21/Lecture-Day-08-09-10.git  

---

## 1. Pipeline tổng quan

Hệ thống tri thức CS & IT Helpdesk đòi hỏi dữ liệu nạp vào Vector Store phải tuyệt đối chính xác và cập nhật. Pipeline ETL của chúng tôi thiết lập một quy trình Ingest → Clean → Validate → Embed khép kín, hoạt động theo lô (batch processing) trên tệp nguồn CSV xuất thô từ cơ sở dữ liệu.

**Chuỗi lệnh chạy End-to-End:**
```bash
# Setup môi trường và cài đặt thư viện
pip install -r requirements.txt
cp .env.example .env

# Chạy pipeline chuẩn (sửa lỗi 14->7 ngày, validate nghiêm ngặt, embed)
python etl_pipeline.py run --run-id run-standard

# Kiểm tra độ tươi (freshness SLA) dựa trên manifest vừa sinh ra
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_run-standard.json

# Đánh giá hiệu năng truy xuất tri thức (RAG retrieval)
python eval_retrieval.py --out artifacts/eval/before_after_eval.csv
```

Mỗi lượt chạy pipeline được gắn một `run_id` duy nhất (ví dụ: `run-standard`), giúp theo vết toàn bộ lịch sử (lineage) của dữ liệu. `run_id` này xuất hiện trong file log (`artifacts/logs/`), tệp dữ liệu sạch (`artifacts/cleaned/`), dữ liệu cô lập (`artifacts/quarantine/`), và tệp manifest (`artifacts/manifests/`).

---

## 2. Cleaning & expectation

Chúng tôi đã mở rộng bộ quy tắc làm sạch (cleaning rules) và bộ kiểm tra chất lượng (expectations) vượt xa baseline nhằm bảo vệ cơ sở tri thức khỏi các nguồn dữ liệu bẩn lọt vào.

### 2a. Bảng metric_impact (bắt buộc)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| **Rule: Dynamic HR Cutoff** | Đọc cứng ngày | Lọc động bản HR 2025 (`effective_date < cutoff`) | `stale_hr_policy_effective_date` trong `quarantine_run-standard.csv` |
| **Rule: PII Masking** | Lộ email/sđt nhạy cảm | Tự động che giấu thành `[MASKED_EMAIL]`, `[MASKED_PHONE]` | Chứa `[MASKED_EMAIL]` trong `cleaned_run-standard.csv` |
| **Rule: Content Integrity** | Nạp nhầm doc bẩn | Cô lập 100% bản ghi không đúng chủ đề tài liệu | `quarantine_records=4` trong manifest của standard run |
| **Expectation: E7 (No unmasked emails)** | 0 vi phạm | 1 vi phạm (cảnh báo) khi inject email ngoài | Log output của `expectation[no_unmasked_external_emails]` |
| **Expectation: E8 (No future date)** | 0 vi phạm | Halt pipeline nếu `effective_date > 2027-12-31` | Log output của `expectation[no_future_effective_date]` |

### Quy tắc Halt vs Warn trong Validation:
- **Halt (Dừng khẩn cấp):** Áp dụng cho các lỗi nghiêm trọng ảnh hưởng trực tiếp đến nghiệp vụ trả lời (như thiếu cột `doc_id`, ngày hiệu lực sai format hoặc nằm trong tương lai xa, hoặc còn tồn tại chính sách hoàn tiền 14 ngày). Khi vi phạm, pipeline lập tức thoát với mã lỗi 2, chặn đứng quá trình embed.
- **Warn (Cảnh báo):** Áp dụng cho lỗi định dạng nhỏ (như chunk quá ngắn < 8 ký tự, hoặc chứa email chưa được che giấu). Pipeline vẫn tiếp tục chạy nhưng ghi nhận cảnh báo vào log hệ thống để kiểm tra thủ công.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent

Chúng tôi đã thiết kế kịch bản kiểm thử chất lượng RAG bằng cách cố tình làm hỏng dữ liệu (Inject Corruption) ở Sprint 3:

**Kịch bản inject:**
Chạy pipeline với các cờ bỏ qua sửa đổi hoàn tiền và tắt tính năng dừng validation:
```bash
python etl_pipeline.py run --run-id run-corrupted --no-refund-fix --skip-validate
```

**Kết quả định lượng (từ CSV eval):**
- **Trước (Index lỗi thời/bẩn):** Khi truy vấn câu hỏi `q_refund_window` ("Khách hàng có bao nhiêu ngày để hoàn tiền..."), ChromaDB trả về chunk chứa văn bản *"14 ngày làm việc"* (dẫn đến `hits_forbidden=yes`). Điều này khiến Chatbot trả lời sai thông tin nghiệp vụ và làm hỏng trải nghiệm khách hàng.
- **Sau (Standard Run - Đã được làm sạch):** Sau khi chạy lại pipeline chuẩn, hệ thống tự động sửa *"14 ngày làm việc"* thành *"7 ngày làm việc"* và tiến hành **prune (xóa bỏ)** các vector cũ khỏi database. Kết quả chạy eval trả về `hits_forbidden=no` và `contains_expected=yes`. Chatbot phục vụ chính xác thông tin 7 ngày.
- **Đánh giá leave policy (`q_leave_version`):** Nhờ quy tắc dynamic cutoff, bản ghi phép năm cũ 10 ngày (2025) đã bị loại bỏ ngay từ layer transform, giúp chatbot trả về đúng 12 ngày phép (chính sách 2026) mà không bị nhiễu thông tin cũ.

---

## 4. Freshness & monitoring

Chúng tôi áp dụng mức SLA freshness là **24 giờ** kể từ thời điểm dữ liệu được xuất khỏi hệ thống nguồn (`latest_exported_at`). 
- **PASS:** Dữ liệu mới cập nhật dưới 24h, hệ thống sẵn sàng phục vụ.
- **WARN:** Dữ liệu trễ từ 24h - 48h, gửi cảnh báo lên Slack `#incident-p1-alerts` để nhắc nhở đội ngũ vận hành.
- **FAIL:** Dữ liệu quá 48h chưa được làm mới, đánh dấu đỏ cảnh báo khẩn cấp vì chatbot có nguy cơ trả lời thông tin cũ.

---

## 5. Liên hệ Day 09

Dữ liệu sau embed được đồng bộ trực tiếp vào Chroma collection `day10_kb`. Đây là collection canonical được chia sẻ cho các Retriever worker trong hệ thống Multi-agent của Day 09. Nhờ sự tách biệt này, tầng tri thức (data layer) được bảo vệ độc lập, giúp agent luôn có dữ liệu chính xác nhất để trả lời người dùng mà không cần thay đổi prompt hay logic agent.

---

## 7. Peer Review (Đánh giá chéo)

Sau khi trao đổi và kiểm tra chéo với nhóm bạn, chúng tôi ghi nhận các phản hồi sau:
1. **Câu hỏi về Idempotency:** Nhóm bạn đánh giá cao việc chúng tôi triển khai logic `embed_prune_removed`. Việc xóa các vector không còn xuất hiện trong lần chạy hiện tại giúp đảm bảo database luôn khớp 1:1 với file cleaned CSV.
2. **Câu hỏi về Freshness:** Chúng tôi đã giải thích rõ điểm đo freshness nằm ở bước **Publish** (ChromaDB) thông qua việc ghi nhận timestamp trong manifest. Nhóm bạn gợi ý nên thêm alert real-time qua Webhook thay vì chỉ log terminal.
3. **Câu hỏi về Quarantine:** Nhóm bạn đã thử inject một file CSV thiếu cột `effective_date` và xác nhận pipeline đã đẩy đúng vào file quarantine với lý do `missing_effective_date`, không làm dừng pipeline (warn mode) cho các dòng hợp lệ khác.

---

## 8. Kết luận

Dự án đã hoàn thành đầy đủ các mục tiêu của Lab Day 10, từ việc xây dựng pipeline ETL an toàn, triển khai Quality Gate nghiêm ngặt đến việc cung cấp bằng chứng định lượng về sự cải thiện chất lượng tri thức cho Agent. Toàn bộ mã nguồn và artifacts đã được đóng gói sẵn sàng cho việc triển khai thực tế.
