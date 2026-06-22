import sqlite3
import pandas as pd
import numpy as np
import joblib

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def load_data():
    conn = sqlite3.connect("bps_data.db")
    query = """
        SELECT 
            tahun,
            jenis_industri,
            n_perusahaan,
            tenaga_kerja,
            nilai_produksi_ribu_rp
        FROM fact_industri_wilayah
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Konversi tipe data
    for col in ['tahun', 'n_perusahaan', 'tenaga_kerja', 'nilai_produksi_ribu_rp']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    return df

def run_ml_pipeline():
    print("Membaca data dari database...")
    df = load_data()
    
    # 1. Penanganan Missing Target (nilai_produksi_ribu_rp)
    # Hapus baris yang tidak punya nilai target atau nilainya <= 0
    df = df.dropna(subset=['nilai_produksi_ribu_rp'])
    df = df[df['nilai_produksi_ribu_rp'] > 0]
    
    print(f"Jumlah data valid untuk training: {len(df)} baris")
    if len(df) == 0:
        print("Error: Tidak ada data yang valid untuk dilatih!")
        return
        
    # Fitur (X) dan Target (y)
    X = df[['tahun', 'jenis_industri', 'n_perusahaan', 'tenaga_kerja']]
    y = df['nilai_produksi_ribu_rp']
    
    # 2. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Preprocessing (Pipeline)
    numeric_features = ['tahun', 'n_perusahaan', 'tenaga_kerja']
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')), # Isi nilai kosong dengan median
        ('scaler', StandardScaler()) # Standarisasi skala
    ])

    categorical_features = ['jenis_industri']
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)
        ])

    # 4. Mendefinisikan Model untuk Dieksperimenkan
    models = {
        'Linear Regression': LinearRegression(),
        'Random Forest': RandomForestRegressor(n_estimators=100, random_state=42),
        'Gradient Boosting': GradientBoostingRegressor(n_estimators=100, random_state=42)
    }
    
    best_model = None
    best_r2 = -float('inf')
    best_name = ""
    best_pipeline = None
    
    print("\nEvaluasi Model:")
    print("-" * 50)
    for name, model in models.items():
        # Buat full pipeline
        clf = Pipeline(steps=[('preprocessor', preprocessor),
                              ('regressor', model)])
        
        # Training
        clf.fit(X_train, y_train)
        
        # Prediksi
        y_pred = clf.predict(X_test)
        
        # Metrik Error
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        
        print(f"Model: {name}")
        print(f"  MAE  : Rp {mae:,.2f} Ribu")
        print(f"  RMSE : Rp {rmse:,.2f} Ribu")
        print(f"  R^2  : {r2:.4f}")
        print("-" * 50)
        
        if r2 > best_r2:
            best_r2 = r2
            best_model = clf
            best_name = name
            
    print(f"\nModel Terbaik: {best_name} (R^2 = {best_r2:.4f})")
    
    # Latih ulang model terbaik menggunakan seluruh data valid (opsional tapi disarankan untuk production)
    print("Melatih ulang model terbaik dengan seluruh dataset...")
    best_model.fit(X, y)
    
    # 5. Ekspor Model
    model_filename = 'model_produksi.pkl'
    joblib.dump(best_model, model_filename)
    print(f"Berhasil menyimpan model terbaik ke {model_filename}!")

if __name__ == "__main__":
    run_ml_pipeline()
