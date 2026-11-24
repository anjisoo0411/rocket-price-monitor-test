# Price provider – 0.4.2

Coupang price-change detection uses the official Open API endpoint `GET /v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/inventories` and stores `data.salePrice` as a consistent change-detection indicator. It is not represented as a verified consumer-facing Rocket Delivery price.

Required Render environment variables: `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`, `COUPANG_VENDOR_ID`. Keys must be newly issued/rotated by the user and must never be entered into chat or committed to source control.

The dashboard first offers a single-item API test, then a five-item test collection, then full on-demand collection. Full collection is sequential and throttled to at most about 3 requests/second (minimum 0.34 seconds between calls). HTTP 401/403/429 immediately stops the job. Each successful result is stored as a Coupang snapshot. Price comparison continues to compare the latest two snapshots per SKU.

Naver Shopping remains a human-opened search link; no automated scraping is implemented.
