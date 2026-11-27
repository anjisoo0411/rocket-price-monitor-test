# 0.7.2

- SmartStore candidate product names are clickable and open their listing in a new tab.
- Use an uploaded product URL when present; otherwise, for SmartStore rows with a numeric product number, generate `https://smartstore.naver.com/excci/products/{product_number}`.
- Existing uploaded candidate rows can use this generated link during comparison; no re-upload is required when their product number was imported.
