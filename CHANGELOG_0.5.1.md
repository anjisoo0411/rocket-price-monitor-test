# 0.5.1

- Changed dated crawl batch inserts to chunked database executemany operations of 1,000 rows.
- Reduced per-row ORM object creation for 15k-row crawl uploads to lower request time and memory use on the test service.
