import sqlite3

conn = sqlite3.connect("bps_data.db")
cursor = conn.cursor()

print("--- Status Tabel di Database ---")
cursor.execute("SELECT download_status, COUNT(*) FROM tabel_katalog GROUP BY download_status")
for status, count in cursor.fetchall():
    print(f"Status: {status} | Jumlah: {count}")

print("\n--- Contoh 5 Data Katalog Teratas ---")
cursor.execute("SELECT table_id, title, domain_name, download_status, file_path FROM tabel_katalog LIMIT 5")
for row in cursor.fetchall():
    print(row)

conn.close()
