# BPS Data Downloader

Alur kerja (workflow) Python untuk mengunduh tabel statistik dari situs web Badan Pusat Statistik (BPS) menggunakan Web API resmi dan menyimpannya ke database SQLite lokal.

## Setup & Instalasi

1. Pastikan Anda memiliki Python 3.8+ terinstal di sistem Anda.
2. Buat Virtual Environment (opsional namun disarankan):
   ```bash
   python -m venv venv
   # Di Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # Di macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
4. Dapatkan API Key BPS Anda melalui [BPS Web API Portal](https://webapi.bps.go.id/developer/).
5. Edit file `.env` dan ganti `YOUR_BPS_API_KEY_HERE` dengan API Key BPS Anda.

## Cara Menggunakan

Jalankan script downloader utama:
```bash
python downloader.py
```

Script akan:
1. Menghubungi BPS Web API untuk mendapatkan daftar tabel statistik subjek yang ditentukan (Default: `531` - Industri Besar dan Sedang).
2. Memasukkan metadata setiap tabel ke dalam database SQLite lokal (`bps_data.db`) pada tabel `tabel_katalog`.
3. Mengunduh berkas Excel dari tabel-tabel yang belum terunduh ke direktori `downloads/`.
4. Memperbarui status unduhan di database.
