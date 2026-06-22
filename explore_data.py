"""
explore_data.py - Analisis pola kolom di tabel_data untuk rancangan normalisasi.
"""
import sqlite3, json, re
from collections import Counter, defaultdict

conn = sqlite3.connect("bps_data.db")

# ── 1. Distribusi jumlah baris per tabel ──────────────────────────────────────
print("=== DISTRIBUSI BARIS PER TABEL ===")
rows = conn.execute("""
    SELECT ingestion_rows, COUNT(*) as n_tabel
    FROM tabel_katalog WHERE ingestion_status='DONE'
    GROUP BY
      CASE
        WHEN ingestion_rows <= 5  THEN '1-5'
        WHEN ingestion_rows <= 15 THEN '6-15'
        WHEN ingestion_rows <= 30 THEN '16-30'
        WHEN ingestion_rows <= 60 THEN '31-60'
        ELSE '61+'
      END
    ORDER BY ingestion_rows
""").fetchall()
buckets = Counter()
for n_rows, n_tabel in conn.execute(
    "SELECT ingestion_rows, 1 FROM tabel_katalog WHERE ingestion_status='DONE'"
):
    if   n_rows <= 5:  buckets["  1-5 baris"]  += 1
    elif n_rows <= 15: buckets[" 6-15 baris"]  += 1
    elif n_rows <= 30: buckets["16-30 baris"]  += 1
    elif n_rows <= 60: buckets["31-60 baris"]  += 1
    else:              buckets["61+   baris"]  += 1
for k, v in sorted(buckets.items()):
    print(f"  {k}: {v} tabel")

# ── 2. Kata kunci paling umum di judul tabel ─────────────────────────────────
print("\n=== KATA KUNCI UMUM DI JUDUL ===")
kw_counter = Counter()
KEYWORDS = [
    "Jumlah Perusahaan", "Tenaga Kerja", "Nilai Produksi", "Nilai Output",
    "Biaya Input", "Nilai Tambah", "Investasi", "Bahan Bakar",
    "Mikro dan Kecil", "Besar dan Sedang", "KabupatenKota", "KBLI",
    "Klasifikasi Industri", "Perdagangan Antar Pulau", "Sensus Ekonomi",
]
for (title,) in conn.execute("SELECT title FROM tabel_katalog WHERE ingestion_status='DONE'"):
    for kw in KEYWORDS:
        if kw.lower() in title.lower():
            kw_counter[kw] += 1
for kw, cnt in kw_counter.most_common():
    print(f"  {cnt:3d}x  {kw}")

# ── 3. Sample kolom dari 10 tabel terpopuler ─────────────────────────────────
print("\n=== KOLOM DARI 10 TABEL TERPOPULER (baris pertama) ===")
top_tables = conn.execute("""
    SELECT k.table_id, k.domain_name, k.title, k.ingestion_rows
    FROM tabel_katalog k
    WHERE ingestion_status='DONE'
    ORDER BY ingestion_rows DESC LIMIT 10
""").fetchall()

for table_id, domain, title, n_rows in top_tables:
    # Ambil baris pertama (row_index=0) untuk lihat kolom
    row = conn.execute(
        "SELECT data_json FROM tabel_data WHERE table_id=? ORDER BY row_index LIMIT 1",
        (table_id,)
    ).fetchone()
    if row:
        d = json.loads(row[0])
        cols = list(d.keys())
        print(f"\n  [{domain}] Tabel {table_id} ({n_rows} baris): {title[:55]}")
        print(f"  Kolom: {cols}")
        # Tampilkan nilai baris ke-2 (data actual, bukan header)
        row2 = conn.execute(
            "SELECT data_json FROM tabel_data WHERE table_id=? AND row_index=1",
            (table_id,)
        ).fetchone()
        if row2:
            d2 = json.loads(row2[0])
            print(f"  Baris-2: { {k: str(v)[:30] for k,v in list(d2.items())[:6]} }")

# ── 4. Tabel bertipe "Jumlah Perusahaan + Tenaga Kerja menurut KabupatenKota" ─
print("\n\n=== TABEL TIPE: Perusahaan+TK per Kab/Kota ===")
q = conn.execute("""
    SELECT table_id, domain_name, title, ingestion_rows
    FROM tabel_katalog
    WHERE ingestion_status='DONE'
      AND lower(title) LIKE '%jumlah perusahaan%'
      AND lower(title) LIKE '%tenaga kerja%'
      AND lower(title) LIKE '%kabupaten%'
    ORDER BY domain_name, table_id
""").fetchall()
print(f"  Ditemukan {len(q)} tabel:")
for r in q[:15]:
    print(f"  [{r[1]:15s}] ID {r[0]:5d} ({r[3]:3d} baris) {r[2][:60]}")

conn.close()
