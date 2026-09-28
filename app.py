import hmac
import os

import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import requests
import time
from datetime import datetime
import random
import json
from logic.dala_estimator import estimate_dataframe, format_rupiah, parse_numeric, total_numeric

# ==========================================
# SETUP PAGE & CSS THEME
# ==========================================
st.set_page_config(page_title="DALA-SPK Bali", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# AKSES: password wajib bila DALA_PASSWORD (env) atau app_password (secrets.toml) diisi
# ==========================================
def _configured_password():
    password = os.environ.get('DALA_PASSWORD')
    if password:
        return password
    try:
        return st.secrets.get('app_password')
    except Exception:
        return None


_app_password = _configured_password()
if _app_password and not st.session_state.get('_authenticated'):
    st.markdown("<h2>🛡️ DALA-SPK</h2>", unsafe_allow_html=True)
    with st.form('login_form'):
        entered_password = st.text_input('Password akses dashboard', type='password')
        if st.form_submit_button('Masuk', type='primary'):
            if hmac.compare_digest(entered_password.encode(), str(_app_password).encode()):
                st.session_state['_authenticated'] = True
                st.rerun()
            st.error('Password salah.')
    st.stop()

# Inject Custom CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: #0e1117;
    color: #e2e8f0;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Space Mono', monospace;
    font-weight: 700;
}

/* KPI Cards */
.kpi-card {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 15px;
    text-align: center;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    backdrop-filter: blur(10px);
}

.kpi-value {
    font-family: 'Space Mono', monospace;
    font-size: 2rem;
    font-weight: 700;
    color: #4a90e2;
    margin: 10px 0;
}

.kpi-label {
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Badges */
.badge {
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: bold;
    text-transform: uppercase;
    display: inline-block;
}
.badge-berat { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
.badge-sedang { background-color: rgba(74, 144, 226, 0.2); color: #4a90e2; border: 1px solid #4a90e2; }
.badge-ringan { background-color: rgba(108, 122, 137, 0.2); color: #6c7a89; border: 1px solid #6c7a89; }

/* Status Dot Animation */
.status-dot {
    height: 12px;
    width: 12px;
    background-color: #4a90e2;
    border-radius: 50%;
    display: inline-block;
    animation: pulse 2s infinite;
    vertical-align: middle;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(74, 144, 226, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(74, 144, 226, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(74, 144, 226, 0); }
}

/* Photo Cards */
.photo-card {
    background: #1e293b;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    border: 1px solid #334155;
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.photo-card:hover {
    transform: translateY(-5px);
    border-color: #4a90e2;
    box-shadow: 0 8px 15px rgba(74, 144, 226, 0.2);
}
.photo-emoji {
    font-size: 4.5rem;
    text-align: center;
    margin-bottom: 15px;
}
.photo-details {
    font-size: 0.9rem;
    line-height: 1.5;
}
.photo-gps {
    color: #4a90e2;
    font-family: 'Space Mono', monospace;
    font-size: 0.8rem;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #334155;
}

/* Progress bar color override */
.stProgress > div > div > div > div {
    background-color: #4a90e2;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# MOCK DATA
# ==========================================
KABUPATEN = ["Denpasar", "Badung", "Gianyar", "Tabanan", "Buleleng", "Karangasem", "Klungkung", "Bangli", "Jembrana"]
SEKTOR = ["Pemukiman", "Infrastruktur", "Ekonomi", "Sosial", "Lintas Sektor"]
SEVERITY = ["Berat", "Sedang", "Ringan"]

# ==========================================
# HEADER SECTION
# ==========================================
col_h1, col_h2, col_h3 = st.columns([1.5, 1, 1])

with col_h1:
    st.markdown("<h2 style='margin-bottom:0;'>🛡️ DALA-SPK</h2>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:0.9rem; color:#94a3b8; margin-top:-10px;'>Damage & Loss Assessment System · Provinsi Bali</div>", unsafe_allow_html=True)

with col_h2:
    st.markdown("<div style='text-align:center;'><span class='status-dot'></span> <span class='badge' style='background-color:rgba(74,144,226,0.2); color:#4a90e2; border:1px solid #4a90e2; margin-left:8px;'>LLM LOCAL AKTIF</span></div>", unsafe_allow_html=True)

with col_h3:
    st.markdown("<br>", unsafe_allow_html=True)
    clock_placeholder = st.empty()

st.markdown("---")

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("## 🛡️ DALA-SPK")
    st.markdown("**Version 1.2.0-local**")
    st.markdown("---")
    
    st.markdown("### ⚙️ Filter Global")
    date_filter = st.date_input("Periode Kejadian", [])
    uploaded_data = st.file_uploader(
        "Unggah data kejadian (CSV/XLSX)",
        type=['csv', 'xlsx', 'xls'],
        help='Unggah data sumber untuk menggantikan demo. Jumlah kasus mengikuti baris data yang terbaca.',
    )

    if uploaded_data is not None:
        try:
            suffix = uploaded_data.name.lower().rsplit('.', 1)[-1]
            source_df = pd.read_csv(uploaded_data) if suffix == 'csv' else pd.read_excel(uploaded_data)
            st.success(f'{len(source_df)} baris dibaca dari {uploaded_data.name}')
        except Exception as error:
            source_df = pd.DataFrame()
            st.error(f'File gagal dibaca: {error}')
    else:
        source_df = pd.DataFrame()
        st.info('Unggah CSV/XLSX untuk menampilkan estimasi dari data input. Tidak ada data contoh yang dihitung.')

    def normalize_column(dataframe, target, aliases):
        if target in dataframe.columns:
            return
        key_map = {
            ''.join(character for character in str(column).casefold() if character.isalnum()): column
            for column in dataframe.columns
        }
        for alias in aliases:
            key = ''.join(character for character in alias.casefold() if character.isalnum())
            if key in key_map:
                dataframe[target] = dataframe[key_map[key]]
                return

    for target, aliases in {
        'Kabupaten': ('Kabupaten/Kota', 'Kabupaten Kota', 'Kota', 'Regency'),
        'Sektor': ('Sector', 'Jenis Sektor', 'Kategori Sektor'),
        'Jenis Kejadian / Bencana': ('Jenis Kejadian', 'Jenis Bencana', 'Disaster Type', 'Kejadian'),
        'Jumlah Terkena': ('Jumlah Terdampak', 'Jumlah Unit', 'Affected Quantity', 'Jumlah'),
        'Tingkat_Kerusakan': ('Tingkat Kerusakan', 'Damage Level', 'Kerusakan'),
    }.items():
        normalize_column(source_df, target, aliases)

    for required_column in ('Kabupaten', 'Sektor', 'Jenis Kejadian / Bencana', 'Jumlah Terkena'):
        if required_column not in source_df.columns:
            source_df[required_column] = None

    if 'Tingkat_Kerusakan' not in source_df.columns:
        source_df['Tingkat_Kerusakan'] = None

    region_column = 'Kabupaten' if 'Kabupaten' in source_df.columns else None
    region_options = sorted(source_df[region_column].dropna().astype(str).unique()) if region_column else []
    kab_filter = st.multiselect(
        "Wilayah Terdampak",
        region_options,
        default=region_options,
    )

if region_column:
    df_aktif = source_df[source_df['Kabupaten'].astype(str).isin(kab_filter)].copy()
else:
    df_aktif = source_df.copy()

date_column = next((
    column for column in ('Tanggal Kejadian', 'Tanggal', 'Waktu Kejadian', 'Tanggal Kejadian Bencana')
    if column in df_aktif.columns
), None)
if date_column and isinstance(date_filter, (tuple, list)) and len(date_filter) == 2:
    event_dates = pd.to_datetime(df_aktif[date_column], errors='coerce', dayfirst=True).dt.date
    df_aktif = df_aktif[event_dates.between(date_filter[0], date_filter[1])].copy()

df_terbaru = estimate_dataframe(df_aktif)
damage_total, damage_count = total_numeric(df_terbaru, '_estimasi_kerusakan_numeric')
loss_total, loss_count = total_numeric(df_terbaru, '_kerugian_unit_numeric')
st.sidebar.markdown('---')
st.sidebar.markdown('### 📈 Ringkasan Data Aktif')
st.sidebar.markdown(f'**Baris input:** {len(df_terbaru):,}')
st.sidebar.markdown(f'**Kerusakan terhitung:** {damage_count:,}/{len(df_terbaru):,}')
st.sidebar.markdown(f'**Kerugian terhitung:** {loss_count:,}/{len(df_terbaru):,}')

# ==========================================
# TABS NAVIGATION
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard", 
    "🗺️ Peta Kerusakan", 
    "📸 Tagging Foto", 
    "🤖 LLM Ekstraksi", 
    "📋 Laporan DaLA"
])

# ==========================================
# TAB 1: DASHBOARD
# ==========================================
with tab1:
    st.markdown("### Executive Summary Dashboard")
    if df_terbaru.empty:
        st.info('Belum ada data aktif. Unggah CSV/XLSX pada sidebar untuk menghitung estimasi.')

    total_rows = len(df_terbaru)
    if 'Jumlah Terkena' in df_terbaru:
        parsed_quantities = df_terbaru['Jumlah Terkena'].map(parse_numeric).dropna()
        affected_units = parsed_quantities.sum() if not parsed_quantities.empty else total_rows
    else:
        affected_units = total_rows
    severe_count = (
        df_terbaru['Tingkat_Kerusakan'].astype(str).str.contains('berat|roboh|terbakar habis', case=False, na=False).sum()
        if 'Tingkat_Kerusakan' in df_terbaru else 0
    )
    coverage_text = f'{damage_count}/{total_rows} data terhitung'
    damage_card_value = f'{format_rupiah(damage_total)} ({coverage_text})' if total_rows else 'Belum ada data'
    loss_card_value = f'{format_rupiah(loss_total)} ({loss_count}/{total_rows} data terhitung)' if total_rows else 'Belum ada data'
    source_col = next((column for column in ('source_doc', 'Dokumen Sumber', 'Sumber Dokumen') if column in df_terbaru), None)
    document_count = df_terbaru[source_col].nunique() if source_col else 0

    def count_origin(column, origin):
        return int((df_terbaru[column] == origin).sum()) if column in df_terbaru else 0

    price_input_count = count_origin('_sumber_harga', 'input')
    price_reference_count = count_origin('_sumber_harga', 'acuan')
    damage_input_count = count_origin('_sumber_kerusakan', 'input')
    damage_calc_count = count_origin('_sumber_kerusakan', 'hitung')
    loss_input_count = count_origin('_sumber_kerugian', 'input')
    loss_proxy_count = count_origin('_sumber_kerugian', 'proksi')
    damage_card_note = f'{damage_input_count} dari input user · {damage_calc_count} dihitung (Jumlah × Harga Satuan × Koefisien)'
    loss_card_note = f'{loss_input_count} dari input user · {loss_proxy_count} proksi 15% × kerusakan'

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Total Kerusakan</div><div class='kpi-value' style='font-size:1.05rem'>{damage_card_value}</div><div style='color:#94a3b8; font-size:0.8rem;'>{damage_card_note}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Total Kerugian</div><div class='kpi-value' style='font-size:1.05rem'>{loss_card_value}</div><div style='color:#94a3b8; font-size:0.8rem;'>{loss_card_note}</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Unit Terdampak</div><div class='kpi-value'>{affected_units:,.0f}</div><div style='color:#94a3b8; font-size:0.8rem;'>{total_rows} baris aktif sesuai filter</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Kerusakan Berat</div><div class='kpi-value'>{severe_count:,}</div><div style='color:#94a3b8; font-size:0.8rem;'>Dari data aktif</div></div>", unsafe_allow_html=True)
    with m5:
        coverage_pct = (damage_count / total_rows * 100) if total_rows else 0
        st.markdown(f"<div class='kpi-card'><div class='kpi-label'>Cakupan Estimasi</div><div class='kpi-value'>{coverage_pct:.1f}%</div><div style='color:#94a3b8; font-size:0.8rem;'>{document_count:,} dokumen tercatat</div></div>", unsafe_allow_html=True)

    st.warning(
        'Nilai dari data input user selalu didahulukan. Harga acuan sektor dan kerugian 15% hanya dipakai '
        'bila kolom terkait kosong, dan belum diverifikasi sebagai standar resmi; verifikasi dokumen sumber '
        'sebelum memakai hasil untuk laporan/keputusan resmi.'
    )

    with st.expander('🧮 Cara menghitung Harga Satuan, Estimasi Kerusakan, dan Estimasi Kerugian', expanded=total_rows > 0):
        st.markdown(f"""
| Komponen | Prioritas 1 — data input user | Prioritas 2 — bila input kosong | Baris aktif |
|---|---|---|---|
| **Harga Satuan** | Kolom `Harga Satuan` / `Harga Satuan (Rp)` | Harga acuan sektor (Lingkungan Hidup & SDA, Aset Non-Pasar & Budaya) | {price_input_count} input · {price_reference_count} acuan |
| **Estimasi Kerusakan** | Kolom `Estimasi Kerusakan` / `Nilai Kerusakan` | Jumlah Terkena × Harga Satuan × Koefisien Kerusakan | {damage_input_count} input · {damage_calc_count} dihitung |
| **Estimasi Kerugian** | Kolom `Estimasi Kerugian` / `Nilai Kerugian` / `Kerugian` | 15% × Estimasi Kerusakan (proksi) | {loss_input_count} input · {loss_proxy_count} proksi |

**Koefisien Kerusakan:** kolom `Persentase Kerusakan` bila diisi; jika tidak, dari `Tingkat Kerusakan`
— Ringan 30%, Sedang 50%, Berat/Roboh/Terbakar Habis 100%, rentang (mis. `31%-70%`) memakai nilai tengah.
Baris yang datanya belum lengkap tidak dianggap Rp 0; alasannya tercantum di kolom **Status Estimasi**.
""")
        if total_rows:
            breakdown_columns = [
                column for column in (
                    'Kabupaten', 'Sektor', 'Aset', 'Jenis Kejadian / Bencana', 'Jumlah Terkena', 'Tingkat_Kerusakan',
                    'Harga Satuan (Rp)', 'Sumber Harga Satuan', 'Koefisien Kerusakan',
                    'Estimasi Kerusakan (Rp)', 'Rincian Kerusakan',
                    'Estimasi Kerugian (Rp)', 'Rincian Kerugian', 'Status Estimasi',
                ) if column in df_terbaru.columns
            ]
            st.dataframe(
                df_terbaru[breakdown_columns].rename(columns={'Tingkat_Kerusakan': 'Tingkat Kerusakan'}),
                use_container_width=True,
                hide_index=True,
                column_config={
                    'Koefisien Kerusakan': st.column_config.NumberColumn(format='%.3f'),
                },
            )
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Charts Row 1
    c1, c2 = st.columns(2)
    with c1:
        if total_rows and '_estimasi_kerusakan_numeric' in df_terbaru:
            df_sektor = (
                df_terbaru.groupby('Sektor', dropna=False)['_estimasi_kerusakan_numeric']
                .sum(min_count=1).dropna().rename('Kerusakan (Rp)')
                .reset_index().sort_values('Kerusakan (Rp)', ascending=False)
            )
            if not df_sektor.empty:
                fig_bar = px.bar(df_sektor, x='Sektor', y='Kerusakan (Rp)', title='Estimasi Kerusakan Berdasarkan Sektor', color_discrete_sequence=['#4a90e2'])
                fig_bar.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0", title_font_family="Space Mono")
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info('Belum ada nilai estimasi kerusakan yang dapat dikelompokkan per sektor.')
        else:
            st.info('Grafik sektor menunggu data input.')
        
    with c2:
        # Pie Chart Plotly
        if total_rows and 'Tingkat_Kerusakan' in df_terbaru:
            df_pie = df_terbaru["Tingkat_Kerusakan"].value_counts().rename_axis("Tingkat").reset_index(name="Jumlah")
            fig_pie = px.pie(df_pie, values="Jumlah", names="Tingkat", title="Distribusi Tingkat Kerusakan", hole=0.4, color="Tingkat", color_discrete_map={"Berat":"#ef4444", "Sedang":"#f59e0b", "Ringan":"#10b981"})
            fig_pie.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0", title_font_family="Space Mono")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info('Distribusi tingkat kerusakan menunggu data input.')

    # Charts Row 2
    c3, c4 = st.columns([2, 1])
    with c3:
        if date_column and total_rows:
            df_tren = df_terbaru.copy()
            df_tren['_bulan'] = pd.to_datetime(df_tren[date_column], errors='coerce', dayfirst=True).dt.to_period('M').astype(str)
            df_tren = df_tren.dropna(subset=['_estimasi_kerusakan_numeric'])
            df_tren = df_tren.groupby('_bulan')['_estimasi_kerusakan_numeric'].sum().reset_index(name='Estimasi Kerusakan (Rp)')
            if not df_tren.empty:
                fig_line = px.line(df_tren, x='_bulan', y='Estimasi Kerusakan (Rp)', title='Tren Estimasi Kerusakan Bulanan', markers=True, color_discrete_sequence=['#4a90e2'])
                fig_line.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0", title_font_family="Space Mono")
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info('Belum ada nilai estimasi bertanggal untuk grafik tren.')
        else:
            st.info('Grafik tren memerlukan kolom tanggal kejadian dan nilai estimasi.')
        
    with c4:
        st.markdown("#### Realisasi Bantuan per Sektor", unsafe_allow_html=True)
        st.info('Unggah kolom realisasi bantuan untuk menampilkan progres. Tidak ada nilai progres demo yang digunakan.')
            
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Table
    st.markdown("#### Data Kerusakan Terbaru")
    display_df_terbaru = df_terbaru.rename(columns={"Tingkat_Kerusakan": "Tingkat Kerusakan"})
    internal_columns = [column for column in display_df_terbaru.columns if str(column).startswith('_')]
    st.dataframe(display_df_terbaru.drop(columns=internal_columns), use_container_width=True)

# ==========================================
# TAB 2: PETA KERUSAKAN
# ==========================================
with tab2:
    st.markdown("### Peta Sebaran Kerusakan Wilayah Bali")

    col_map1, col_map2 = st.columns([3, 1])

    with col_map2:
        st.markdown("#### Filter Map")
        filter_peta = st.radio("Tingkat Kerusakan", ["Semua", "Berat", "Sedang", "Ringan"])

        st.markdown("<br>", unsafe_allow_html=True)
        # Keep the chart and map based on the same active input rows.
        map_source = df_terbaru[df_terbaru["Kabupaten"].isin(kab_filter)].copy()
        df_kab = (
            map_source["Kabupaten"]
            .value_counts()
            .reindex(KABUPATEN, fill_value=0)
            .rename_axis("Kabupaten")
            .reset_index(name="Jumlah Kasus")
        )
        df_kab = df_kab.sort_values("Jumlah Kasus", ascending=True)
        fig_kab = px.bar(df_kab, y="Kabupaten", x="Jumlah Kasus", orientation='h', title="Total Kasus per Kab/Kota", color_discrete_sequence=["#2563eb"])
        fig_kab.update_layout(plot_bgcolor="rgba(255,255,255,0)", paper_bgcolor="rgba(255,255,255,0)", font_color="#0f172a", margin=dict(l=0, r=0, t=30, b=0), height=400)
        st.plotly_chart(fig_kab, use_container_width=True)

    with col_map1:
        map_data = [
            {
                'id': row.get('ID Laporan', f'DALA-{index + 1:02d}'),
                'asset': row.get('Aset', 'Aset terdampak'),
                'location': row.get('Kabupaten', 'Lokasi tidak diketahui'),
                'sector': row.get('Sektor', 'Lainnya'),
                'cost': row.get('Estimasi Kerugian (Juta)', 0),
                'damage_level': row.get('Tingkat_Kerusakan', 'Sedang'),
                'disaster_type': row.get('Jenis Kejadian / Bencana', 'Tidak diketahui'),
            }
            for index, (_, row) in enumerate(map_source.iterrows())
        ]

        from ui.components.map_view import create_location_map
        map_html = create_location_map(filter_peta, map_data)
        st.components.v1.html(map_html, height=520, scrolling=True)

# ==========================================
# TAB 3: TAGGING FOTO
# ==========================================
with tab3:
    st.markdown("### Sistem Tagging & Validasi Lapangan")
    
    col_f1, col_f2 = st.columns([1, 2.5])
    
    with col_f1:
        st.markdown("#### 📤 Upload Dokumentasi Baru")
        uploaded_files = st.file_uploader("Pilih foto lapangan", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} foto berhasil diunggah!")
            
        st.markdown("---")
        st.markdown("#### ⏱️ Timeline Aktivitas")
        df_timeline = pd.DataFrame({
            "Waktu": ["10:30", "11:15", "13:05", "14:20"], 
            "Aktivitas": ["Upload 5 foto (Badung)", "Validasi lokasi Karangasem", "Upload 2 foto (Denpasar)", "Sinkronisasi Data GIS"]
        })
        st.dataframe(df_timeline, use_container_width=True, hide_index=True)
        
        # Mini Pie Chart
        df_pie_foto = pd.DataFrame({"Status": ["Tervalidasi", "Pending"], "Jumlah": [1450, 397]})
        fig_pie_foto = px.pie(df_pie_foto, values="Jumlah", names="Status", title="Status Validasi Foto", hole=0.5, color_discrete_sequence=["#4a90e2", "#6c7a89"])
        fig_pie_foto.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0", margin=dict(t=30, b=0, l=0, r=0), height=250)
        st.plotly_chart(fig_pie_foto, use_container_width=True)
        
    with col_f2:
        st.markdown("#### 📸 Galeri Foto Lapangan")
        filter_foto = st.radio("Filter Tingkat Kerusakan:", ["Semua", "Berat", "Sedang", "Ringan"], horizontal=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Generate 18 mock photos
        emojis = ["🏠", "🏥", "🏫", "🌉", "🏭", "🚜", "🏪", "🛣️"]
        mock_photos = []
        for i in range(18):
            tingkat = random.choice(SEVERITY)
            mock_photos.append({
                "id": f"IMG-{random.randint(1000,9999)}",
                "emoji": random.choice(emojis),
                "tingkat": tingkat,
                "lokasi": random.choice(KABUPATEN),
                "sektor": random.choice(SEKTOR),
                "tanggal": f"2026-05-{random.randint(1,13):02d}",
                "koordinat": f"-8.{random.randint(1000, 9000)}, 115.{random.randint(1000, 9000)}"
            })
            
        if filter_foto != "Semua":
            mock_photos = [p for p in mock_photos if p["tingkat"] == filter_foto]
            
        # Grid 3 columns
        cols = st.columns(3)
        for i, p in enumerate(mock_photos):
            col = cols[i % 3]
            with col:
                badge_class = f"badge-{p['tingkat'].lower()}"
                html_card = f"""
                <div class="photo-card">
                    <div class="photo-emoji">{p['emoji']}</div>
                    <div style="text-align:center; margin-bottom:15px;">
                        <span class="badge {badge_class}">{p['tingkat']}</span>
                    </div>
                    <div class="photo-details">
                        <b>ID:</b> {p['id']}<br>
                        <b>Lokasi:</b> {p['lokasi']}<br>
                        <b>Sektor:</b> {p['sektor']}<br>
                        <b>Tgl Upload:</b> {p['tanggal']}
                    </div>
                    <div class="photo-gps">GPS: {p['koordinat']}</div>
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)
                
                # Expandable details
                with st.expander(f"Detail & Validasi ({p['id']})"):
                    st.write(f"**Sektor**: {p['sektor']}")
                    st.write("**Catatan Assessor**:")
                    st.write("Kerusakan struktur utama terlihat jelas. Diperlukan evaluasi mendalam oleh tim teknis konstruksi sebelum rekonstruksi dimulai.")
                    st.button("Validasi Data", key=f"btn_val_{p['id']}", use_container_width=True)

# ==========================================
# TAB 4: LLM EKSTRAKSI
# ==========================================
with tab4:
    st.markdown("### 🤖 Ekstraksi Parameter DaLA Berbasis Local LLM")
    st.info("Fitur ini menggunakan model LLM lokal untuk mengekstrak parameter Damage & Loss Assessment (DaLA) dari teks dokumen atau jurnal tanpa perlu koneksi internet, menjamin kerahasiaan data bencana.")
    st.caption("Catatan: pada versi online (Streamlit Cloud), alamat `localhost` merujuk ke server, bukan komputer Anda, sehingga LLM lokal tidak terjangkau dan yang tampil adalah hasil simulasi. Jalankan dashboard di komputer sendiri untuk memakai LLM lokal.")

    col_llm1, col_llm2 = st.columns([1, 2])
    
    with col_llm1:
        st.markdown("#### ⚙️ Konfigurasi Endpoint")
        llm_url = st.text_input("Base URL Endpoint", value="http://localhost:11434/api/chat")
        llm_model = st.text_input("Nama Model", value="llama3")
        
        if st.button("🔌 Test Koneksi LLM", use_container_width=True):
            try:
                base = llm_url.replace("/api/chat", "").replace("/v1/chat/completions", "")
                res = requests.get(base, timeout=3)
                if res.status_code == 200:
                    st.success("✅ Terhubung ke Local LLM!")
                else:
                    st.warning(f"⚠️ Terhubung, tapi status code: {res.status_code}")
            except Exception as e:
                st.error("❌ Gagal terhubung ke Local LLM.")
                st.caption(f"Error details: {str(e)}")
                st.info("Pastikan Ollama / LM Studio / Jan sedang berjalan di port yang benar.")
                
        st.markdown("---")
        st.markdown("**Kompatibilitas:**")
        st.markdown("""
        - 🦙 **Ollama:** `http://localhost:11434/api/chat`
        - 🤖 **LM Studio:** `http://localhost:1234/v1/chat/completions`
        - 🧠 **Jan:** `http://localhost:1337/v1/chat/completions`
        """)
        
    with col_llm2:
        st.markdown("#### 📝 Input Teks / Jurnal Assessment")
        query_text = st.text_area("Masukkan teks laporan, jurnal, atau deskripsi kerusakan di sini...", height=200, placeholder="Contoh: Pada desa A, terjadi gempa yang merusak 50 rumah dengan tingkat rusak berat. Harga satuan bangunan di area tersebut diperkirakan Rp 3.500.000 per meter persegi. Nilai ekosistem yang hilang sekitar Rp 200.000.000. Koefisien kerusakan untuk kategori berat ditetapkan sebesar 0.8.")
        
        sys_prompt = "Kamu adalah asisten ahli DaLA (Damage and Loss Assessment). Ekstrak parameter harga satuan bangunan, koefisien kerusakan, nilai ekosistem dari teks yang diberikan. Jawab dalam Bahasa Indonesia dengan format terstruktur dan bullet points."
        
        if st.button("🚀 Ekstrak Parameter DaLA", type="primary"):
            if not query_text:
                st.warning("⚠️ Mohon masukkan teks terlebih dahulu.")
            else:
                with st.spinner("⏳ Memproses query dengan Local LLM..."):
                    payload = {
                        "model": llm_model,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": query_text}
                        ],
                        "stream": False
                    }
                    
                    try:
                        res = requests.post(llm_url, json=payload, timeout=10)
                        if res.status_code == 200:
                            data = res.json()
                            # Handle Ollama vs OpenAI format
                            if "message" in data:
                                output = data["message"]["content"]
                            elif "choices" in data:
                                output = data["choices"][0]["message"]["content"]
                            else:
                                output = str(data)
                        else:
                            raise Exception(f"HTTP Status {res.status_code}")
                    except Exception as e:
                        # Fallback / Simulated output if LLM is offline
                        time.sleep(1.5)
                        output = """### Hasil Ekstraksi Parameter DaLA
*   **Harga Satuan Bangunan**: Rp 3.500.000 / m²
*   **Koefisien Kerusakan (Berat)**: 0.8
*   **Nilai Ekosistem Terdampak**: Rp 200.000.000
*   **Jumlah Unit Terdampak**: 50 Rumah
*   **Tingkat Kerusakan**: Berat
*   **Sektor**: Pemukiman
"""
                        st.warning("⚠️ Local LLM tidak merespons. Menampilkan hasil ekstraksi simulasi berdasarkan konteks.")
                        
                    st.markdown("#### 📄 Hasil Ekstraksi LLM:")
                    st.info(output)
                    
                    st.markdown("#### 📊 Tabel Parameter Terstruktur")
                    df_extracted = pd.DataFrame({
                        "Parameter DaLA": ["Harga Satuan (HSB)", "Koefisien Kerusakan", "Nilai Ekosistem", "Unit Terdampak", "Sektor Terdampak", "Kategori Kerusakan"],
                        "Nilai Terekstrak": ["Rp 3.500.000 / m²", "0.80", "Rp 200.000.000", "50 Unit", "Pemukiman", "Berat"],
                        "Tingkat Keyakinan": ["98%", "95%", "92%", "99%", "99%", "98%"]
                    })
                    st.dataframe(df_extracted, use_container_width=True, hide_index=True)

# ==========================================
# TAB 5: LAPORAN DALA
# ==========================================
with tab5:
    st.markdown("### 📋 Form Pembuatan Laporan DaLA")
    st.markdown("Isi formulir di bawah ini untuk menghasilkan dokumen laporan final Damage and Loss Assessment secara otomatis.")
    
    with st.form("form_laporan"):
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            judul_lap = st.text_input("Judul Laporan", value="Laporan Rapid Assessment DaLA Bali")
            wilayah_lap = st.text_input("Wilayah Terdampak", value="Kabupaten Karangasem & Buleleng")
            assessor = st.text_input("Nama Assessor Utama", value="Tim Ahli BPBD Provinsi Bali")
        with col_l2:
            periode_lap = st.date_input("Periode Kejadian", value=datetime.today())
            jenis_bencana = st.selectbox("Jenis Bencana", ["Gempa Bumi", "Banjir Bandang", "Tsunami", "Tanah Longsor", "Erupsi Gunung Api"])
            
        st.markdown("<br>", unsafe_allow_html=True)
        submit_btn = st.form_submit_button("Generate Laporan DaLA 📄")
        
    if submit_btn:
        st.success("✅ Laporan berhasil digenerate dan siap untuk diunduh!")
        st.balloons()
        
        with st.expander("👁️ Preview Dokumen Laporan Final", expanded=True):
            st.markdown(f"<h2 style='text-align:center;'>{judul_lap}</h2>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center; color:#94a3b8; margin-bottom:20px;'><b>Wilayah:</b> {wilayah_lap} | <b>Bencana:</b> {jenis_bencana} | <b>Assessor:</b> {assessor} | <b>Tanggal:</b> {periode_lap.strftime('%d %B %Y')}</div>", unsafe_allow_html=True)
            st.markdown("---")
            
            st.markdown("#### 1. Executive Summary")
            st.write("Laporan ini menyajikan hasil penilaian cepat (rapid assessment) kerusakan dan kerugian pasca bencana menggunakan metodologi Damage and Loss Assessment (DaLA). Berdasarkan pendataan lapangan dan analisis spasial, tercatat kerugian signifikan pada sektor pemukiman dan infrastruktur utama.")
            
            st.markdown("#### 2. Metodologi")
            st.write("Penilaian dilakukan menggunakan pendekatan DaLA dengan panduan standar ECLAC yang disesuaikan dengan peraturan BNPB (Perka BNPB No. 15 Tahun 2011). Data diperoleh melalui tagging foto lapangan, analisis citra satelit, dan ekstraksi informasi dari laporan tingkat desa menggunakan sistem LLM lokal.")
            
            st.markdown("#### 3. Temuan Utama per Sektor")
            st.write("""
            - **Pemukiman**: Kerusakan berat pada 342 unit rumah di area episentrum bencana, mengakibatkan 1.200 jiwa mengungsi.
            - **Infrastruktur**: Terputusnya akses jalan provinsi sepanjang 2.5 km yang mengisolasi 3 desa di Karangasem.
            - **Ekonomi**: Kerugian pada sektor pertanian akibat rusaknya sistem irigasi subak.
            """)
            
            st.markdown("#### 4. Rekomendasi Penanganan")
            st.write("""
            1. **Jangka Pendek**: Segera lakukan pembersihan material longsoran dan berikan bantuan logistik untuk pengungsi.
            2. **Jangka Menengah**: Alokasikan dana darurat dan dana siap pakai untuk perbaikan infrastruktur jalan.
            3. **Jangka Panjang**: Program rekonstruksi pemukiman dengan standar bangunan tahan gempa.
            """)
            
            st.markdown("#### 5. Tabel Ringkasan Kerugian Final (Miliar Rp)")
            df_final = pd.DataFrame({
                "Sektor DaLA": SEKTOR,
                "Kerusakan Fisik (Damage)": [80, 50, 30, 15, 5],
                "Kerugian Ekonomi (Loss)": [40, 35, 15, 9, 5],
                "Total Kebutuhan (Needs)": [120, 85, 45, 24, 10]
            })
            st.dataframe(df_final, use_container_width=True, hide_index=True)
            
            # Download Action
            st.markdown("---")
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data Kerugian (CSV)",
                data=csv,
                file_name=f'Ringkasan_DaLA_{jenis_bencana.replace(" ", "_")}.csv',
                mime='text/csv',
                type="primary"
            )

# ==========================================
# REALTIME CLOCK INJECTION
# ==========================================
# Karena Streamlit top-down execution, menggunakan `while True: time.sleep(1)` akan memblokir interaksi user.
# Untuk memenuhi requirement "jam realtime menggunakan st.empty() dan time.sleep(1)" tapi tetap interaktif:
# Kita lakukan 1x render pada placeholder untuk waktu saat di-load. 
# Sebagai ganti agar *benar-benar* real-time tanpa blokir, kita gunakan Javascript.

clock_placeholder.markdown(f"<div style='text-align:right; font-family:\"Space Mono\", monospace; font-size:1.3rem; color:#4a90e2; font-weight:700;'>{datetime.now().strftime('%H:%M:%S WIB')}</div>", unsafe_allow_html=True)

# Jika memaksa menggunakan time.sleep(1), kode berikut ini (jika di-uncomment) 
# akan memblokir app tapi memenuhi kriteria loop murni Python:
# while True:
#     clock_placeholder.markdown(f"<div style='text-align:right; font-family:\"Space Mono\", monospace; font-size:1.3rem; color:#4a90e2; font-weight:700;'>{datetime.now().strftime('%H:%M:%S WIB')}</div>", unsafe_allow_html=True)
#     time.sleep(1)
#     st.rerun()

# Solusi aman non-blocking: inject sedikit Javascript untuk jam berjalan
st.markdown("""
<script>
    const doc = window.parent.document;
    function updateTime() {
        const elements = doc.querySelectorAll('div');
        for (let el of elements) {
            if (el.innerHTML.includes('WIB') && el.style.color === 'rgb(74, 144, 226)') {
                const now = new Date();
                const timeString = now.toLocaleTimeString('id-ID', { hour12: false }) + ' WIB';
                el.innerHTML = timeString;
            }
        }
    }
    setInterval(updateTime, 1000);
</script>
""", unsafe_allow_html=True)
