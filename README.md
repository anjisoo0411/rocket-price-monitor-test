# Rocket Price Monitor 0.5.1

Manual investigation tool for comparing daily Coupang crawl exports and reviewing possible Naver Shopping candidates.

## Daily workflow

1. Sign in with the administrator token.
2. Upload each raw `.xlsx` or `.csv` crawl export. The date is read from a filename containing `YYYYMMDD`, or can be supplied in the form.
3. Select two saved batches and compare them. Only options with a changed price, stock quantity, or sold-out state are shown.
4. Open the Naver Shopping search link for a changed product. Review results manually and optionally save candidate product name, price, seller, URL, and evidence.

Candidate products are possible context only; the application never labels them as proven causes. It does not scrape Naver or assume the retired Naver Shopping Search API is available.

## Crawl file format

Required columns: `옵션ID`, `노출ID`, `아이템ID`, `판매가`, `상품명`.

Optional columns: `재고량`, `품절 여부`, `평점`, `리뷰개수`, `판매자 ID`, `카테고리 ID`.

The supplied crawler's 11-column XLSX export is supported. Option ID uniquely identifies a row within a batch. Duplicate IDs and duplicate dates are rejected. Comparison reports options missing from either date. Product-master matching uses `products.option_id` and does not require replacing the master workbook.

Coupang URLs are generated as:

```text
https://www.coupang.com/vp/products/{노출ID}?vendorItemId={옵션ID}
```

## Data preservation

New batch and Naver-candidate tables are created additively at startup. Existing product rows, price snapshots, and the 9,583-item product master are retained. Crawl batches are immutable by date; a duplicate date is rejected instead of replacing stored data.

## Run locally

Install dependencies from `requirements.txt`, then run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Set `ADMIN_TOKEN`, `APP_SECRET`, and `DATABASE_URL` for the environment. No Coupang seller API credentials are used or requested.

## API

- `POST /api/crawl-batches` – upload a dated XLSX/CSV batch
- `GET /api/crawl-batches` – list batches
- `GET /api/crawl-batches/compare?previous_id=…&current_id=…` – compare two complete batches
- `POST /api/naver-candidates` – save a manual candidate review
- `GET /api/summary` – product and snapshot summary

All application APIs except `/api/health` require `Authorization: Bearer <ADMIN_TOKEN>`.
