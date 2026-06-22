"""
normalizer.py - Normalisasi data BPS ke tabel fakta terstruktur.
================================================================
Membuat tabel `fact_industri_wilayah` dengan kolom semantik:
  table_id, domain_id, domain_name, source_title,
  tahun, wilayah, jenis_industri,
  n_perusahaan, tenaga_kerja, investasi_ribu_rp, nilai_produksi_ribu_rp

Algoritma heuristik:
  1. Cari "baris header" = baris pertama yang mengandung "kabupaten" / "kota"
  2. Map kolom ke semantik dengan keyword matching
  3. Untuk tabel multi-tahun (pivot), unpivot ke format long
  4. Bersihkan angka (hapus spasi ribuan, konversi ke float)
  5. Ekstrak tahun dari judul tabel jika tidak tersedia di kolom
"""

import re
import json
import sqlite3
from datetime import datetime

DATABASE_PATH = "bps_data.db"

# ─── Keyword maps ─────────────────────────────────────────────────────────────

KW_WILAYAH    = ["kabupaten", "kota", "wilayah", "regency", "municipality",
                 "region", "daerah", "provinsi"]
KW_PERUSAHAAN = ["perusahaan", "usaha", "establishment", "company", "companies",
                 "unit"]
KW_TK         = ["tenaga kerja", "pekerja", "labour", "worker", "employee",
                 "karyawan"]
KW_INVESTASI  = ["investasi", "investment", "modal"]
KW_PRODUKSI   = ["nilai produksi", "production value", "nilai output",
                 "output value", "pendapatan", "revenue"]

JENIS_IBS_KW  = ["besar dan sedang", "besar sedang", "large and medium",
                 "ibs", "manufacturing"]
JENIS_IMK_KW  = ["mikro dan kecil", "mikro kecil", "micro and small",
                 "imk", "micro small"]


# ─── Utilitas ──────────────────────────────────────────────────────────────────

def clean_number(val) -> float | None:
    """Konversi nilai (string/int/float) ke float, atau None jika tidak bisa."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("-", "...", "n.a.", "na", "n/a", "", "none", "null"):
        return None
    # Hapus spasi ribuan dan ubah koma desimal ke titik
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_years_from_title(title: str) -> list[int]:
    """Ekstrak tahun dari judul tabel. Contoh: '2017 - 2019' → [2017, 2018, 2019]"""
    years = []
    # Cari range tahun: "2017 - 2019" atau "2017-2019"
    range_match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', title)
    if range_match:
        y1, y2 = int(range_match.group(1)), int(range_match.group(2))
        years = list(range(y1, y2 + 1))
    else:
        # Cari tahun tunggal
        found = re.findall(r'\b(20\d{2}|19\d{2})\b', title)
        years = sorted(set(int(y) for y in found))
    return years


def contains_kw(text: str, keywords: list[str]) -> bool:
    """Cek apakah text mengandung salah satu keyword (case-insensitive)."""
    t = str(text).lower()
    return any(kw in t for kw in keywords)


def detect_jenis(title: str) -> str:
    """Tentukan jenis industri dari judul."""
    t = title.lower()
    if any(kw in t for kw in JENIS_IMK_KW):
        return "IMK"
    if any(kw in t for kw in JENIS_IBS_KW):
        return "IBS"
    return "UNKNOWN"


def is_place_name(val) -> bool:
    """Heuristik: apakah nilai ini seperti nama wilayah?"""
    if val is None:
        return False
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return False
    # Jangan ambil baris yang berisi angka murni
    if re.match(r'^[\d\s.,]+$', s):
        return False
    # Minimal 2 karakter, tidak terlalu panjang
    return 2 <= len(s) <= 80


# ─── Header Detection ──────────────────────────────────────────────────────────

def find_header_row(rows: list[list]) -> int | None:
    """
    Cari indeks baris yang mengandung keyword wilayah dan setidaknya satu
    keyword metrik (perusahaan / tenaga kerja).
    Kembalikan None jika tidak ditemukan.
    """
    for i, row in enumerate(rows):
        row_text = " ".join(str(v).lower() for v in row if v is not None)
        has_wilayah = any(kw in row_text for kw in KW_WILAYAH)
        has_metric  = any(kw in row_text for kw in
                         KW_PERUSAHAAN + KW_TK + KW_INVESTASI + KW_PRODUKSI)
        if has_wilayah and has_metric:
            return i
    # Fallback: cari baris yang hanya mengandung wilayah
    for i, row in enumerate(rows):
        row_text = " ".join(str(v).lower() for v in row if v is not None)
        if any(kw in row_text for kw in KW_WILAYAH):
            return i
    return None


def map_columns(header_rows: list[list]) -> dict:
    """
    Dari satu atau beberapa baris header, tentukan mapping kolom:
      { 'wilayah': [col_idx], 'perusahaan': [...], ... }
    Menggabungkan teks semua header rows per kolom untuk keyword matching.
    """
    if not header_rows:
        return {}

    n_cols = max(len(r) for r in header_rows)
    # Gabungkan teks per kolom dari semua baris header
    col_texts = []
    for c in range(n_cols):
        parts = []
        for r in header_rows:
            if c < len(r) and r[c] is not None:
                parts.append(str(r[c]).lower())
        col_texts.append(" ".join(parts))

    mapping = {"wilayah": None, "perusahaan": None,
               "tenaga_kerja": None, "investasi": None, "nilai_produksi": None}

    for c, text in enumerate(col_texts):
        if not text.strip():
            continue
        if mapping["wilayah"] is None and any(kw in text for kw in KW_WILAYAH):
            mapping["wilayah"] = c
        elif mapping["perusahaan"] is None and any(kw in text for kw in KW_PERUSAHAAN):
            mapping["perusahaan"] = c
        elif mapping["tenaga_kerja"] is None and any(kw in text for kw in KW_TK):
            mapping["tenaga_kerja"] = c
        elif mapping["investasi"] is None and any(kw in text for kw in KW_INVESTASI):
            mapping["investasi"] = c
        elif mapping["nilai_produksi"] is None and any(kw in text for kw in KW_PRODUKSI):
            mapping["nilai_produksi"] = c

    # Fallback: jika tidak ada wilayah terdeteksi, gunakan kolom 0
    if mapping["wilayah"] is None:
        mapping["wilayah"] = 0

    return mapping


# ─── Multi-Year Pivot Detection ────────────────────────────────────────────────

def detect_year_columns(rows: list[list], header_idx: int) -> list[tuple[int, int]]:
    """
    Untuk tabel pivot multi-tahun, cari kolom-kolom yang mengandung tahun.
    Kembalikan list of (col_idx, year).
    """
    year_cols = []
    for r in rows[max(0, header_idx - 1): header_idx + 3]:
        for c, v in enumerate(r):
            if v is None:
                continue
            s = str(v).strip()
            m = re.match(r'^(20\d{2}|19\d{2})\.?0?$', s)
            if m:
                year_cols.append((c, int(m.group(1))))
    return year_cols


# ─── Main Extraction ───────────────────────────────────────────────────────────

def extract_from_table(table_id: int, domain_id: str, domain_name: str,
                       title: str, raw_rows: list[list]) -> list[dict]:
    """
    Ekstrak rekaman fakta dari daftar baris mentah satu tabel.
    Kembalikan list of dict siap INSERT ke fact_industri_wilayah.
    """
    if not raw_rows:
        return []

    jenis = detect_jenis(title)
    title_years = extract_years_from_title(title)
    now = datetime.now().isoformat()

    header_idx = find_header_row(raw_rows)
    if header_idx is None:
        return []

    # Kumpulkan semua baris header (bisa beberapa baris)
    header_rows = []
    for i in range(header_idx, min(header_idx + 3, len(raw_rows))):
        row = raw_rows[i]
        row_text = " ".join(str(v) for v in row if v is not None).lower()
        # Hentikan jika baris ini tidak lagi seperti header
        if i > header_idx and is_place_name(row[0] if row else None):
            break
        header_rows.append(row)

    data_start = header_idx + len(header_rows)
    col_map = map_columns(header_rows)

    # Deteksi apakah tabel multi-tahun
    year_cols = detect_year_columns(raw_rows, header_idx)

    records = []

    if year_cols and len(year_cols) >= 2:
        # ── Mode tabel pivot multi-tahun ──────────────────────────────────────
        # Cari kelompok kolom per metrik berdasarkan posisi relatif
        # Strategi: untuk setiap kelompok tahun yang terdeteksi, unpivot
        wilayah_col = col_map.get("wilayah", 0)
        n_year_groups = len(year_cols)

        # Hitung offset kolom metrik dari wilayah_col
        metric_offsets = {}
        for metric, mc in col_map.items():
            if metric == "wilayah" or mc is None:
                continue
            metric_offsets[metric] = mc

        for row in raw_rows[data_start:]:
            if not row or not is_place_name(row[0] if wilayah_col == 0 else
                                            row[wilayah_col] if wilayah_col < len(row) else None):
                continue
            wilayah_val = str(row[wilayah_col]).strip() if wilayah_col < len(row) else None
            if not wilayah_val:
                continue

            for yc, year in year_cols:
                rec = {
                    "table_id": table_id, "domain_id": domain_id,
                    "domain_name": domain_name, "source_title": title[:200],
                    "tahun": year, "wilayah": wilayah_val,
                    "jenis_industri": jenis,
                    "n_perusahaan": None, "tenaga_kerja": None,
                    "investasi_ribu_rp": None, "nilai_produksi_ribu_rp": None,
                    "ingested_at": now,
                }
                # Coba ambil nilai di kolom yc
                if yc < len(row):
                    # Tentukan metrik kolom ini berdasarkan peta kolom terdekat
                    for metric, mc in metric_offsets.items():
                        if mc is not None and abs(mc - yc) <= 3:
                            key = {
                                "perusahaan": "n_perusahaan",
                                "tenaga_kerja": "tenaga_kerja",
                                "investasi": "investasi_ribu_rp",
                                "nilai_produksi": "nilai_produksi_ribu_rp",
                            }.get(metric)
                            if key:
                                rec[key] = clean_number(row[yc])
                            break
                records.append(rec)

    else:
        # ── Mode tabel tahun tunggal ──────────────────────────────────────────
        tahun = title_years[0] if len(title_years) == 1 else (
            title_years[-1] if title_years else None)

        wilayah_col      = col_map.get("wilayah", 0)
        perusahaan_col   = col_map.get("perusahaan")
        tenaga_kerja_col = col_map.get("tenaga_kerja")
        investasi_col    = col_map.get("investasi")
        produksi_col     = col_map.get("nilai_produksi")

        for row in raw_rows[data_start:]:
            if not row:
                continue
            wilayah_val = row[wilayah_col] if wilayah_col < len(row) else None
            if not is_place_name(wilayah_val):
                continue

            def get_col(ci):
                return clean_number(row[ci]) if ci is not None and ci < len(row) else None

            records.append({
                "table_id": table_id, "domain_id": domain_id,
                "domain_name": domain_name, "source_title": title[:200],
                "tahun": tahun, "wilayah": str(wilayah_val).strip(),
                "jenis_industri": jenis,
                "n_perusahaan":        get_col(perusahaan_col),
                "tenaga_kerja":        get_col(tenaga_kerja_col),
                "investasi_ribu_rp":   get_col(investasi_col),
                "nilai_produksi_ribu_rp": get_col(produksi_col),
                "ingested_at": now,
            })

    return records


# ─── Database ──────────────────────────────────────────────────────────────────

def init_fact_table(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS fact_industri_wilayah (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        table_id             INTEGER NOT NULL,
        domain_id            TEXT,
        domain_name          TEXT,
        source_title         TEXT,
        tahun                INTEGER,
        wilayah              TEXT,
        jenis_industri       TEXT,
        n_perusahaan         REAL,
        tenaga_kerja         REAL,
        investasi_ribu_rp    REAL,
        nilai_produksi_ribu_rp REAL,
        ingested_at          TEXT,
        FOREIGN KEY (table_id) REFERENCES tabel_katalog(table_id)
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_domain ON fact_industri_wilayah(domain_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_tahun  ON fact_industri_wilayah(tahun)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_wilayah ON fact_industri_wilayah(wilayah)")
    conn.commit()


# ─── Main ──────────────────────────────────────────────────────────────────────

def run_normalization(table_ids: list[int] | None = None,
                      keyword_filter: list[str] | None = None):
    """
    Normalisasi tabel-tabel BPS ke fact_industri_wilayah.

    Args:
        table_ids: Daftar table_id spesifik. Jika None, gunakan keyword_filter.
        keyword_filter: Daftar keyword judul (AND logic) untuk memilih tabel.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    init_fact_table(conn)

    # Tentukan tabel yang akan diproses
    if table_ids:
        placeholders = ",".join("?" * len(table_ids))
        tables = conn.execute(f"""
            SELECT table_id, domain_id, domain_name, title
            FROM tabel_katalog
            WHERE table_id IN ({placeholders}) AND ingestion_status='DONE'
        """, table_ids).fetchall()
    elif keyword_filter:
        query = "SELECT table_id, domain_id, domain_name, title FROM tabel_katalog WHERE ingestion_status='DONE'"
        conditions = [f"lower(title) LIKE ?" for _ in keyword_filter]
        query += " AND " + " AND ".join(conditions)
        params = [f"%{kw.lower()}%" for kw in keyword_filter]
        tables = conn.execute(query, params).fetchall()
    else:
        # Default: tabel yg judul mengandung "kabupaten" atau "kota"
        tables = conn.execute("""
            SELECT table_id, domain_id, domain_name, title
            FROM tabel_katalog
            WHERE ingestion_status='DONE'
              AND (lower(title) LIKE '%kabupaten%' OR lower(title) LIKE '%kota%'
                   OR lower(title) LIKE '%regency%' OR lower(title) LIKE '%municipality%')
        """).fetchall()

    print(f"\n{'='*60}")
    print(f"  BPS Normalizer - fact_industri_wilayah")
    print(f"{'='*60}")
    print(f"  Tabel yang akan diproses: {len(tables)}\n")

    total_records = 0
    success = 0
    skipped = 0

    for table_id, domain_id, domain_name, title in tables:
        # Ambil semua baris mentah
        raw = conn.execute(
            "SELECT data_json FROM tabel_data WHERE table_id=? ORDER BY row_index",
            (table_id,)
        ).fetchall()
        if not raw:
            skipped += 1
            continue

        rows = [list(json.loads(r[0]).values()) for r in raw]

        records = extract_from_table(table_id, domain_id, domain_name, title, rows)

        if not records:
            print(f"  SKIP Tabel {table_id} [{domain_name}]: tidak ada rekaman yang bisa diekstrak")
            skipped += 1
            continue

        # Hapus data lama untuk tabel ini (idempoten)
        conn.execute("DELETE FROM fact_industri_wilayah WHERE table_id=?", (table_id,))

        conn.executemany("""
            INSERT INTO fact_industri_wilayah
                (table_id, domain_id, domain_name, source_title, tahun, wilayah,
                 jenis_industri, n_perusahaan, tenaga_kerja,
                 investasi_ribu_rp, nilai_produksi_ribu_rp, ingested_at)
            VALUES
                (:table_id, :domain_id, :domain_name, :source_title, :tahun, :wilayah,
                 :jenis_industri, :n_perusahaan, :tenaga_kerja,
                 :investasi_ribu_rp, :nilai_produksi_ribu_rp, :ingested_at)
        """, records)
        conn.commit()

        n = len(records)
        print(f"  OK  Tabel {table_id:5d} [{domain_name:15s}] {title[:45]:45s} -> {n} rekaman")
        total_records += n
        success += 1

    conn.close()

    print(f"\n{'='*60}")
    print(f"  Normalisasi Selesai")
    print(f"{'='*60}")
    print(f"  Berhasil: {success} tabel")
    print(f"  Dilewati: {skipped} tabel")
    print(f"  Total rekaman: {total_records:,}")
    print(f"{'='*60}")


def print_sample_query():
    """Tampilkan contoh query ke fact_industri_wilayah."""
    conn = sqlite3.connect(DATABASE_PATH)

    print("\n=== CONTOH DATA fact_industri_wilayah ===")
    rows = conn.execute("""
        SELECT domain_name, wilayah, tahun, jenis_industri,
               n_perusahaan, tenaga_kerja, nilai_produksi_ribu_rp
        FROM fact_industri_wilayah
        WHERE n_perusahaan IS NOT NULL AND tenaga_kerja IS NOT NULL
        ORDER BY tenaga_kerja DESC NULLS LAST
        LIMIT 15
    """).fetchall()
    print(f"{'Domain':15s} {'Wilayah':20s} {'Thn':4s} {'Jenis':4s}  {'Perush':>8s}  {'TK':>10s}  {'Produksi (ribu Rp)':>22s}")
    print("-" * 90)
    for r in rows:
        prod = f"{r[6]:,.0f}" if r[6] else "-"
        print(f"{(r[0] or ''):15s} {(r[1] or ''):20s} {str(r[2] or ''):4s} {(r[3] or ''):4s}  "
              f"{int(r[4]) if r[4] else 0:>8,}  {int(r[5]) if r[5] else 0:>10,}  {prod:>22s}")

    print("\n=== STATISTIK PER PROVINSI (Nilai Produksi terbesar) ===")
    rows2 = conn.execute("""
        SELECT domain_name, jenis_industri, tahun,
               COUNT(DISTINCT wilayah) as n_wilayah,
               SUM(n_perusahaan) as total_perusahaan,
               SUM(tenaga_kerja) as total_tk
        FROM fact_industri_wilayah
        WHERE n_perusahaan IS NOT NULL
        GROUP BY domain_name, jenis_industri, tahun
        ORDER BY total_tk DESC NULLS LAST
        LIMIT 15
    """).fetchall()
    print(f"{'Provinsi':20s} {'Jenis':5s} {'Thn':4s}  {'Kab/Kota':>8s}  {'Perusahaan':>12s}  {'Tenaga Kerja':>14s}")
    print("-" * 80)
    for r in rows2:
        print(f"{(r[0] or ''):20s} {(r[1] or ''):5s} {str(r[2] or ''):4s}  "
              f"{r[3]:>8}  {int(r[4]) if r[4] else 0:>12,}  {int(r[5]) if r[5] else 0:>14,}")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Normalisasi data BPS ke tabel fakta.")
    parser.add_argument("--keywords", nargs="+", help="Filter judul tabel (contoh: kabupaten 'tenaga kerja')")
    parser.add_argument("--ids", nargs="+", type=int, help="Table ID spesifik")
    parser.add_argument("--sample", action="store_true", help="Tampilkan contoh data saja")
    args = parser.parse_args()

    if args.sample:
        print_sample_query()
    else:
        run_normalization(table_ids=args.ids, keyword_filter=args.keywords)
        print_sample_query()
