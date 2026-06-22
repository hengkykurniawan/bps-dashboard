import sqlite3
import pandas as pd

def export_data():
    print("Mengambil data dari fact_industri_wilayah...")
    conn = sqlite3.connect("bps_data.db")
    
    # Ambil data fakta
    df = pd.read_sql_query("""
        SELECT 
            domain_name AS Provinsi,
            wilayah AS Kabupaten_Kota,
            tahun AS Tahun,
            jenis_industri AS Jenis_Industri,
            n_perusahaan AS Jumlah_Perusahaan,
            tenaga_kerja AS Jumlah_Tenaga_Kerja,
            investasi_ribu_rp AS Investasi_Ribu_Rp,
            nilai_produksi_ribu_rp AS Nilai_Produksi_Ribu_Rp,
            source_title AS Sumber_Tabel
        FROM fact_industri_wilayah
        ORDER BY Provinsi, Kabupaten_Kota, Tahun
    """, conn)
    
    conn.close()
    
    if df.empty:
        print("Tidak ada data untuk diekspor.")
        return

    print(f"Berhasil mengambil {len(df)} baris data.")
    
    # Bersihkan karakter ilegal yang tidak disukai Excel (seperti control characters)
    import re
    def clean_illegal_chars(val):
        if isinstance(val, str):
            # Hapus karakter kontrol ASCII (kecuali tab, newline, carriage return)
            return re.sub(r'[\000-\010]|[\013-\014]|[\016-\037]', '', val)
        return val
        
    for col in df.select_dtypes(include=['object']):
        df[col] = df[col].apply(clean_illegal_chars)
    
    # Ekspor ke CSV
    csv_filename = "hasil_normalisasi_bps.csv"
    df.to_csv(csv_filename, index=False)
    print(f"Data diekspor ke: {csv_filename}")
    
    # Ekspor ke Excel
    excel_filename = "hasil_normalisasi_bps.xlsx"
    try:
        df.to_excel(excel_filename, index=False)
        print(f"Data diekspor ke: {excel_filename}")
    except Exception as e:
        print(f"Gagal mengekspor ke Excel: {e}")
    
    print("\nSelesai! File ekspor siap digunakan.")

if __name__ == "__main__":
    export_data()

