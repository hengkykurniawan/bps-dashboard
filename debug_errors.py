"""Debug script for OLE2 tables 34 and 35."""
import sqlite3, xlrd, pandas as pd

conn = sqlite3.connect('bps_data.db')
rows = conn.execute("SELECT table_id, title, file_path FROM tabel_katalog WHERE table_id IN (34,35)").fetchall()
conn.close()

for tid, title, fpath in rows:
    print(f"\n=== Tabel {tid}: {title[:60]} ===")
    print(f"File: {fpath}")
    try:
        wb = xlrd.open_workbook(fpath)
        print(f"Sheet names: {wb.sheet_names()}")
        for sname in wb.sheet_names():
            ws = wb.sheet_by_name(sname)
            print(f"  Sheet '{sname}': nrows={ws.nrows}, ncols={ws.ncols}")
            if ws.nrows > 0:
                print(f"  Row 0 sample: {[ws.cell_value(0,c) for c in range(min(5, ws.ncols))]}")
            if ws.nrows > 1:
                print(f"  Row 1 sample: {[ws.cell_value(1,c) for c in range(min(5, ws.ncols))]}")
    except Exception as e:
        print(f"  xlrd ERROR: {e}")
