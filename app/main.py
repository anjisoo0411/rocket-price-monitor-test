from datetime import datetime, timezone
from pathlib import Path
import csv, io, os, secrets, urllib.parse, json, re, logging
from itertools import chain, islice
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, Integer, Float, DateTime, ForeignKey, Text, func, or_, UniqueConstraint, insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_secret: str = "dev-only-change-me"
    admin_token: str = "dev-admin-token"
    database_url: str = "sqlite:///./data/rocket_prices.db"
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
logger = logging.getLogger("rocket_price_monitor")
if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
Path("data").mkdir(exist_ok=True)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    model_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    coupang_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    option_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    item_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    exposure_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_sale_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    search_term: Mapped[Optional[str]] = mapped_column(String(700), nullable=True)
    tracking: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    prices = relationship("PriceSnapshot", back_populates="product", cascade="all, delete-orphan")

class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[int] = mapped_column(Integer)
    shipping: Mapped[int] = mapped_column(Integer, default=0)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    match_method: Mapped[str] = mapped_column(String(40), default="manual")
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    product = relationship("Product", back_populates="prices")

class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class SellerImportJob(Base):
    __tablename__ = "seller_import_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(100))
    source_filename: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class CrawlBatch(Base):
    __tablename__ = "crawl_batches"
    __table_args__ = (UniqueConstraint("crawl_date", name="uq_crawl_batch_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crawl_date: Mapped[str] = mapped_column(String(10), index=True)
    source_filename: Mapped[str] = mapped_column(String(300))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class CrawlRow(Base):
    __tablename__ = "crawl_rows"
    __table_args__ = (UniqueConstraint("batch_id", "option_id", name="uq_crawl_option_per_batch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("crawl_batches.id", ondelete="CASCADE"), index=True)
    option_id: Mapped[str] = mapped_column(String(40), index=True)
    exposure_id: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[str] = mapped_column(String(40))
    price: Mapped[int] = mapped_column(Integer)
    stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(700))
    sold_out: Mapped[Optional[bool]] = mapped_column(nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seller_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

class NaverCandidate(Base):
    __tablename__ = "naver_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("crawl_batches.id"), index=True)
    option_id: Mapped[str] = mapped_column(String(40), index=True)
    product_name: Mapped[str] = mapped_column(String(700))
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seller: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class SellerOfferBatch(Base):
    """One current product/price export supplied by an authorized seller center."""
    __tablename__ = "seller_offer_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_filename: Mapped[str] = mapped_column(String(300))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

class SellerOffer(Base):
    __tablename__ = "seller_offers"
    __table_args__ = (UniqueConstraint("batch_id", "source_product_id", name="uq_seller_offer_product_per_batch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("seller_offer_batches.id", ondelete="CASCADE"), index=True)
    source_product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    smartstore_product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    seller_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(700), index=True)
    price: Mapped[int] = mapped_column(Integer)
    price_basis: Mapped[str] = mapped_column(String(20), default="판매가")
    seller: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    email_sent: Mapped[bool] = mapped_column(default=False)

Base.metadata.create_all(engine)

# Additive migration: retain existing product rows and all price history.
from sqlalchemy import inspect
def migrate_product_columns():
    existing = {c["name"] for c in inspect(engine).get_columns("products")}
    additions = {
        "option_id": "VARCHAR(40)",
        "item_id": "VARCHAR(40)",
        "exposure_id": "VARCHAR(40)",
        "source_sale_price": "INTEGER",
    }
    with engine.begin() as conn:
        for name, sql_type in additions.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE products ADD COLUMN {name} {sql_type}")
    batch_columns = {c["name"] for c in inspect(engine).get_columns("seller_offer_batches")}
    if "status" not in batch_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE seller_offer_batches ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'completed'")
    offer_columns = {c["name"] for c in inspect(engine).get_columns("seller_offers")}
    if "smartstore_product_id" not in offer_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE seller_offers ADD COLUMN smartstore_product_id VARCHAR(100)")
    offer_columns = {c["name"] for c in inspect(engine).get_columns("seller_offers")}
    if "price_basis" not in offer_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE seller_offers ADD COLUMN price_basis VARCHAR(20) NOT NULL DEFAULT '판매가'")
migrate_product_columns()

app = FastAPI(title="Rocket Price Investigation", version="0.7.5")
app.mount("/static", StaticFiles(directory=str(BASE / "app" / "static")), name="static")

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

def auth(authorization: Optional[str] = Header(default=None)):
    if not settings.admin_token or settings.admin_token == "dev-admin-token":
        # 개발용 기본 토큰은 실행 편의를 위한 값. 클라우드 배포 전 반드시 변경.
        expected = settings.admin_token
    else: expected = settings.admin_token
    token = authorization.removeprefix("Bearer ") if authorization else ""
    if not secrets.compare_digest(token, expected): raise HTTPException(401, "인증 토큰이 올바르지 않습니다.")

class PriceIn(BaseModel):
    sku_id: str
    source: str = Field(min_length=1, max_length=80)
    price: int = Field(gt=0)
    shipping: int = Field(default=0, ge=0)
    url: Optional[str] = None
    seller: Optional[str] = None
    match_method: str = "manual"

class CandidateIn(BaseModel):
    batch_id: int
    option_id: str
    product_name: str = Field(min_length=1, max_length=700)
    price: Optional[int] = Field(default=None, gt=0)
    seller: Optional[str] = Field(default=None, max_length=250)
    url: Optional[str] = None
    evidence: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
def home(): return (BASE / "app" / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"status":"ok", "version":"0.7.5", "price_collection":"manual_dated_batch_upload", "seller_price_source":"authorized_seller_center_exports"}

@app.get("/api/summary", dependencies=[Depends(auth)])
def summary(s: Session=Depends(db)):
    total=s.query(func.count(Product.id)).scalar() or 0
    tracked=s.query(func.count(Product.id)).filter(Product.tracking.is_(True)).scalar() or 0
    with_prices=s.query(func.count(func.distinct(PriceSnapshot.product_id))).scalar() or 0
    alerts=s.query(func.count(AlertEvent.id)).scalar() or 0
    return {"total_products":total,"tracked_products":tracked,"products_with_prices":with_prices,"alerts":alerts,"price_sources": ["쿠팡", "판매자센터 내보내기"],"last_update":s.query(func.max(PriceSnapshot.verified_at)).scalar()}

@app.get("/api/products", dependencies=[Depends(auth)])
def products(q: str="", page:int=1, limit:int=50, s:Session=Depends(db)):
    limit=max(1,min(limit,200)); query=s.query(Product)
    if q: query=query.filter(or_(Product.sku_id.contains(q),Product.name.contains(q),Product.barcode.contains(q)))
    total=query.count(); rows=query.order_by(Product.id).offset((page-1)*limit).limit(limit).all()
    out=[]
    for p in rows:
        prices=s.query(PriceSnapshot).filter_by(product_id=p.id).order_by(PriceSnapshot.verified_at.desc()).limit(50).all()
        latest={}
        for x in prices:
            if x.source not in latest: latest[x.source]={"price":x.price,"shipping":x.shipping,"total":x.price+x.shipping,"url":x.url,"seller":x.seller,"verified_at":x.verified_at,"match_method":x.match_method}
        out.append({"sku_id":p.sku_id,"name":p.name,"barcode":p.barcode,"model_no":p.model_no,"tracking":p.tracking,"coupang_url":p.coupang_url,"option_id":p.option_id,"item_id":p.item_id,"exposure_id":p.exposure_id,"source_sale_price":p.source_sale_price,"prices":latest})
    return {"total":total,"page":page,"limit":limit,"items":out}

def _run_xlsx_import(job_id: int, raw: bytes):
    """Process the workbook in small committed batches after returning HTTP response."""
    s = SessionLocal()
    wb = None
    try:
        job = s.get(ImportJob, job_id)
        if not job: return
        job.status = "processing"; job.updated_at = datetime.now(timezone.utc); s.commit()
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb["추적대상_옵션IDURL"] if "추적대상_옵션IDURL" in wb.sheetnames else (wb["상품마스터"] if "상품마스터" in wb.sheetnames else wb.active)
        iterator = ws.iter_rows(values_only=True)
        headers = [str(c or "").strip() for c in next(iterator)]
        idx = {h:i for i,h in enumerate(headers)}
        if "SKU ID" not in idx or "상품명" not in idx:
            raise ValueError("SKU ID, 상품명 컬럼을 찾을 수 없습니다.")
        rows = []
        for row in iterator:
            sku = str(row[idx["SKU ID"]] or "").strip()
            name = str(row[idx["상품명"]] or "").strip()
            if sku and name:
                def val(col):
                    return str(row[idx[col]]).strip() if col in idx and row[idx[col]] is not None else None
                def priceval(col):
                    raw_price = row[idx[col]] if col in idx else None
                    try: return int(float(raw_price)) if raw_price not in (None, "") else None
                    except (TypeError, ValueError): return None
                rows.append({"sku":sku,"name":name,"barcode":val("바코드"),"model_no":val("모델번호(확인필요)"),
                    "coupang_url":val("쿠팡 상품 URL"),"option_id":val("옵션아이디"),"item_id":val("ITEM ID"),
                    "exposure_id":val("노출 ID"),"source_sale_price":priceval("판매가"),
                    "search_term":val("외부 검색어(자동생성)"),"tracking":(val("추적 여부") or "Y").upper() in ("Y","YES","1","TRUE")})
        job = s.get(ImportJob, job_id); job.total = len(rows); job.updated_at = datetime.now(timezone.utc); s.commit()
        batch_size = 200
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start+batch_size]
            skus = list({r["sku"] for r in batch})
            existing = {p.sku_id:p for p in s.query(Product).filter(Product.sku_id.in_(skus)).all()}
            added = updated = failed = 0
            for r in batch:
                try:
                    p = existing.get(r["sku"])
                    if p is None:
                        p = Product(sku_id=r["sku"], name=r["name"]); s.add(p); existing[r["sku"]] = p; added += 1
                    else:
                        p.name = r["name"]; updated += 1
                    p.barcode=r["barcode"]; p.model_no=r["model_no"]; p.coupang_url=r["coupang_url"]; p.option_id=r.get("option_id"); p.item_id=r.get("item_id"); p.exposure_id=r.get("exposure_id"); p.source_sale_price=r.get("source_sale_price"); p.search_term=r["search_term"]; p.tracking=r["tracking"]
                except Exception:
                    failed += 1
            s.flush()
            job = s.get(ImportJob, job_id)
            job.added += added; job.updated += updated; job.failed += failed
            job.processed = min(start + len(batch), len(rows)); job.updated_at = datetime.now(timezone.utc)
            s.commit()
        job = s.get(ImportJob, job_id); job.status = "completed"; job.updated_at = datetime.now(timezone.utc); s.commit()
    except Exception as e:
        s.rollback()
        job = s.get(ImportJob, job_id)
        if job:
            job.status = "failed"; job.error = str(e)[:1000]; job.updated_at = datetime.now(timezone.utc); s.commit()
    finally:
        if wb: wb.close()
        s.close()

@app.post("/api/import-xlsx/start", dependencies=[Depends(auth)])
async def start_import_xlsx(background_tasks: BackgroundTasks, file: UploadFile=File(...), s:Session=Depends(db)):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400,".xlsx 파일만 업로드할 수 있습니다.")
    active = s.query(ImportJob).filter(ImportJob.status.in_(["queued", "processing"])).first()
    if active:
        raise HTTPException(409,"이미 상품 가져오기가 진행 중입니다. 진행 상태를 먼저 확인하세요.")
    raw = await file.read()
    job = ImportJob(status="queued"); s.add(job); s.commit(); s.refresh(job)
    background_tasks.add_task(_run_xlsx_import, job.id, raw)
    return {"job_id":job.id,"status":job.status}

@app.get("/api/import-xlsx/status/{job_id}", dependencies=[Depends(auth)])
def import_xlsx_status(job_id:int, s:Session=Depends(db)):
    job=s.get(ImportJob, job_id)
    if not job: raise HTTPException(404,"가져오기 작업을 찾을 수 없습니다.")
    total=job.total
    percent=100 if job.status=="completed" else (round(job.processed/total*100) if total else 0)
    return {"job_id":job.id,"status":job.status,"total":total,"processed":job.processed,"percent":percent,"added":job.added,"updated":job.updated,"failed":job.failed,"error":job.error}

def _norm_header(value):
    return re.sub(r"[\s_]+", "", str(value or "").strip()).lower()

def _crawl_date(filename: str, supplied: Optional[str]):
    value = supplied or ""
    if not value:
        m = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", filename)
        if m: value = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    try: return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError: raise HTTPException(400, "수집일을 YYYY-MM-DD로 지정하거나 파일명에 YYYYMMDD 날짜를 넣어 주세요.")

def _read_crawl_file(filename: str, raw: bytes):
    required = {"옵션id", "노출id", "아이템id", "판매가", "상품명"}
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            ws = wb.active; iterator = ws.iter_rows(values_only=True)
            headers = [_norm_header(x) for x in next(iterator, ())]
            records = [dict(zip(headers, row)) for row in iterator]
        finally: wb.close()
    elif filename.lower().endswith(".csv"):
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = [_norm_header(x) for x in (reader.fieldnames or [])]
        records = [dict(zip(headers, row.values())) for row in reader]
    else: raise HTTPException(400, ".xlsx 또는 .csv 파일을 업로드해 주세요.")
    if not required.issubset(set(headers)):
        raise HTTPException(400, "필수 컬럼(옵션ID, 노출ID, 아이템ID, 판매가, 상품명)이 없습니다.")
    def value(row, key): return row.get(_norm_header(key))
    def integer(x, label, required=True):
        try:
            if x in (None, "") and not required: return None
            return int(float(str(x).replace(",", "").replace("원", "").strip()))
        except (ValueError, TypeError): raise HTTPException(400, f"{label} 숫자 형식을 확인해 주세요.")
    result=[]; seen=set()
    for row in records:
        option=str(value(row,"옵션ID") or "").strip()
        if not option: continue
        if option in seen: raise HTTPException(400, f"중복 옵션ID가 있습니다: {option}")
        seen.add(option)
        sold = str(value(row,"품절 여부") or "").strip().lower()
        result.append({"option_id":option,"exposure_id":str(value(row,"노출ID") or "").strip(),
          "item_id":str(value(row,"아이템ID") or "").strip(),"price":integer(value(row,"판매가"),"판매가"),
          "stock":integer(value(row,"재고량"),"재고량",False),"name":str(value(row,"상품명") or "").strip(),
          "sold_out": True if sold in ("yes","y","true","1","품절") else (False if sold in ("no","n","false","0","판매중") else None),
          "rating":float(value(row,"평점")) if value(row,"평점") not in (None,"") else None,
          "review_count":integer(value(row,"리뷰개수"),"리뷰개수",False),
          "seller_id":str(value(row,"판매자 ID") or "").strip() or None,
          "category_id":str(value(row,"카테고리 ID") or "").strip() or None})
    if not result: raise HTTPException(400, "가져올 데이터 행이 없습니다.")
    return result

def _iter_seller_export(filename: str, raw: bytes):
    """Yield normalized seller rows without materializing the full CSV matrix."""
    wb = None
    csv_stream = None
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        iterator = wb.active.iter_rows(values_only=True)
    elif filename.lower().endswith(".csv"):
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("cp949")
        csv_stream = io.StringIO(content, newline="")
        iterator = csv.reader(csv_stream)
    else:
        raise HTTPException(400, ".xlsx 또는 .csv 판매자센터 내보내기 파일을 선택해 주세요.")
    aliases = {
        "name": {"상품명", "스마트스토어상품명", "판매상품명", "상품명(스마트스토어)"},
        "price": {"판매가", "판매가격", "상품판매가", "판매가(원)", "판매가격(원)"},
        "discount_price": {"할인가", "할인가격", "할인판매가", "할인 판매가", "할인가(원)"},
        "product_id": {"상품번호", "스마트스토어상품번호", "상품번호(스마트스토어)", "상품번호스마트스토어", "상품ID", "상품ID(스마트스토어)"},
        "seller_code": {"판매자상품코드", "판매자코드", "상품코드", "판매자관리코드"},
        "barcode": {"바코드", "표준바코드", "EAN", "UPC"},
        "url": {"상품URL", "상품주소", "스마트스토어URL", "판매URL", "URL"},
        "seller": {"판매처", "스토어명", "판매자명", "판매자"},
    }
    def normalized(v):
        return re.sub(r"[\s_()（）\-]+", "", str(v or "").strip()).lower()
    normalized_aliases = {key:{normalized(v) for v in values} for key,values in aliases.items()}
    header_row = None; indexes = None
    prefix = list(islice(iterator, 30))
    for row_no, row in enumerate(prefix):
        names = [normalized(v) for v in row]
        found = {key: next((i for i,v in enumerate(names) if v in vals), None) for key,vals in normalized_aliases.items()}
        if found["name"] is not None and (found["price"] is not None or found["discount_price"] is not None):
            header_row = row_no; indexes = found; break
    if indexes is None:
        if wb: wb.close()
        if csv_stream: csv_stream.close()
        raise HTTPException(400, "판매자센터 파일에서 상품명과 판매가 열을 찾지 못했습니다. 내보낸 원본 파일을 선택해 주세요.")
    def cell(row, key):
        i = indexes.get(key)
        return row[i] if i is not None and i < len(row) else None
    def clean(v):
        if v in (None, ""): return None
        if isinstance(v, (int,float)) and float(v).is_integer(): return str(int(v))
        return str(v).strip()
    def generate():
        seen=set(); count=0
        try:
            for row_no, row in enumerate(chain(prefix[header_row+1:], iterator), start=header_row+1):
                name = clean(cell(row,"name"))
                if not name: continue
                raw_discount = cell(row,"discount_price")
                price_basis = "할인가"
                try:
                    discount_value = int(float(str(raw_discount).replace(",","").replace("원","").strip())) if raw_discount not in (None, "") else 0
                except (TypeError, ValueError):
                    discount_value = 0
                raw_price = raw_discount if discount_value > 0 else cell(row,"price")
                if discount_value <= 0: price_basis = "판매가"
                try: price = discount_value if discount_value > 0 else int(float(str(raw_price).replace(",","").replace("원","").strip()))
                except (TypeError, ValueError):
                    raise HTTPException(400, f"판매가 숫자 형식을 확인해 주세요: {name[:80]}")
                if price <= 0: continue
                product_id=clean(cell(row,"product_id")); code=clean(cell(row,"seller_code")); barcode=clean(cell(row,"barcode"))
                if not barcode and code and re.fullmatch(r"\d{8,14}", code): barcode=code
                url=clean(cell(row,"url"))
                if url and not url.startswith(("https://","http://")): url=None
                key=product_id or code or f"{normalized(name)}|{price}"
                if key in seen: key=f"{key}|{row_no}"
                seen.add(key); count += 1
                yield {"source_product_id":key,"smartstore_product_id":product_id,"seller_code":code,"barcode":barcode,"product_name":name,"price":price,"price_basis":price_basis,
                       "seller":clean(cell(row,"seller")),"url":url}
            if not count: raise HTTPException(400, "판매자센터 파일에 가져올 상품 행이 없습니다.")
        finally:
            if wb: wb.close()
            if csv_stream: csv_stream.close()
    return generate()

def _read_seller_export(filename: str, raw: bytes):
    """Compatibility helper for small test inputs; the production import streams rows."""
    return list(_iter_seller_export(filename, raw))

def _name_tokens(value):
    tokens = re.findall(r"[0-9a-z가-힣]+", (value or "").lower())
    ignored = {"엑씨", "엑시", "휴대폰", "스마트폰", "케이스", "보호", "필름", "갤럭시", "맥세이프", "호환", "용", "용품"}
    return {t for t in tokens if len(t) > 1 and t not in ignored}

def _seller_offer_matches(offers, product: Optional[Product], crawl_name: str, coupang_price: int):
    """Return different-priced own-store offers, ranking verified identifiers first."""
    if not offers: return []
    target_barcode = (product.barcode or "").strip() if product else ""
    target_tokens = _name_tokens(product.name if product else crawl_name)
    scored=[]
    for offer, source in offers:
        if offer.price == coupang_price: continue
        if target_barcode and offer.barcode and target_barcode == offer.barcode:
            score=1.0; evidence="바코드 일치"
        else:
            candidate_tokens=_name_tokens(offer.product_name)
            overlap=target_tokens & candidate_tokens
            score=(len(overlap)/len(target_tokens | candidate_tokens)) if target_tokens and candidate_tokens else 0.0
            if score < 0.28: continue
            evidence=f"상품명 단어 유사도 {round(score*100)}%"
        candidate_url=offer.url
        if not candidate_url and ("스마트스토어" in source.lower() or "smartstore" in source.lower()):
            product_number=(offer.smartstore_product_id or "").strip()
            if re.fullmatch(r"\d{6,20}",product_number):
                candidate_url=f"https://smartstore.naver.com/excci/products/{product_number}"
        scored.append({"source":source,"product_name":offer.product_name,"price":offer.price,"price_basis":offer.price_basis or "판매가","price_delta":offer.price-coupang_price,
                       "seller":offer.seller or source,"url":candidate_url,"seller_code":offer.seller_code,"barcode":offer.barcode,
                       "match_score":round(score,3),"match_evidence":evidence,"is_same_price":False})
    by_source={}
    for row in sorted(scored,key=lambda x:(x["match_score"],abs(x["price_delta"])),reverse=True):
        by_source.setdefault(row["source"],[])
        if len(by_source[row["source"]])<3: by_source[row["source"]].append(row)
    return [row for source_rows in by_source.values() for row in source_rows]

def _run_seller_import(job_id: int, source: str, filename: str, raw: bytes):
    """Parse and insert rows in bounded chunks outside the browser request lifetime."""
    s = SessionLocal(); batch = None
    try:
        logger.info("seller_import_started job_id=%s source=%s filename=%s bytes=%s",job_id,source,filename,len(raw))
        job = s.get(SellerImportJob, job_id)
        if not job: return
        job.status = "processing"; job.updated_at = datetime.now(timezone.utc); s.commit()
        batch = SellerOfferBatch(source=source, source_filename=filename[:300], row_count=0, status="processing")
        s.add(batch); s.commit(); s.refresh(batch)
        chunk=[]; processed=0
        for row in _iter_seller_export(filename, raw):
            chunk.append(dict(batch_id=batch.id, **row))
            if len(chunk) >= 500:
                s.execute(insert(SellerOffer), chunk)
                processed += len(chunk); chunk=[]
                batch.row_count=processed
                job=s.get(SellerImportJob,job_id); job.processed=processed; job.updated_at=datetime.now(timezone.utc)
                s.commit()
                logger.info("seller_import_progress job_id=%s processed=%s",job_id,processed)
        if chunk:
            s.execute(insert(SellerOffer), chunk)
            processed += len(chunk)
        if processed < 1:
            raise HTTPException(400, "판매자센터 파일에 가져올 상품 행이 없습니다.")
        batch.row_count=processed; batch.status="completed"
        job=s.get(SellerImportJob,job_id); job.processed=processed; job.status="completed"; job.updated_at=datetime.now(timezone.utc)
        s.commit()
        logger.info("seller_import_completed job_id=%s rows=%s",job_id,processed)
    except Exception as exc:
        s.rollback()
        job=s.get(SellerImportJob,job_id)
        if job:
            job.status="failed"
            job.error=(str(exc.detail) if isinstance(exc,HTTPException) else str(exc))[:1000]
            job.updated_at=datetime.now(timezone.utc)
        if batch:
            batch=s.get(SellerOfferBatch,batch.id)
            if batch: batch.status="failed"
        s.commit()
        logger.exception("seller_import_failed job_id=%s",job_id)
    finally:
        s.close()

@app.post("/api/seller-batches", status_code=202, dependencies=[Depends(auth)])
async def upload_seller_batch(background_tasks: BackgroundTasks, source: str=Form(...), file: UploadFile=File(...), s: Session=Depends(db)):
    source=source.strip(); filename=file.filename or "upload"
    if not source or len(source)>100: raise HTTPException(400,"판매처 이름을 입력해 주세요.")
    if not filename.lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(400,".xlsx 또는 .csv 판매자센터 파일을 선택해 주세요.")
    raw=await file.read()
    job=SellerImportJob(source=source,source_filename=filename[:300],status="queued")
    s.add(job); s.commit(); s.refresh(job)
    background_tasks.add_task(_run_seller_import,job.id,source,filename,raw)
    logger.info("seller_upload_accepted job_id=%s source=%s filename=%s bytes=%s",job.id,source,filename,len(raw))
    return {"job_id":job.id,"source":source,"status":"queued"}

@app.get("/api/seller-batches/status/{job_id}", dependencies=[Depends(auth)])
def seller_import_status(job_id: int, s: Session=Depends(db)):
    job=s.get(SellerImportJob,job_id)
    if not job: raise HTTPException(404,"판매처 가격표 업로드 작업을 찾을 수 없습니다.")
    return {"job_id":job.id,"source":job.source,"filename":job.source_filename,"status":job.status,
            "processed":job.processed,"error":job.error}

@app.get("/api/seller-batches", dependencies=[Depends(auth)])
def list_seller_batches(s: Session=Depends(db)):
    latest=s.query(func.max(SellerOfferBatch.id).label("id")).filter(SellerOfferBatch.status=="completed").group_by(SellerOfferBatch.source).subquery()
    rows=s.query(SellerOfferBatch).join(latest,SellerOfferBatch.id==latest.c.id).order_by(SellerOfferBatch.source).all()
    return [{"id":b.id,"source":b.source,"source_filename":b.source_filename,"row_count":b.row_count,"imported_at":b.imported_at} for b in rows]

@app.post("/api/crawl-batches", dependencies=[Depends(auth)])
async def upload_crawl_batch(file: UploadFile=File(...), crawl_date: Optional[str]=Form(default=None), s: Session=Depends(db)):
    day = _crawl_date(file.filename or "", crawl_date)
    if s.query(CrawlBatch).filter_by(crawl_date=day).first(): raise HTTPException(409, f"{day} 배치가 이미 있습니다. 기존 기록은 자동으로 덮어쓰지 않습니다.")
    rows = _read_crawl_file(file.filename or "", await file.read())
    batch = CrawlBatch(crawl_date=day, source_filename=(file.filename or "upload")[:300], row_count=len(rows))
    s.add(batch); s.flush()
    # Core executemany avoids creating and returning 15k ORM objects in a single request.
    payload = [dict(batch_id=batch.id, **row) for row in rows]
    for start in range(0, len(payload), 1000):
        s.execute(insert(CrawlRow), payload[start:start + 1000])
    s.commit()
    return {"batch_id":batch.id,"crawl_date":day,"row_count":len(rows),"status":"completed"}

@app.get("/api/crawl-batches", dependencies=[Depends(auth)])
def list_crawl_batches(s: Session=Depends(db)):
    return [{"id":b.id,"crawl_date":b.crawl_date,"source_filename":b.source_filename,"row_count":b.row_count,"imported_at":b.imported_at}
            for b in s.query(CrawlBatch).order_by(CrawlBatch.crawl_date.desc()).all()]

@app.get("/api/crawl-batches/compare", dependencies=[Depends(auth)])
def compare_crawl_batches(previous_id: int, current_id: int, s: Session=Depends(db)):
    old=s.get(CrawlBatch,previous_id); new=s.get(CrawlBatch,current_id)
    if not old or not new or old.id==new.id: raise HTTPException(400,"서로 다른 두 날짜의 배치를 선택해 주세요.")
    a={x.option_id:x for x in s.query(CrawlRow).filter_by(batch_id=old.id).all()}; b={x.option_id:x for x in s.query(CrawlRow).filter_by(batch_id=new.id).all()}
    ids=set(a)&set(b); products={}
    latest_offer_ids=s.query(func.max(SellerOfferBatch.id).label("id")).filter(SellerOfferBatch.status=="completed").group_by(SellerOfferBatch.source).subquery()
    offer_rows=s.query(SellerOffer,SellerOfferBatch.source).join(SellerOfferBatch,SellerOfferBatch.id==SellerOffer.batch_id).join(latest_offer_ids,SellerOfferBatch.id==latest_offer_ids.c.id).all()
    for p in s.query(Product).filter(Product.option_id.in_(ids)).all(): products.setdefault(p.option_id,[]).append(p)
    out=[]; missing_master=0; price_changed_count=0; inventory_changed_count=0
    for oid in ids:
        x,y=a[oid],b[oid]
        change_types=[]
        if x.price != y.price: change_types.append("price"); price_changed_count += 1
        if x.stock != y.stock: change_types.append("stock")
        if x.sold_out != y.sold_out: change_types.append("sold_out")
        if "stock" in change_types or "sold_out" in change_types: inventory_changed_count += 1
        if not change_types: continue
        matched=products.get(oid,[])
        if not matched: missing_master+=1
        p=matched[0] if len(matched)==1 else None
        name=(p.name if p else y.name)
        url=f"https://www.coupang.com/vp/products/{urllib.parse.quote(y.exposure_id,safe='')}?vendorItemId={urllib.parse.quote(oid,safe='')}" if y.exposure_id else None
        seller_matches=_seller_offer_matches(offer_rows,p,y.name,y.price) if "price" in change_types else []
        out.append({"option_id":oid,"sku_id":p.sku_id if p else None,"name":name,"crawl_name":y.name,"barcode":p.barcode if p else None,
          "previous_price":x.price,"current_price":y.price,"delta":y.price-x.price,"previous_stock":x.stock,"current_stock":y.stock,
          "previous_sold_out":x.sold_out,"current_sold_out":y.sold_out,"previous_date":old.crawl_date,"current_date":new.crawl_date,
          "change_types":change_types,
          "coupang_url":url,
          "match_evidence":("마스터 옵션ID 일치" if p else "마스터에서 옵션ID를 찾지 못함; 크롤링 상품명으로 표시"),
          "seller_price_matches":seller_matches})
    out.sort(key=lambda v:abs(v["delta"]),reverse=True)
    return {"previous":{"id":old.id,"date":old.crawl_date,"row_count":old.row_count},"current":{"id":new.id,"date":new.crawl_date,"row_count":new.row_count},
      "compared_count":len(ids),"changed_count":len(out),"price_changed_count":price_changed_count,"inventory_changed_count":inventory_changed_count,
      "previous_only_count":len(set(a)-set(b)),"current_only_count":len(set(b)-set(a)),
      "unmatched_master_changes":missing_master,"items":out,"note":"쿠팡에서 가격 변동한 상품과 각 판매자센터 내보내기 자료의 자사 상품명을 대조합니다. 후보는 가격 차이와 상품명/바코드 일치 근거를 보여주는 참고 정보이며 원인을 확정하지 않습니다."}

@app.post("/api/naver-candidates", dependencies=[Depends(auth)])
def add_naver_candidate(data: CandidateIn, s: Session=Depends(db)):
    if not s.query(CrawlRow).filter_by(batch_id=data.batch_id,option_id=data.option_id).first(): raise HTTPException(404,"해당 배치의 옵션을 찾을 수 없습니다.")
    if data.url and not data.url.startswith(("https://", "http://")): raise HTTPException(400,"후보 URL은 http(s) 주소여야 합니다.")
    row=NaverCandidate(**data.model_dump());s.add(row);s.commit();return {"id":row.id,"ok":True}

# 이전 버전 클라이언트 호환용 동기 API. 새 대시보드는 위의 백그라운드 API를 사용합니다.
@app.post("/api/import-xlsx", dependencies=[Depends(auth)])
async def import_xlsx(file: UploadFile=File(...), s:Session=Depends(db)):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")): raise HTTPException(400,".xlsx 파일만 업로드할 수 있습니다.")
    raw=await file.read(); wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    ws=wb["추적대상_옵션IDURL"] if "추적대상_옵션IDURL" in wb.sheetnames else (wb["상품마스터"] if "상품마스터" in wb.sheetnames else wb.active)
    headers=[str(c or "").strip() for c in next(ws.iter_rows(min_row=1,max_row=1,values_only=True))]; idx={h:i for i,h in enumerate(headers)}
    if "SKU ID" not in idx or "상품명" not in idx: raise HTTPException(400,"SKU ID, 상품명 컬럼을 찾을 수 없습니다.")
    added=updated=0
    for row in ws.iter_rows(min_row=2,values_only=True):
        sku=str(row[idx["SKU ID"]] or "").strip(); name=str(row[idx["상품명"]] or "").strip()
        if not sku or not name: continue
        def val(col): return str(row[idx[col]]).strip() if col in idx and row[idx[col]] is not None else None
        p=s.query(Product).filter_by(sku_id=sku).first()
        if not p: p=Product(sku_id=sku,name=name); s.add(p); added+=1
        else: updated+=1; p.name=name
        p.barcode=val("바코드"); p.model_no=val("모델번호(확인필요)"); p.coupang_url=val("쿠팡 상품 URL")
        p.option_id=val("옵션아이디"); p.item_id=val("ITEM ID"); p.exposure_id=val("노출 ID")
        try: p.source_sale_price=int(float(val("판매가"))) if val("판매가") else None
        except (TypeError, ValueError): p.source_sale_price=None
        p.search_term=val("외부 검색어(자동생성)"); p.tracking=(val("추적 여부") or "Y").upper() in ("Y","YES","1","TRUE")
    s.commit(); wb.close(); return {"added":added,"updated":updated,"total":s.query(func.count(Product.id)).scalar()}

@app.post("/api/prices", dependencies=[Depends(auth)])
def add_price(data:PriceIn,s:Session=Depends(db)):
    p=s.query(Product).filter_by(sku_id=data.sku_id).first()
    if not p: raise HTTPException(404,"SKU를 찾을 수 없습니다.")
    snap=PriceSnapshot(product_id=p.id,source=data.source,price=data.price,shipping=data.shipping,url=data.url,seller=data.seller,match_method=data.match_method)
    s.add(snap)
    # On-demand workflow: save snapshots only; no alert/email is generated.
    s.commit(); return {"ok":True,"snapshot_id":snap.id}

@app.post("/api/import-prices-csv", dependencies=[Depends(auth)])
async def import_prices_csv(file:UploadFile=File(...),s:Session=Depends(db)):
    raw=(await file.read()).decode("utf-8-sig")
    reader=csv.DictReader(io.StringIO(raw)); required={"SKU ID","판매처","가격"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise HTTPException(400,"CSV 필수 컬럼: SKU ID, 판매처, 가격 (선택: 배송비, URL, 판매자)")
    count=0; missing=0; skipped_source=0
    for r in reader:
        if str(r.get("판매처") or "").strip() != "쿠팡":
            skipped_source += 1
            continue
        p=s.query(Product).filter_by(sku_id=str(r["SKU ID"]).strip()).first()
        if not p: missing+=1; continue
        try: price=int(str(r["가격"]).replace(",","").replace("원","")); shipping=int(str(r.get("배송비") or "0").replace(",","").replace("원",""))
        except: continue
        if price<=0: continue
        s.add(PriceSnapshot(product_id=p.id,source=r["판매처"],price=price,shipping=shipping,url=r.get("URL"),seller=r.get("판매자"),match_method="csv")); count+=1
        # No automatic alert/email; the user runs the investigation when needed.
    s.commit(); return {"imported":count,"unknown_sku_rows":missing,"skipped_non_coupang_rows":skipped_source}



@app.post("/api/investigations/changed", dependencies=[Depends(auth)])
def investigate_changed_products(s: Session=Depends(db)):
    """Compare the latest two saved Coupang snapshots; no website crawling occurs here."""
    products = s.query(Product).filter(Product.tracking.is_(True)).order_by(Product.sku_id).all()
    changed = []
    insufficient = 0
    for p in products:
        snaps = (s.query(PriceSnapshot).filter_by(product_id=p.id, source="쿠팡")
                 .order_by(PriceSnapshot.verified_at.desc(), PriceSnapshot.id.desc()).limit(2).all())
        if len(snaps) < 2:
            insufficient += 1
            continue
        latest, previous = snaps[0], snaps[1]
        old_total = previous.price + previous.shipping
        new_total = latest.price + latest.shipping
        if old_total != new_total:
            term = p.barcode or p.name
            changed.append({
                "sku_id":p.sku_id,"name":p.name,"barcode":p.barcode,
                "previous_price":old_total,"current_price":new_total,"delta":new_total-old_total,
                "previous_at":previous.verified_at,"current_at":latest.verified_at,
                "coupang_url":p.coupang_url,
                "naver_search_url":"https://search.shopping.naver.com/search/all?query=" + urllib.parse.quote(term or p.name),
            })
    changed.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return {"checked_products":len(products),"changed_count":len(changed),
            "insufficient_history_count":insufficient,"items":changed,
            "note":"저장된 쿠팡 가격 스냅샷 2건을 비교했습니다. 네이버 쇼핑은 링크로 열어 담당자가 동일 상품과 관련 가격을 확인합니다. 자동 접속·크롤링은 수행하지 않습니다."}

@app.get("/api/products/{sku_id}/investigation", dependencies=[Depends(auth)])
def product_investigation(sku_id: str, s: Session=Depends(db)):
    p=s.query(Product).filter_by(sku_id=sku_id).first()
    if not p: raise HTTPException(404,"등록된 SKU ID를 찾을 수 없습니다.")
    snaps=(s.query(PriceSnapshot).filter_by(product_id=p.id,source="쿠팡")
           .order_by(PriceSnapshot.verified_at.desc(),PriceSnapshot.id.desc()).limit(10).all())
    term=p.barcode or p.name
    return {"sku_id":p.sku_id,"name":p.name,"barcode":p.barcode,"coupang_url":p.coupang_url,
            "option_id":p.option_id,"item_id":p.item_id,"exposure_id":p.exposure_id,
            "source_sale_price":p.source_sale_price,
            "naver_search_url":"https://search.shopping.naver.com/search/all?query="+urllib.parse.quote(term or p.name),
            "coupang_snapshots":[{"price":x.price+x.shipping,"verified_at":x.verified_at,"url":x.url} for x in snaps]}

@app.get("/api/alerts", dependencies=[Depends(auth)])
def alerts(limit:int=50,s:Session=Depends(db)):
    rows=s.query(AlertEvent).order_by(AlertEvent.created_at.desc()).limit(min(limit,200)).all()
    return [{"id":x.id,"message":x.message,"created_at":x.created_at,"email_sent":x.email_sent} for x in rows]

@app.get("/api/settings", dependencies=[Depends(auth)])
def get_settings():
    return {"coupang_provider":"수동 업로드 배치","seller_price_provider":"권한이 있는 판매자센터 파일 업로드","email_notifications":"사용 안 함","scheduled_collection":"사용 안 함"}

@app.get("/api/export.csv", dependencies=[Depends(auth)])
def export_csv(s:Session=Depends(db)):
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["SKU ID","상품명","바코드","옵션아이디","ITEM ID","노출 ID","기준 판매가","판매처","가격","배송비","총액","판매자","URL","확인시각","매칭방식"])
    for p in s.query(Product).order_by(Product.sku_id).all():
        snaps=s.query(PriceSnapshot).filter_by(product_id=p.id).order_by(PriceSnapshot.verified_at.desc()).all()
        if not snaps: writer.writerow([p.sku_id,p.name,p.barcode or "",p.option_id or "",p.item_id or "",p.exposure_id or "",p.source_sale_price or "","미수집","","","","","","",""])
        else:
            for x in snaps:
                writer.writerow([p.sku_id,p.name,p.barcode or "",p.option_id or "",p.item_id or "",p.exposure_id or "",p.source_sale_price or "",x.source,x.price,x.shipping,x.price+x.shipping,x.seller or "",x.url or "",x.verified_at.isoformat(),x.match_method])
    data="\ufeff"+output.getvalue()
    return StreamingResponse(iter([data]),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=rocket_price_report.csv"})
