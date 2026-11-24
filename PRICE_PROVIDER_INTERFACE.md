# Price data provider boundary

This release does not automate access to Coupang or Naver Shopping pages.

Coupang snapshots are imported from an authorized data source or a manually verified CSV. Required CSV fields: `SKU ID`, `판매처`, `가격`; optional fields: `배송비`, `URL`, `판매자`. The current dashboard accepts rows whose source is exactly `쿠팡`.

The investigation endpoint compares the latest two saved Coupang snapshots per SKU and generates Naver Shopping search links only for changed SKUs. A person confirms that the result is the same own-brand product. The system does not claim causation based on a single price observation.

Do not add browser automation, scraping, anti-bot workarounds, or authenticated page extraction unless the platform has expressly authorized the access or an approved data provider is used. WING seller API `salePrice` must not be treated as Rocket Delivery consumer-facing price without independent validation.
