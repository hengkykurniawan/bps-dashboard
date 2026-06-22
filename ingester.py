"""
ingester.py - BPS Data Ingestion Script
========================================
Membaca semua file yang sudah diunduh (Excel/HTML) dari folder downloads/
dan memasukkan isinya ke dalam tabel SQLite 'tabel_data'.

Desain:
  - Skema fleksibel: setiap baris data disimpan sebagai JSON agar dapat
    menampung berbagai struktur kolom dari ratusan tabel yang heterogen.
  - Setiap lembar (sheet) dari file Excel diproses secara terpisah.
  - Status ingesti disimpan di tabel katalog (kolom 'ingestion_status').
  - Script idempoten: bisa dijalankan ulang tanpa duplikasi data.
"""

import os
import re
import json
import sqlite3
import warnings
from datetime import datetime

import pandas as pd

# ─── Konfigurasi ─────────────────────────────────────────────────────────────

DATABASE_PATH = "bps_data.db"
DOWNLOAD_DIR = "downloads"

# Jumlah baris header yang dicoba saat membaca tabel (untuk tabel multi-header)
MAX_HEADER_ROWS = 3

# ─── Setup Database ───────────────────────────────────────────────────────────

def init_ingestion_schema(conn: sqlite3.Connection):
    """
    Menambahkan kolom ingestion_status ke tabel_katalog (jika belum ada)
    dan membuat tabel tabel_data untuk menyimpan baris data mentah.
    """
    cursor = conn.cursor()

    # Tambah kolom ingestion_status ke tabel katalog jika belum ada
    try:
        cursor.execute("ALTER TABLE tabel_katalog ADD COLUMN ingestion_status TEXT DEFAULT 'PENDING'")
        cursor.execute("ALTER TABLE tabel_katalog ADD COLUMN ingestion_rows INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE tabel_katalog ADD COLUMN ingestion_error TEXT")
        conn.commit()
        print("[DB] Kolom ingestion ditambahkan ke tabel_katalog.")
    except sqlite3.OperationalError:
        pass  # Kolom sudah ada

    # Buat tabel penyimpan data mentah
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tabel_data (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        table_id     INTEGER NOT NULL,
        domain_id    TEXT NOT NULL,
        domain_name  TEXT,
        title        TEXT,
        sheet_name   TEXT,
        row_index    INTEGER,
        data_json    TEXT NOT NULL,
        ingested_at  TEXT NOT NULL,
        FOREIGN KEY (table_id) REFERENCES tabel_katalog(table_id)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tabel_data_table_id ON tabel_data(table_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tabel_data_domain_id ON tabel_data(domain_id)")
    conn.commit()
    print("[DB] Tabel 'tabel_data' siap.")


# ─── Parsing Nama File ─────────────────────────────────────────────────────────

def parse_filename(filename: str) -> dict | None:
    """
    Mengekstrak metadata dari nama file.
    Format: {domain_id}_{domain_name}_{table_id}_{title}.{ext}
    Contoh: 3300_Jawa_Tengah_1060_Banyaknya_Perusahaan...xlsx
    """
    base = os.path.splitext(filename)[0]
    # Ambil domain_id (4 digit awal), domain_name, table_id (angka setelah domain_name)
    match = re.match(r'^(\d{4})_(.+?)_(\d+)_(.+)$', base)
    if not match:
        return None
    return {
        "domain_id":   match.group(1),
        "domain_name": match.group(2).replace("_", " "),
        "table_id":    int(match.group(3)),
        "title":       match.group(4).replace("_", " "),
    }


# ─── Pembaca File ──────────────────────────────────────────────────────────────

def flatten_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    """
    Meratakan MultiIndex kolom menjadi string tunggal.
    Contoh: ('Tahun', '2020') → 'Tahun_2020'
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(c).strip() for c in col if str(c) not in ("", "nan", "Unnamed: 0_level_0"))
            for col in df.columns
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membersihkan DataFrame: menghapus baris/kolom kosong total,
    meratakan header, dan mengonversi nilai ke tipe Python standar.
    """
    # Hapus baris dan kolom yang semuanya NaN
    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)

    # Rename kolom Unnamed
    cols = []
    for i, c in enumerate(df.columns):
        s = str(c).strip()
        if s.startswith("Unnamed:") or s == "nan":
            s = f"col_{i}"
        cols.append(s)
    df.columns = cols

    # Reset index
    df.reset_index(drop=True, inplace=True)
    return df


def read_excel_file(filepath: str) -> list[tuple[str, pd.DataFrame]]:
    """
    Membaca semua sheet dari file Excel.
    Mengembalikan list of (sheet_name, DataFrame).
    Mencoba berbagai jumlah baris header (0, 1, 2) untuk menangani
    tabel multi-header BPS.
    Fallback chain: openpyxl → xlrd (via pd.ExcelFile) → xlrd.open_workbook
    (untuk file OLE2/xls97 yang diberi ekstensi .xlsx) → read_html.
    """
    results = []
    warnings.filterwarnings("ignore", category=UserWarning)

    xl = None
    try:
        xl = pd.ExcelFile(filepath, engine="openpyxl")
    except Exception:
        try:
            xl = pd.ExcelFile(filepath, engine="xlrd")
        except Exception:
            # OLE2 (.xls97) files named as .xlsx: xlrd 2.x checks extension via
            # pd.ExcelFile, tapi xlrd.open_workbook() tidak peduli ekstensi.
            try:
                import xlrd as _xlrd
                wb = _xlrd.open_workbook(filepath)
                for sheet_name in wb.sheet_names():
                    ws = wb.sheet_by_name(sheet_name)
                    if ws.nrows < 2:
                        continue
                    # Baca semua baris ke list-of-list
                    raw = [[ws.cell_value(r, c) for c in range(ws.ncols)]
                           for r in range(ws.nrows)]
                    _df = pd.DataFrame(raw[1:], columns=raw[0])
                    _df = flatten_multiindex(_df)
                    _df = clean_dataframe(_df)
                    if not _df.empty and len(_df.columns) > 1:
                        results.append((str(sheet_name), _df))
                if results:
                    return results
            except Exception:
                pass
            # Last resort: coba baca sebagai HTML (file berisi WAF HTML block)
            print(f"   [INFO] Bukan Excel murni, mencoba baca sebagai HTML...")
            return read_html_file(filepath)


    if xl is None:
        return results

    for sheet_name in xl.sheet_names:
        df = None
        for header_opt in [0, [0, 1], [0, 1, 2]]:
            try:
                _df = xl.parse(sheet_name, header=header_opt)
                _df = flatten_multiindex(_df)
                _df = clean_dataframe(_df)
                if not _df.empty and len(_df.columns) > 1:
                    df = _df
                    break
            except Exception:
                continue

        if df is not None and not df.empty:
            results.append((str(sheet_name), df))

    return results



def read_html_file(filepath: str) -> list[tuple[str, pd.DataFrame]]:
    """
    Membaca tabel dari file HTML (fallback dari API view BPS).
    Mengembalikan list of (sheet_name, DataFrame).
    """
    results = []
    try:
        tables = pd.read_html(filepath, flavor="lxml", thousands=".", decimal=",")
    except Exception:
        try:
            tables = pd.read_html(filepath, thousands=".", decimal=",")
        except Exception as e:
            print(f"   [ERROR] Tidak dapat membaca HTML: {e}")
            return results

    for i, df in enumerate(tables):
        df = flatten_multiindex(df)
        df = clean_dataframe(df)
        if not df.empty:
            results.append((f"tabel_{i+1}", df))

    return results


# ─── Serialisasi JSON ──────────────────────────────────────────────────────────

def row_to_json(row: pd.Series) -> str:
    """Mengonversi satu baris pandas ke JSON string yang aman."""
    d = {}
    for k, v in row.items():
        # Konversi tipe numpy/pandas ke Python standar
        if pd.isna(v) if not isinstance(v, (list, dict)) else False:
            d[str(k)] = None
        elif hasattr(v, "item"):
            d[str(k)] = v.item()
        else:
            d[str(k)] = str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v
    return json.dumps(d, ensure_ascii=False)


# ─── Proses Ingesti ────────────────────────────────────────────────────────────

def ingest_file(conn: sqlite3.Connection, filepath: str, meta: dict) -> tuple[int, str | None]:
    """
    Memproses satu file dan memasukkan datanya ke tabel_data.
    Mengembalikan (jumlah_baris, pesan_error).
    """
    cursor = conn.cursor()
    ext = os.path.splitext(filepath)[1].lower()
    now = datetime.now().isoformat()

    # Baca file sesuai tipe
    if ext in (".xlsx", ".xls"):
        sheets = read_excel_file(filepath)
    elif ext == ".html":
        sheets = read_html_file(filepath)
    else:
        return 0, f"Ekstensi tidak dikenal: {ext}"

    if not sheets:
        return 0, "Tidak ada data yang dapat dibaca dari file"

    total_rows = 0
    for sheet_name, df in sheets:
        rows_inserted = 0
        for row_idx, row in df.iterrows():
            try:
                data_json = row_to_json(row)
                cursor.execute("""
                    INSERT INTO tabel_data
                        (table_id, domain_id, domain_name, title, sheet_name, row_index, data_json, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta["table_id"],
                    meta["domain_id"],
                    meta["domain_name"],
                    meta["title"],
                    sheet_name,
                    int(row_idx),
                    data_json,
                    now,
                ))
                rows_inserted += 1
            except Exception as e:
                print(f"   [WARN] Gagal memasukkan baris {row_idx}: {e}")

        total_rows += rows_inserted

    conn.commit()
    return total_rows, None


def run_ingestion(force: bool = False):
    """
    Proses utama ingesti: baca semua file dari downloads/,
    parse metadata dari nama file, dan masukkan data ke database.

    Args:
        force: Jika True, proses ulang file yang sudah diingesti sebelumnya.
    """
    if not os.path.exists(DATABASE_PATH):
        print(f"[ERROR] Database tidak ditemukan: {DATABASE_PATH}")
        print("       Jalankan downloader.py terlebih dahulu.")
        return

    if not os.path.isdir(DOWNLOAD_DIR):
        print(f"[ERROR] Folder downloads tidak ditemukan: {DOWNLOAD_DIR}")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    init_ingestion_schema(conn)

    # Ambil status ingesti yang sudah ada
    cursor = conn.cursor()
    cursor.execute("SELECT table_id, ingestion_status FROM tabel_katalog")
    ingestion_status_map = {row[0]: row[1] for row in cursor.fetchall()}

    all_files = sorted(os.listdir(DOWNLOAD_DIR))
    valid_files = [f for f in all_files if f.endswith((".xlsx", ".xls", ".html"))]

    print(f"\n{'='*60}")
    print(f"  BPS Data Ingester")
    print(f"{'='*60}")
    print(f"  Total file ditemukan : {len(valid_files)}")
    print(f"  Mode                 : {'Force (proses ulang semua)' if force else 'Incremental (skip yang sudah selesai)'}")
    print(f"{'='*60}\n")

    success_count = 0
    skip_count = 0
    fail_count = 0
    total_rows = 0

    for i, filename in enumerate(valid_files, 1):
        meta = parse_filename(filename)
        if meta is None:
            print(f"[{i}/{len(valid_files)}] SKIP: Nama file tidak dikenali → {filename}")
            skip_count += 1
            continue

        table_id = meta["table_id"]
        current_status = ingestion_status_map.get(table_id)

        # Skip file yang sudah berhasil diingesti (kecuali mode force)
        if not force and current_status == "DONE":
            skip_count += 1
            continue

        filepath = os.path.join(DOWNLOAD_DIR, filename)
        short_title = meta["title"][:55] + "..." if len(meta["title"]) > 55 else meta["title"]
        print(f"[{i}/{len(valid_files)}] [{meta['domain_name']}] Tabel {table_id}: {short_title}")

        # Hapus data lama jika ada (untuk idempoten)
        conn.execute("DELETE FROM tabel_data WHERE table_id = ?", (table_id,))
        conn.commit()

        rows_inserted, error = ingest_file(conn, filepath, meta)

        if error:
            conn.execute("""
                UPDATE tabel_katalog
                SET ingestion_status = 'ERROR', ingestion_error = ?, ingestion_rows = 0
                WHERE table_id = ?
            """, (error, table_id))
            conn.commit()
            print(f"   [ERROR] {error}")
            fail_count += 1
        else:
            conn.execute("""
                UPDATE tabel_katalog
                SET ingestion_status = 'DONE', ingestion_rows = ?, ingestion_error = NULL
                WHERE table_id = ?
            """, (rows_inserted, table_id))
            conn.commit()
            print(f"   [OK] {rows_inserted} baris dimasukkan")
            success_count += 1
            total_rows += rows_inserted

    # ── Putaran ke-2: proses tabel PENDING/ERROR berdasarkan file_path di DB ──
    # Menangani file repaired yang namanya tidak sesuai konvensi parse_filename()
    cursor.execute("""
        SELECT table_id, domain_id, domain_name, title, file_path
        FROM tabel_katalog
        WHERE (ingestion_status = 'PENDING' OR ingestion_status = 'ERROR')
          AND file_path IS NOT NULL
    """)
    db_pending = cursor.fetchall()

    if db_pending:
        print(f"\n--- Putaran ke-2: {len(db_pending)} tabel dari DB (file_path) ---\n")
        for table_id, domain_id, domain_name, title, file_path in db_pending:
            if not os.path.exists(file_path):
                print(f"  SKIP Tabel {table_id}: file tidak ditemukan -> {file_path}")
                continue
            meta = {
                "table_id": table_id,
                "domain_id": domain_id,
                "domain_name": domain_name,
                "title": (title or "")[:120],
            }
            short_title = meta["title"][:55] + "..." if len(meta["title"]) > 55 else meta["title"]
            print(f"  [{domain_name}] Tabel {table_id}: {short_title}")
            conn.execute("DELETE FROM tabel_data WHERE table_id = ?", (table_id,))
            conn.commit()
            rows_inserted, error = ingest_file(conn, file_path, meta)
            if error:
                conn.execute("""
                    UPDATE tabel_katalog
                    SET ingestion_status = 'ERROR', ingestion_error = ?, ingestion_rows = 0
                    WHERE table_id = ?
                """, (error, table_id))
                conn.commit()
                print(f"   [ERROR] {error}")
                fail_count += 1
            else:
                conn.execute("""
                    UPDATE tabel_katalog
                    SET ingestion_status = 'DONE', ingestion_rows = ?, ingestion_error = NULL
                    WHERE table_id = ?
                """, (rows_inserted, table_id))
                conn.commit()
                print(f"   [OK] {rows_inserted} baris dimasukkan")
                success_count += 1
                total_rows += rows_inserted

    conn.close()

    print(f"\n{'='*60}")
    print(f"  Ingesti Selesai")
    print(f"{'='*60}")
    print(f"  Berhasil   : {success_count} file")
    print(f"  Dilewati   : {skip_count} file")
    print(f"  Gagal      : {fail_count} file")
    print(f"  Total baris: {total_rows:,}")
    print(f"{'='*60}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest BPS downloaded files into SQLite database."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proses ulang semua file, termasuk yang sudah selesai diingesti."
    )
    args = parser.parse_args()

    run_ingestion(force=args.force)
