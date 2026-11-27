# 0.7.5

- Prefer the seller export's `할인가` when it contains a positive amount; use `판매가` when the discount value is blank, zero, or not numeric.
- Show the applied price basis (`할인가` or `판매가`) beside each seller candidate price.
- Store the price basis in an additive database column; prior price history and seller batches are preserved. Re-upload the export once after deployment so the current batch reflects discounted prices.
- Includes the URL/product-number fixes and large-file upload handling from 0.7.1–0.7.4.
