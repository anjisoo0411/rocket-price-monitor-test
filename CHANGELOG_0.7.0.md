# 0.7.0

- Added an upload flow for XLSX/CSV product-price exports from seller centers the user is authorized to access.
- Stores seller-center exports in new additive tables without replacing existing Coupang product master or crawl history.
- Compares price-changed Coupang products with the latest uploaded price list per seller center.
- Matches exact barcodes first, then ranks product-name overlap and displays the match evidence and price difference.
- Clarified in the interface that matches are investigation clues, not confirmed causes; no SCM scraping or access-control bypass is performed.
