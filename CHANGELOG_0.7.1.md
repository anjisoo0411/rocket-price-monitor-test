# 0.7.1

- Seller-center CSV imports stream normalized rows and write them in bounded batches rather than keeping multiple full-size row lists in memory.
- Seller uploads are accepted as background jobs; the page polls and displays progress while rows are parsed and saved.
- Incomplete or failed seller batches are excluded from matching, so a failed upload cannot replace the last completed price list.
- Added seller import status reporting and safe progress/error logs. File contents and credentials are never logged.
- Added an additive migration for seller batch status. Existing products, batches, and price history are preserved.
