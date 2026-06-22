"""
repair_corrupt.py - Memperbaiki file Excel yang korup dengan mengambil ulang
data melalui BPS API view endpoint (HTML fallback).
"""
import os
import html as html_parser
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

BPS_API_KEY = os.getenv("BPS_API_KEY", "")
DATABASE_PATH = "bps_data.db"
DOWNLOAD_DIR = "downloads"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_html_from_api(table_id: int, domain_id: str, out_path: str) -> bool:
    """Ambil data HTML tabel dari BPS API view, simpan ke out_path."""
    url = (f"https://webapi.bps.go.id/v1/api/view/model/statictable"
           f"/domain/{domain_id}/id/{table_id}/lang/ind/key/{BPS_API_KEY}/")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK" and "data" in data:
            table_html = data["data"].get("table", "")
            if table_html:
                table_html = html_parser.unescape(table_html)
                full_html = (f"<!doctype html><html><head><meta charset='utf-8'>"
                             f"<title>{data['data'].get('title','')}</title></head>"
                             f"<body>{table_html}</body></html>")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(full_html)
                print(f"  -> Berhasil mengambil HTML ({len(full_html)} chars)")
                return True
    except Exception as e:
        print(f"  -> ERROR: {e}")
    return False

def main():
    conn = sqlite3.connect(DATABASE_PATH)
    # Ambil semua tabel dengan status ERROR
    rows = conn.execute(
        "SELECT table_id, domain_id, domain_name, file_path "
        "FROM tabel_katalog WHERE ingestion_status = 'ERROR'"
    ).fetchall()
    conn.close()

    print(f"Ditemukan {len(rows)} tabel ERROR untuk diperbaiki.\n")

    for table_id, domain_id, domain_name, old_path in rows:
        print(f"Tabel {table_id} [{domain_name}]:")

        # Buat path HTML baru
        if old_path:
            new_path = os.path.splitext(old_path)[0] + "_repaired.html"
        else:
            new_path = os.path.join(DOWNLOAD_DIR, f"{domain_id}_{table_id}_repaired.html")

        ok = fetch_html_from_api(table_id, domain_id, new_path)
        if ok:
            # Update file_path di database ke file HTML yang baru
            conn2 = sqlite3.connect(DATABASE_PATH)
            conn2.execute(
                "UPDATE tabel_katalog SET file_path=?, download_status='DOWNLOADED', "
                "ingestion_status='PENDING' WHERE table_id=?",
                (new_path, table_id)
            )
            conn2.commit()
            conn2.close()
            print(f"  -> DB diperbarui: {new_path}")
        else:
            print(f"  -> Gagal memperbaiki tabel {table_id}")

    print("\nSelesai. Jalankan ingester.py untuk mengingesti file yang sudah diperbaiki.")

if __name__ == "__main__":
    main()
