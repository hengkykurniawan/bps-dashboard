import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

# Konfigurasi Halaman & Tema BPS
st.set_page_config(
    page_title="Dashboard BPS - Industri",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for BPS Blue Theme
st.markdown("""
<style>
    .stApp {
        background-color: #F8F9FA;
    }
    .main-header {
        color: #004F98; /* BPS Primary Blue */
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 700;
        margin-bottom: 0px;
    }
    .sub-header {
        color: #00A3E0; /* BPS Light Blue */
        font-size: 1.2rem;
        margin-top: 0px;
        margin-bottom: 30px;
    }
    .metric-container {
        background-color: white;
        border-top: 4px solid #004F98;
        border-radius: 5px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div[data-testid="stMetricValue"] {
        color: #004F98;
    }
</style>
""", unsafe_allow_html=True)

# 1. Mengambil data
@st.cache_data
def load_data():
    conn = sqlite3.connect("bps_data.db")
    query = """
        SELECT 
            domain_name AS Provinsi,
            wilayah AS Kabupaten_Kota,
            tahun AS Tahun,
            jenis_industri AS Jenis_Industri,
            n_perusahaan AS Jumlah_Perusahaan,
            tenaga_kerja AS Jumlah_Tenaga_Kerja,
            investasi_ribu_rp AS Investasi_Ribu_Rp,
            nilai_produksi_ribu_rp AS Nilai_Produksi_Ribu_Rp
        FROM fact_industri_wilayah
        WHERE Jumlah_Tenaga_Kerja IS NOT NULL OR Jumlah_Perusahaan IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Cleaning data types
    df['Tahun'] = pd.to_numeric(df['Tahun'], errors='coerce')
    df['Jumlah_Perusahaan'] = pd.to_numeric(df['Jumlah_Perusahaan'], errors='coerce')
    df['Jumlah_Tenaga_Kerja'] = pd.to_numeric(df['Jumlah_Tenaga_Kerja'], errors='coerce')
    df['Nilai_Produksi_Ribu_Rp'] = pd.to_numeric(df['Nilai_Produksi_Ribu_Rp'], errors='coerce')
    df = df.dropna(subset=['Provinsi', 'Tahun'])
    df['Tahun'] = df['Tahun'].astype(int)
    
    return df

df = load_data()

# ==============================================================================
# SIDEBAR (FILTER)
# ==============================================================================
st.sidebar.markdown("### ⚙️ Filter Data")

# Filter Tahun
min_year = int(df['Tahun'].min())
max_year = int(df['Tahun'].max())
selected_years = st.sidebar.slider("Pilih Rentang Tahun", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# Filter Jenis Industri
jenis_options = sorted(df['Jenis_Industri'].astype(str).unique().tolist())
selected_jenis = st.sidebar.multiselect("Pilih Jenis Industri", options=jenis_options, default=jenis_options)

# Filter Provinsi
prov_options = sorted(df['Provinsi'].astype(str).unique().tolist())
selected_prov = st.sidebar.multiselect("Pilih Provinsi", options=prov_options, default=prov_options)

# Apply Filter
df_filtered = df[
    (df['Tahun'] >= selected_years[0]) & 
    (df['Tahun'] <= selected_years[1]) &
    (df['Jenis_Industri'].isin(selected_jenis)) &
    (df['Provinsi'].isin(selected_prov))
]

# ==============================================================================
# MAIN PAGE
# ==============================================================================
st.markdown('<h1 class="main-header">📊 Dashboard Industri BPS</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Visualisasi Data Industri Besar Sedang (IBS) dan Mikro Kecil (IMK)</p>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 Visualisasi Data", "🤖 Prediktor AI"])

with tab1:
    # 2. Key Metrics
    st.markdown("### 💡 Ringkasan Indikator Utama")
    col1, col2, col3 = st.columns(3)

    total_perusahaan = df_filtered['Jumlah_Perusahaan'].sum()
    total_tk = df_filtered['Jumlah_Tenaga_Kerja'].sum()
    total_produksi = df_filtered['Nilai_Produksi_Ribu_Rp'].sum()

    with col1:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("🏢 Total Perusahaan", f"{total_perusahaan:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("👷‍♂️ Total Tenaga Kerja", f"{total_tk:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("💰 Total Produksi (Ribu Rp)", f"Rp {total_produksi:,.0f}")
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")

    # 3. Visualisasi
    color_bps_primary = "#004F98"
    color_bps_secondary = "#00A3E0"

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("#### 🏆 Top 10 Provinsi berdasarkan Tenaga Kerja")
        df_prov = df_filtered.groupby('Provinsi')['Jumlah_Tenaga_Kerja'].sum().reset_index()
        df_prov = df_prov.sort_values(by='Jumlah_Tenaga_Kerja', ascending=False).head(10)
        
        fig_bar = px.bar(
            df_prov, x='Provinsi', y='Jumlah_Tenaga_Kerja', 
            color_discrete_sequence=[color_bps_primary]
        )
        fig_bar.update_layout(xaxis_title="", yaxis_title="Tenaga Kerja")
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_chart2:
        st.markdown("#### 📈 Tren Pertumbuhan Tenaga Kerja per Tahun")
        df_trend = df_filtered.groupby('Tahun')['Jumlah_Tenaga_Kerja'].sum().reset_index()
        
        fig_line = px.line(
            df_trend, x='Tahun', y='Jumlah_Tenaga_Kerja', markers=True,
            color_discrete_sequence=[color_bps_secondary]
        )
        fig_line.update_layout(xaxis=dict(tickmode='linear', dtick=1), yaxis_title="Tenaga Kerja", xaxis_title="Tahun")
        st.plotly_chart(fig_line, use_container_width=True)

    st.write("---")

    st.markdown("#### 🔍 Hubungan: Jumlah Tenaga Kerja vs Nilai Produksi")
    # Scatter plot for Kab/Kota level
    df_scatter = df_filtered.groupby(['Provinsi', 'Kabupaten_Kota']).agg({
        'Jumlah_Tenaga_Kerja': 'sum',
        'Nilai_Produksi_Ribu_Rp': 'sum'
    }).reset_index()
    df_scatter = df_scatter[(df_scatter['Jumlah_Tenaga_Kerja'] > 0) & (df_scatter['Nilai_Produksi_Ribu_Rp'] > 0)]

    fig_scatter = px.scatter(
        df_scatter, x='Jumlah_Tenaga_Kerja', y='Nilai_Produksi_Ribu_Rp', 
        hover_name='Kabupaten_Kota', hover_data=['Provinsi'],
        color='Provinsi',
        log_x=True, log_y=True,
        labels={"Jumlah_Tenaga_Kerja": "Jumlah Tenaga Kerja (Log)", "Nilai_Produksi_Ribu_Rp": "Nilai Produksi (Log)"}
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # 4. Tabel Data Raw
    st.write("---")
    st.markdown("#### 📋 Tabel Data Mentah (Telah Difilter)")
    st.dataframe(df_filtered, use_container_width=True)

with tab2:
    st.markdown("### 🤖 Prediktor Nilai Produksi (Machine Learning)")
    st.write("Masukkan estimasi parameter di bawah ini untuk memprediksi perkiraan **Nilai Produksi** menggunakan model *Machine Learning* yang telah dilatih.")
    
    import joblib
    import os
    model_path = 'model_produksi.pkl'
    
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
            
            st.markdown("<br>", unsafe_allow_html=True)
            col_input1, col_input2 = st.columns(2)
            
            with col_input1:
                input_tahun = st.number_input("Tahun Prediksi", min_value=2000, max_value=2050, value=2024, step=1)
                input_jenis = st.selectbox("Jenis Industri", options=["IBS", "IMK", "Lainnya"])
            with col_input2:
                input_n_perusahaan = st.number_input("Jumlah Perusahaan", min_value=1, value=10, step=1)
                input_tk = st.number_input("Jumlah Tenaga Kerja", min_value=1, value=100, step=10)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔮 Prediksi Nilai Produksi", type="primary"):
                # Format input for model
                input_data = pd.DataFrame({
                    'tahun': [input_tahun],
                    'jenis_industri': [input_jenis],
                    'n_perusahaan': [input_n_perusahaan],
                    'tenaga_kerja': [input_tk]
                })
                
                prediction = model.predict(input_data)[0]
                
                st.success(f"### 🎉 Estimasi Nilai Produksi: **Rp {prediction:,.2f} Ribu**")
                st.info(f"*(Atau setara dengan **Rp {prediction/1000:,.2f} Juta**)*")
        except Exception as e:
            st.error(f"Gagal memuat model. Error: {e}")
    else:
        st.warning("Model Machine Learning (`model_produksi.pkl`) belum ditemukan. Sedang dilatih di latar belakang...")

