# 0.7.4

- Store the SmartStore product number in its own database field, separate from seller code and barcode.
- Build generated SmartStore links only from that explicit product number; a barcode or seller code can no longer be used in the URL.
- Add the product-number field with a non-destructive migration. Existing uploaded rows remain intact; re-upload the SmartStore export once to populate this field for older rows.
- Includes all 0.7.1 large CSV upload handling, 0.7.2 clickable candidate names, and 0.7.3 `상품번호(스마트스토어)` header recognition.
