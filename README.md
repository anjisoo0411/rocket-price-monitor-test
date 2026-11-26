# Rocket Price Monitor 0.7.1

Manual investigation tool for comparing daily Coupang crawl exports with EXCCI's own product prices exported from seller centers where the user has access. Seller CSV records are streamed and saved in bounded batches by a background job, with progress shown in the page.

## Daily workflow

1. Sign in with the administrator token.
2. Upload each raw `.xlsx` or `.csv` crawl export. The date is read from a filename containing `YYYYMMDD`, or can be supplied in the form.
3. Select two saved batches and compare them. The results show separate counts for price changes and inventory/sold-out changes. Filter to price changes, inventory/sold-out changes, or all changes, then search by SKU, product name, barcode, or option ID.
4. Export the product list from each authorized seller center as XLSX or CSV and upload it with the seller-center name (for example, `스마트스토어`). The newest upload for each source is used as its current price list.
5. Compare batches. Price-changed Coupang products show different-priced own-store listings matched by exact barcode first, then conservative product-name overlap. Each result includes seller center, listing title, price difference, product URL, and match evidence. Only a successfully completed seller upload is used; a failed upload leaves the previous completed list active.

Seller-center listings are possible context only; the application never labels them as proven causes. It reads only user-provided seller-center exports. It does not sign in to SCMs, scrape listings, or bypass access controls.

## Crawl file format

Required columns: `옵션ID`, `노출ID`, `아이템ID`, `판매가`, `상품명`.

Optional columns: `재고량`, `품절 여부`, `평점`, `리뷰개수`, `판매자 ID`, `카테고리 ID`.

The supplied crawler's 11-column XLSX export is supported. Option ID uniquely identifies a row within a batch. Duplicate IDs and duplicate dates are rejected. Comparison reports options missing from either date. Product-master matching uses `products.option_id` and does not require replacing the master workbook.

Coupang URLs are generated as:

```text
https://www.coupang.com/vp/products/{노출ID}?vendorItemId={옵션ID}
```

## Data preservation

New crawl-batch, legacy candidate, and seller-center tables are created additively at startup. Existing product rows, price snapshots, and the 9,583-item product master are retained. Crawl batches are immutable by date; a duplicate date is rejected instead of replacing stored data.

Seller-center price exports are stored in separate `seller_offer_batches` and `seller_offers` tables. Each upload is retained. For comparison, the latest uploaded file per seller-center name represents its current price list. Required columns are product name and sale price. A barcode or seller product code improves matching; product title overlap is shown as weaker evidence.

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
- `POST /api/naver-candidates` – legacy endpoint retained for compatibility
- `POST /api/seller-batches` – upload an authorized seller-center XLSX/CSV export (`source` form field plus `file`)
- `GET /api/seller-batches/status/{job_id}` – check seller upload progress and result
- `GET /api/seller-batches` – list latest price lists by seller center
- `GET /api/summary` – product and snapshot summary

All application APIs except `/api/health` require `Authorization: Bearer <ADMIN_TOKEN>`.
