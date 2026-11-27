# 0.7.7

- Exclude a seller candidate when both listing titles identify different phone or tablet models, including Galaxy S/A/Tab, Z Fold/ Z Flip families, iPhone model tiers, and iPad.
- Use the current Coupang crawl title as the primary matching reference; fall back to the product-master title only when the crawl title is absent.
- Apply model and package-quantity conflict checks before barcode matching, preventing generic words or a conflicting barcode from overriding an explicit model/quantity mismatch.
- Normalize common model/title spacing variants and require a more conservative title-token overlap score when no exact barcode is available.
- Show explicit model agreement or missing model-name evidence for manual review.
- Retain the discounted-price preference, SmartStore URLs, quantity checks, upload handling, and all additive database changes from earlier versions.
