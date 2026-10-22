# Bot Fleet Dashboard

Trang tĩnh phục vụ bởi **GitHub Pages**, dữ liệu được **Python** thu thập trong
**GitHub Actions** (cron mỗi 10 phút) rồi ghi vào `data/`.

## Kiến trúc

```
cron (mỗi 10') ──> Actions: collect.py (Python) ──> data/status.json + data/history.json
                                                  └─> git push ──> Pages deploy
                                                            │
   trình duyệt ──> index.html (fetch data/) ────────────────┘
                 └─> Pyodide (Python 3.11 chạy ngay trong browser)
```

- **Pages chỉ phục vụ file tĩnh** → mọi logic chạy ở bước build/deploy của Actions.
- `collect.py` đọc API GitHub (runs + log job) cho các repo: `jieqi-core`, `the-anh`, `vht`
  rồi trích số claim/transfer/idle/lỗi/dest-id từ log.
- `index.html` có **Python console client-side** (Pyodide/WASM): biến `status` đã nạp sẵn,
  dùng `result = ...` để in kết quả.

## Dùng
- Mở: https://nguyen05566.github.io/bot-dashboard/
- Chạy lại thu thập ngay: Actions → `pages` → Run workflow
- Bấm "Chạy Python" trong trang để tải Pyodide (CDN ~10MB, cache 1 lần)

## Token
Workflow dùng `secrets.GH_PAT` (PAT có scope `repo`) để đọc log của các repo khác.
Nếu thiếu, job collect sẽ báo lỗi auth — cần thêm secret `GH_PAT` trong repo này.
