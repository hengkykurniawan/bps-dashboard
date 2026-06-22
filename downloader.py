import os
import re
import html as html_parser
import requests
from dotenv import load_dotenv
from database import init_db, insert_or_update_table, get_pending_downloads, update_download_status

# Load configuration from .env file
load_dotenv()

BPS_API_KEY = os.getenv("BPS_API_KEY", "YOUR_BPS_API_KEY_HERE")
BPS_SUBJECT = os.getenv("BPS_SUBJECT", "9")  # Default ke subjek 9 (IBS)
DATABASE_PATH = os.getenv("DATABASE_PATH", "bps_data.db")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")

# Headers to mimic a real browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Daftar kode wilayah provinsi di Indonesia (BPS Domain ID format 2-digit + 00)
DOMAINS = [
    ("0000", "Nasional"),
    ("1100", "Aceh"),
    ("1200", "Sumatera Utara"),
    ("1300", "Sumatera Barat"),
    ("1400", "Riau"),
    ("1500", "Jambi"),
    ("1600", "Sumatera Selatan"),
    ("1700", "Bengkulu"),
    ("1800", "Lampung"),
    ("1900", "Kep. Bangka Belitung"),
    ("2100", "Kep. Riau"),
    ("3100", "DKI Jakarta"),
    ("3200", "Jawa Barat"),
    ("3300", "Jawa Tengah"),
    ("3400", "DI Yogyakarta"),
    ("3500", "Jawa Timur"),
    ("3600", "Banten"),
    ("5100", "Bali"),
    ("5200", "Nusa Tenggara Barat"),
    ("5300", "Nusa Tenggara Timur"),
    ("6100", "Kalimantan Barat"),
    ("6200", "Kalimantan Tengah"),
    ("6300", "Kalimantan Selatan"),
    ("6400", "Kalimantan Timur"),
    ("6500", "Kalimantan Utara"),
    ("7100", "Sulawesi Utara"),
    ("7200", "Sulawesi Tengah"),
    ("7300", "Sulawesi Selatan"),
    ("7400", "Sulawesi Tenggara"),
    ("7500", "Gorontalo"),
    ("7600", "Sulawesi Barat"),
    ("8100", "Maluku"),
    ("8200", "Maluku Utara"),
    ("9100", "Papua Barat"),
    ("9400", "Papua")
]

def sanitize_filename(filename):
    """Membersihkan nama file dari karakter ilegal Windows/Linux."""
    # Hapus karakter kontrol non-printable (seperti \x02) yang membuat Windows error
    clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', "", filename)
    # Hapus karakter ilegal Windows
    clean = re.sub(r'[\\/*?:"<>|]', "", clean)
    return clean.replace(" ", "_")[:120]

def fetch_and_save_metadata():
    """
    Mengambil daftar tabel statis untuk subjek tertentu dari BPS Web API 
    di seluruh domain provinsi, lalu menyimpannya ke database SQLite.
    """
    if BPS_API_KEY == "YOUR_BPS_API_KEY_HERE" or not BPS_API_KEY:
        print("[ERROR] Harap konfigurasi BPS_API_KEY Anda di file .env terlebih dahulu.")
        return False
        
    print(f"Memulai pengambilan metadata untuk Subjek: {BPS_SUBJECT} di seluruh Indonesia...")
    
    total_added = 0
    
    for domain_id, domain_name in DOMAINS:
        print(f"\nMengecek wilayah: {domain_name} ({domain_id})...")
        page = 1
        
        while True:
            # Endpoint URL BPS Web API untuk list statictable
            url = f"https://webapi.bps.go.id/v1/api/list/model/statictable/domain/{domain_id}/subject/{BPS_SUBJECT}/page/{page}/key/{BPS_API_KEY}/"
            
            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                response.raise_for_status()
                res_json = response.json()
            except Exception as e:
                print(f"   [ERROR] Gagal menghubungi API BPS untuk wilayah {domain_name} di Halaman {page}: {e}")
                break
                
            status = res_json.get("status")
            availability = res_json.get("data-availability")
            
            # Jika domain ini tidak memiliki tabel untuk subjek ini
            if status != "OK" or availability != "available":
                break
                
            data = res_json.get("data", [])
            
            # BPS API mengembalikan list [pagination_dict, tables_list] jika sukses
            if len(data) > 1 and isinstance(data[1], list):
                tables_list = data[1]
            elif len(data) == 1 and isinstance(data[0], list):
                tables_list = data[0]
            else:
                tables_list = data
                
            if not tables_list or not isinstance(tables_list, list):
                break
                
            page_added = 0
            for item in tables_list:
                table_id = item.get("table_id")
                title = item.get("title")
                excel_url = item.get("excel")
                
                if not table_id or not title:
                    continue
                    
                table_data = {
                    "table_id": int(table_id),
                    "title": title,
                    "subject_id": int(BPS_SUBJECT),
                    "domain_id": domain_id,
                    "domain_name": domain_name,
                    "excel_url": excel_url
                }
                
                inserted = insert_or_update_table(DATABASE_PATH, table_data)
                if inserted:
                    page_added += 1
                    
            total_added += page_added
            if page_added > 0:
                print(f"   Halaman {page}: Berhasil menambahkan {page_added} tabel baru.")
            
            # Cek apakah ada halaman berikutnya (berdasarkan metadata pagination)
            pagination = data[0] if data and isinstance(data[0], dict) else {}
            total_pages = pagination.get("pages", 1)
            
            if page >= total_pages:
                break
            page += 1
            
    print(f"\n[DONE] Proses metadata selesai. Total {total_added} tabel baru dimasukkan ke database.")
    return True

def download_via_api_view(table_id, domain_id, local_path_html):
    """
    Mengunduh isi tabel dalam bentuk HTML langsung dari API view BPS 
    sebagai fallback jika file Excel tidak dapat diunduh.
    """
    url = f"https://webapi.bps.go.id/v1/api/view/model/statictable/domain/{domain_id}/id/{table_id}/lang/ind/key/{BPS_API_KEY}/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        res_json = response.json()
        
        if res_json.get("status") == "OK" and "data" in res_json:
            data = res_json["data"]
            table_html_escaped = data.get("table")
            
            if table_html_escaped:
                # Unescape HTML (misal &lt; menjadi <)
                table_html = html_parser.unescape(table_html_escaped)
                
                # Bungkus dengan HTML body agar valid dan mudah dibaca
                full_html = f"<!doctype html><html><head><meta charset='utf-8'><title>{data.get('title')}</title></head><body>{table_html}</body></html>"
                
                with open(local_path_html, "w", encoding="utf-8") as f:
                    f.write(full_html)
                    
                file_size = os.path.getsize(local_path_html)
                return local_path_html, file_size
    except Exception as e:
        print(f"   [FALLBACK ERROR] Gagal mengambil HTML tabel melalui API: {e}")
        
    return None, None

def download_pending_files():
    """
    Membaca database untuk tabel dengan status PENDING/FAILED, 
    mengunduh file Excel-nya, atau mengambil isi HTML tabel melalui API view jika gagal.
    """
    pending_tables = get_pending_downloads(DATABASE_PATH)
    
    if not pending_tables:
        print("\nSemua berkas data telah berhasil diunduh.")
        return
        
    print(f"\nDitemukan {len(pending_tables)} tabel yang perlu diunduh.")
    
    # Pastikan folder downloads utama ada
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    success_count = 0
    failed_count = 0
    
    for table in pending_tables:
        table_id = table["table_id"]
        title = table["title"]
        domain_id = table["domain_id"]
        domain_name = table["domain_name"]
        excel_url = table["excel_url"]
        
        safe_title = sanitize_filename(title)
        safe_domain = sanitize_filename(domain_name)
        
        # Path lokal untuk Excel dan HTML (fallback)
        filename_xls = f"{domain_id}_{safe_domain}_{table_id}_{safe_title}.xlsx"
        filename_html = f"{domain_id}_{safe_domain}_{table_id}_{safe_title}.html"
        
        local_path_xls = os.path.join(DOWNLOAD_DIR, filename_xls)
        local_path_html = os.path.join(DOWNLOAD_DIR, filename_html)
        
        # Cek apakah ini tautan mati (archive.bps.go.id)
        is_legacy_archive = False
        if excel_url and "archive.bps.go.id" in excel_url:
            is_legacy_archive = True
            
        downloaded = False
        
        # Skenario 1: Coba unduh Excel (hanya untuk tautan non-legacy/provinsi)
        if excel_url and not is_legacy_archive:
            # Perbaiki domain (web-api -> webapi)
            rewritten_url = excel_url.replace("web-api.bps.go.id", "webapi.bps.go.id")
            
            # Ubah skema ke HTTPS dengan fallback HTTP
            if rewritten_url.startswith("http://"):
                # webapi.bps.go.id berjalan baik di HTTP port 80 maupun HTTPS
                pass
                
            print(f"Mengunduh [{domain_name}] Excel Tabel {table_id}: {title[:50]}...")
            try:
                # Menggunakan verify=False untuk menghindari masalah SSL certificate di webapi
                response = requests.get(rewritten_url, headers=HEADERS, timeout=25, verify=False, stream=True)
                
                # Cek jika dialihkan ke halaman pemblokiran WAF atau status error
                content_type = response.headers.get("Content-Type", "")
                if response.status_code == 200 and "text/html" not in content_type:
                    with open(local_path_xls, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                
                    file_size = os.path.getsize(local_path_xls)
                    update_download_status(DATABASE_PATH, table_id, "DOWNLOADED", local_path_xls, file_size)
                    print(f"   [SUCCESS] Excel disimpan di {local_path_xls} ({file_size} bytes)")
                    success_count += 1
                    downloaded = True
                else:
                    print(f"   [WARNING] Excel tidak dapat diunduh (WAF block / Status: {response.status_code})")
            except Exception as e:
                print(f"   [WARNING] Gagal mengunduh Excel: {e}")
                
        # Skenario 2: Fallback ke API View (ambil data HTML)
        if not downloaded:
            print(f"Mengambil [{domain_name}] HTML Tabel {table_id} (Fallback API)...")
            path, size = download_via_api_view(table_id, domain_id, local_path_html)
            if path:
                update_download_status(DATABASE_PATH, table_id, "DOWNLOADED", path, size)
                print(f"   [SUCCESS] HTML disimpan di {path} ({size} bytes)")
                success_count += 1
                downloaded = True
            else:
                update_download_status(DATABASE_PATH, table_id, "FAILED")
                print(f"   [FAILED] Gagal mendapatkan data untuk Tabel {table_id}")
                failed_count += 1
                
    print(f"\nProses unduhan selesai. Berhasil: {success_count}, Gagal: {failed_count}")

def main():
    # 1. Inisialisasi database SQLite
    init_db(DATABASE_PATH)
    
    # 2. Ambil list tabel dari API BPS (subjek 9) di seluruh provinsi
    success = fetch_and_save_metadata()
    
    if success:
        # 3. Unduh berkas data (Excel / HTML fallback) untuk tabel yang dikumpulkan
        download_pending_files()

if __name__ == "__main__":
    main()
