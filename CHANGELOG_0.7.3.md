# 0.7.3

- Recognize the SmartStore export column `상품번호(스마트스토어)` as the product number used to build EXCCI SmartStore listing URLs.
- Product number parsing remains compatible with existing supported product ID headers.
- Previously stored rows without the imported product number need to be uploaded again after deploying this version for generated links to appear.
