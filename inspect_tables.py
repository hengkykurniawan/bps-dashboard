"""
inspect_tables.py - Lihat data mentah dari beberapa tabel untuk rancangan normalizer.
"""
import sqlite3, json

conn = sqlite3.connect("bps_data.db")

# Tabel yang menarik untuk dinormalisasi
SAMPLE_IDS = [1698, 886, 1969, 1668, 257]  # Perusahaan+TK+Investasi per Kab/Kota

for table_id in SAMPLE_IDS:
    info = conn.execute(
        "SELECT domain_name, title, ingestion_rows FROM tabel_katalog WHERE table_id=?",
        (table_id,)
    ).fetchone()
    if not info:
        continue
    domain, title, n = info
    print(f"\n{'='*70}")
    print(f"Tabel {table_id} [{domain}] ({n} baris)")
    print(f"Judul: {title}")
    print(f"{'-'*70}")

    rows = conn.execute(
        "SELECT row_index, data_json FROM tabel_data WHERE table_id=? ORDER BY row_index LIMIT 12",
        (table_id,)
    ).fetchall()
    for ri, dj in rows:
        d = json.loads(dj)
        vals = list(d.values())
        print(f"  [{ri:2d}] {vals}")

conn.close()
