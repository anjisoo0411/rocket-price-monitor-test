# 0.7.8

- Base name matching on the first six product-identity words, after removing model, color, and package-count terms.
- Require at least two shared leading identity words for name-based candidates; common trailing model/color text no longer creates a match.
- Preserve exact barcode matching only after explicit model and package conflicts are rejected. Show the number of matching leading words as evidence.
- Keep prior discount-price, SmartStore URL, quantity, model conflict, upload, and additive database behavior.
