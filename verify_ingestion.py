import sqlite3, json

conn = sqlite3.connect('bps_data.db')

print('=== RINGKASAN INGESTI ===')
for row in conn.execute("SELECT ingestion_status, COUNT(*), SUM(ingestion_rows) FROM tabel_katalog GROUP BY ingestion_status"):
    print(f'  Status: {row[0]:10s} | File: {row[1]:4d} | Baris: {row[2]}')

print()
print('=== 5 TABEL DENGAN DATA TERBANYAK ===')
for row in conn.execute('SELECT table_id, domain_name, title, ingestion_rows FROM tabel_katalog WHERE ingestion_status="DONE" ORDER BY ingestion_rows DESC LIMIT 5'):
    print(f'  ID {row[0]:5d} [{row[1]:15s}] {row[2][:55]} -> {row[3]} baris')

print()
print('=== CONTOH DATA DARI TABEL 1081 (Nasional - Nilai Output IBS) ===')
for row in conn.execute('SELECT data_json FROM tabel_data WHERE table_id=1081 LIMIT 3'):
    d = json.loads(row[0])
    print(' ', json.dumps(d, ensure_ascii=False)[:130])

print()
print('=== FILE GAGAL (ERROR) ===')
for row in conn.execute("SELECT table_id, domain_name, ingestion_error FROM tabel_katalog WHERE ingestion_status='ERROR'"):
    print(f'  ID {row[0]:5d} [{row[1]}]: {row[2]}')

conn.close()
