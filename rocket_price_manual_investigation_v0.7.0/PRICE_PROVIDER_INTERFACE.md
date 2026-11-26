# Price data input – 0.5.0

Daily Coupang crawl exports are uploaded manually as XLSX or CSV. Accepted columns are `옵션ID`, `노출ID`, `아이템ID`, `판매가`, `상품명`; optional columns include `재고량`, `품절 여부`, `평점`, `리뷰개수`, `판매자 ID`, and `카테고리 ID`.

The crawl date is read from a YYYYMMDD filename or supplied explicitly. Each date is stored as an immutable batch. Duplicate option IDs and duplicate dates are rejected; existing product and price records are not overwritten. Comparisons use option ID across the complete two batches and return only rows whose price, stock, or sold-out state changed. Master matching uses the existing `products.option_id` field. Coupang URLs are generated from exposure ID and option ID.

Naver Shopping has no assumed automated search integration. The interface opens a human-operated search link and lets a reviewer record candidate name, price, seller, URL, and match evidence. Candidates are context for investigation and are never asserted to be causes.
