"""Transparent, rule-based DaLA cost proxies for the Streamlit dashboard."""

import math
import re

import pandas as pd


# Sektor Lingkungan Hidup & SDA (Satuan: Titik Lokasi / Titik Kejadian)
ENVIRONMENT_REFERENCE = {
    'pohon': (3_500_000, 'Standar Operasional Penanganan Darurat TRC BPBD & DLH'),
    'longsor': (15_000_000, 'AHSP PUPR / Penanganan Darurat Longsoran BPBD'),
    'tebing': (15_000_000, 'AHSP PUPR / Penanganan Darurat Longsoran BPBD'),
    'senderan': (15_000_000, 'AHSP PUPR / Penanganan Darurat Longsoran BPBD'),
    'karhutla': (15_000_000, 'Operasional Pemadaman Kebakaran Hutan & Lahan'),
    'kebakaran_hutan': (15_000_000, 'Operasional Pemadaman Kebakaran Hutan & Lahan'),
    'banjir': (7_500_000, 'Biaya Penanganan Darurat Dampak Banjir'),
    'default': (5_000_000, 'Standar Estimasi Pemulihan Lingkungan Darurat'),
}

# Sektor Aset Non-Pasar & Budaya (Satuan: Unit / Buah)
CULTURAL_REFERENCE = {
    'pura': (33_817_778, 'Pergub Bali No. 37/2023 (Bansos Tempat Ibadah/Pura)'),
    'pelinggih': (15_000_000, 'Pergub Bali No. 37/2023 (Bansos Pelinggih/Sarana Ibadah)'),
    'sanggah': (15_000_000, 'Pergub Bali No. 37/2023 (Bansos Pelinggih/Sarana Ibadah)'),
    'piyasan': (15_000_000, 'Pergub Bali No. 37/2023 (Bansos Pelinggih/Sarana Ibadah)'),
    'bale': (25_000_000, 'Pergub Bali No. 37/2023 (Bansos Sarana Komunitas Adat)'),
    'balai': (25_000_000, 'Pergub Bali No. 37/2023 (Bansos Sarana Komunitas Adat)'),
    'wantilan': (25_000_000, 'Pergub Bali No. 37/2023 (Bansos Sarana Komunitas Adat)'),
    'kulkul': (25_000_000, 'Pergub Bali No. 37/2023 (Bansos Sarana Komunitas Adat)'),
    'default': (20_000_000, 'Pergub Bali No. 37/2023 (Bansos Fasilitas Adat)'),
}


def _normalize_text(value):
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return re.sub(r'\s+', ' ', str(value)).strip().casefold()


def _get_value(row, *names):
    normalized_row = {
        re.sub(r'[^a-z0-9]+', '', str(column).casefold()): value
        for column, value in row.items()
    }
    for name in names:
        key = re.sub(r'[^a-z0-9]+', '', name.casefold())
        value = normalized_row.get(key)
        if value is not None and _normalize_text(value) not in {'', 'nan', 'none', 'null'}:
            return value
    return None


def parse_numeric(value):
    """Parse Indonesian-formatted counts/currency without treating missing as zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None

    text = str(value).strip()
    if not text or text.casefold() in {'-', '—', 'nan', 'none', 'null', 'tidak tersedia'}:
        return None
    match = re.search(r'-?\d[\d.,]*', text)
    if not match:
        return None
    number = match.group()
    if ',' in number and '.' in number:
        if number.rfind(',') > number.rfind('.'):
            number = number.replace('.', '').replace(',', '.')
        else:
            number = number.replace(',', '')
    elif ',' in number:
        parts = number.split(',')
        number = ''.join(parts[:-1]) + ('.' + parts[-1] if len(parts[-1]) <= 2 else parts[-1])
    elif '.' in number:
        parts = number.split('.')
        number = ''.join(parts[:-1]) + ('.' + parts[-1] if len(parts[-1]) <= 2 else parts[-1])
    try:
        result = float(number)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def format_rupiah(value):
    if value is None:
        return 'Tidak tersedia'
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 'Tidak tersedia'
    if not math.isfinite(numeric_value):
        return 'Tidak tersedia'
    return f"Rp {int(round(numeric_value)):,}".replace(',', '.')


def _reference_for_row(row):
    """
    Determine reference price for a row using flexible keyword matching.
    Returns (unit_price, basis_text, sector_name) tuple.
    Supports multi-tier matching for Environmental and Cultural sectors.
    """
    sector = _normalize_text(_get_value(row, 'Sektor', 'Sector', 'Kategori Sektor'))
    asset = _normalize_text(_get_value(row, 'Aset', 'Nama Aset', 'Komponen', 'Asset'))
    disaster = _normalize_text(_get_value(
        row,
        'Jenis Kejadian / Bencana', 'Jenis Kejadian', 'Jenis Bencana', 'Disaster Type', 'Kejadian',
    ))
    
    # Combine all text for matching
    combined_text = f'{sector} {asset} {disaster}'

    # ============================================
    # TIER 1: Check if it's Environmental Sector
    # ============================================
    is_environmental = any(term in sector for term in (
        'lingkungan', 'sda', 'sumber daya alam', 'lingkungan hidup', 'environment'
    ))
    
    if is_environmental:
        # Tier 1A: Pohon Tumbang / Penanganan Pohon
        if 'pohon' in combined_text:
            return (
                ENVIRONMENT_REFERENCE['pohon'][0],
                ENVIRONMENT_REFERENCE['pohon'][1],
                'Lingkungan Hidup & SDA'
            )
        
        # Tier 1B: Longsor / Tebing / Senderan
        if any(term in combined_text for term in ('longsor', 'tebing', 'senderan')):
            return (
                ENVIRONMENT_REFERENCE['longsor'][0],
                ENVIRONMENT_REFERENCE['longsor'][1],
                'Lingkungan Hidup & SDA'
            )
        
        # Tier 1C: Kebakaran Hutan & Lahan (Karhutla)
        if any(term in combined_text for term in ('kebakaran', 'karhutla', 'hutan lahan')):
            return (
                ENVIRONMENT_REFERENCE['karhutla'][0],
                ENVIRONMENT_REFERENCE['karhutla'][1],
                'Lingkungan Hidup & SDA'
            )
        
        # Tier 1D: Banjir
        if 'banjir' in combined_text:
            return (
                ENVIRONMENT_REFERENCE['banjir'][0],
                ENVIRONMENT_REFERENCE['banjir'][1],
                'Lingkungan Hidup & SDA'
            )
        
        # Tier 1E: Default untuk sektor lingkungan lainnya
        return (
            ENVIRONMENT_REFERENCE['default'][0],
            ENVIRONMENT_REFERENCE['default'][1],
            'Lingkungan Hidup & SDA'
        )

    # ============================================
    # TIER 2: Check if it's Cultural/Non-Market Sector
    # ============================================
    is_cultural = (
        any(term in sector for term in (
            'non pasar', 'non-pasar', 'aset non pasar', 'budaya', 'adat',
            'fasilitas adat', 'fasilitas keagamaan', 'non market', 'cultural'
        ))
        or any(term in combined_text for term in (
            'pura', 'pelinggih', 'sanggah', 'piyasan', 'bale', 'balai adat',
            'wantilan', 'kulkul', 'bale kulkul'
        ))
    )
    
    if is_cultural:
        # Tier 2A: Pura
        if 'pura' in combined_text:
            return (
                CULTURAL_REFERENCE['pura'][0],
                CULTURAL_REFERENCE['pura'][1],
                'Aset Non-Pasar & Budaya'
            )
        
        # Tier 2B: Pelinggih / Sanggah / Piyasan
        if any(term in combined_text for term in ('pelinggih', 'sanggah', 'piyasan')):
            return (
                CULTURAL_REFERENCE['pelinggih'][0],
                CULTURAL_REFERENCE['pelinggih'][1],
                'Aset Non-Pasar & Budaya'
            )
        
        # Tier 2C: Bale / Balai / Wantilan / Kulkul
        if any(term in combined_text for term in ('bale', 'balai', 'wantilan', 'kulkul')):
            return (
                CULTURAL_REFERENCE['bale'][0],
                CULTURAL_REFERENCE['bale'][1],
                'Aset Non-Pasar & Budaya'
            )
        
        # Tier 2D: Default untuk aset budaya lainnya
        return (
            CULTURAL_REFERENCE['default'][0],
            CULTURAL_REFERENCE['default'][1],
            'Aset Non-Pasar & Budaya'
        )
    
    # ============================================
    # No match for known sectors
    # ============================================
    return (None, None, None)


def _damage_coefficient(value):
    """
    Parse damage level and return coefficient for damage calculation.
    
    Coefficients:
    - Rusak Ringan: 0.30 (30%)
    - Rusak Sedang: 0.50 (50%)
    - Rusak Berat / Roboh / Terbakar Habis: 1.00 (100%)
    
    For ranges, returns the midpoint.
    """
    text = _normalize_text(value)
    if not text:
        return None

    # Try to parse range format first (e.g., "50-70%" or "50 - 70")
    range_match = re.search(
        r'(?<!\d)(\d+(?:[.,]\d+)?)\s*(%)?\s*(?:-|–|s/d|sampai)\s*'
        r'(\d+(?:[.,]\d+)?)\s*(%)?', text,
    )
    if range_match:
        lower = float(range_match.group(1).replace(',', '.'))
        upper = float(range_match.group(3).replace(',', '.'))
        if lower <= upper:
            midpoint = (lower + upper) / 2
            return midpoint / 100 if range_match.group(2) or range_match.group(4) or midpoint > 1 else midpoint

    # Try to parse single numeric value
    numeric_value = parse_numeric(value)
    if numeric_value is not None:
        return numeric_value / 100 if numeric_value > 1 else numeric_value
    
    # Check for severity keywords - Heavy damage
    if any(term in text for term in ('roboh', 'terbakar habis', 'rusak berat', 'berat', 'heavy', 'severe', 'parah')):
        return 1.0
    
    # Check for severity keywords - Medium damage
    if any(term in text for term in ('rusak sedang', 'sedang', 'medium', 'moderate')):
        return 0.50
    
    # Check for severity keywords - Light damage
    if any(term in text for term in ('rusak ringan', 'ringan', 'light', 'minor', 'slight')):
        return 0.30
    
    return None


LOSS_PROXY_RATIO = 0.15

# Kolom input user yang diutamakan sebelum memakai acuan/proksi.
UNIT_PRICE_COLUMNS = (
    'Harga Satuan', 'Harga Satuan (Rp)', 'Harga Satuan Input', 'Unit Price',
    'unit_price', 'harga_satuan', 'fixed_unit_price', 'estimated_unit_price',
)
UNIT_PRICE_SOURCE_COLUMNS = ('Sumber Harga', 'Sumber Harga Satuan', 'unit_price_source')
QUANTITY_COLUMNS = (
    'Jumlah Terkena', 'Jumlah Terdampak', 'Jumlah Unit', 'Affected Quantity', 'Jumlah',
    'Kuantitas Fisik', 'physical_quantity', 'damaged_units', 'Volume', 'Luas',
)
PHYSICAL_UNIT_COLUMNS = ('Satuan', 'Satuan Fisik', 'physical_unit')
REFERENCE_UNITS = {
    'unit', 'buah', 'bh', 'titik', 'titik lokasi', 'titik kejadian', 'lokasi', 'kejadian',
    'bangunan', 'pohon', 'batang',
}
DAMAGE_PERCENT_COLUMNS = (
    'Persentase Kerusakan', 'Persentase Kerusakan (%)', 'damage_percentage', 'damage_percent',
    'persentase_kerusakan',
)
DAMAGE_LEVEL_COLUMNS = ('Tingkat_Kerusakan', 'Tingkat Kerusakan', 'Damage Level', 'damage_level', 'Kerusakan')
DAMAGE_INPUT_COLUMNS = (
    'Estimasi Kerusakan (Rp)', 'Estimasi Kerusakan', 'Nilai Kerusakan', 'Nilai Kerusakan (Rp)',
    'Kerusakan (Rp)', 'damage_estimate', 'reported_asset_damage_est',
)
LOSS_INPUT_COLUMNS = (
    'Estimasi Kerugian (Rp)', 'Estimasi Kerugian', 'Nilai Kerugian', 'Nilai Kerugian (Rp)',
    'Kerugian (Rp)', 'Kerugian', 'economic_loss', 'reported_economic_loss',
)

ESTIMATE_COLUMNS = (
    'Harga Satuan (Rp)', 'Sumber Harga Satuan', 'Dasar Acuan', 'Koefisien Kerusakan',
    'Estimasi Kerusakan (Rp)', 'Rincian Kerusakan', 'Estimasi Kerugian (Rp)', 'Rincian Kerugian',
    'Status Estimasi',
    '_harga_satuan_numeric', '_estimasi_kerusakan_numeric', '_kerugian_unit_numeric',
    '_sumber_harga', '_sumber_kerusakan', '_sumber_kerugian',
)


def _format_number(value):
    text = f'{value:,.2f}'.rstrip('0').rstrip('.')
    return text.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def _format_percent(coefficient):
    return f'{_format_number(coefficient * 100)}%'


def _input_amount(row, columns):
    value = parse_numeric(_get_value(row, *columns))
    return value if value is not None and value >= 0 else None


def estimate_row(row):
    """
    Hitung harga satuan, estimasi kerusakan, dan estimasi kerugian satu baris.

    Urutan prioritas (nilai input user selalu didahulukan):
    - Harga satuan : kolom harga satuan input -> acuan sektor (tabel referensi).
    - Kerusakan    : nilai kerusakan input -> Jumlah x Harga Satuan x Koefisien Kerusakan.
    - Kerugian     : nilai kerugian input -> 15% x Estimasi Kerusakan (proksi).
    """
    reference_price, reference_basis, _sector_kind = _reference_for_row(row)
    physical_unit = _get_value(row, *PHYSICAL_UNIT_COLUMNS)
    unit_label = str(physical_unit).strip() if physical_unit else 'unit'
    # Harga acuan sektor berlaku per unit/buah/titik; jangan dipakai untuk satuan lain (m, m2, dst).
    reference_unit_mismatch = (
        reference_price is not None and physical_unit is not None
        and _normalize_text(physical_unit) not in REFERENCE_UNITS
    )
    if reference_unit_mismatch:
        reference_price = None
    input_price = _input_amount(row, UNIT_PRICE_COLUMNS)
    if input_price is not None and input_price > 0:
        unit_price = input_price
        price_origin = 'input'
        input_source = _get_value(row, *UNIT_PRICE_SOURCE_COLUMNS)
        price_source = f'Input user ({input_source})' if input_source else 'Input user (kolom Harga Satuan)'
        basis = str(input_source) if input_source else 'Harga satuan dari data input user'
    elif reference_price is not None:
        unit_price = reference_price
        price_origin = 'acuan'
        price_source = f'Acuan sektor: {reference_basis}'
        basis = reference_basis
    elif reference_unit_mismatch:
        unit_price = None
        price_origin = None
        price_source = (
            f'Tidak tersedia: acuan sektor berlaku per unit/titik, tidak cocok dengan satuan "{unit_label}"'
        )
        basis = 'Tidak tersedia'
    else:
        unit_price = None
        price_origin = None
        price_source = 'Tidak tersedia: tidak ada harga input dan sektor/aset tidak cocok dengan acuan'
        basis = 'Tidak tersedia'

    quantity = parse_numeric(_get_value(row, *QUANTITY_COLUMNS))

    percent_input = _get_value(row, *DAMAGE_PERCENT_COLUMNS)
    if percent_input is not None:
        coefficient = _damage_coefficient(percent_input)
        coefficient_label = 'persentase kerusakan input'
    else:
        damage_level = _get_value(row, *DAMAGE_LEVEL_COLUMNS)
        coefficient = _damage_coefficient(damage_level)
        coefficient_label = f'tingkat kerusakan "{damage_level}"' if damage_level is not None else ''

    damage = None
    damage_origin = None
    input_damage = _input_amount(row, DAMAGE_INPUT_COLUMNS)
    if input_damage is not None:
        damage = input_damage
        damage_origin = 'input'
        damage_detail = f'Nilai kerusakan dari data input user = {format_rupiah(damage)}'
        status = 'Kerusakan dari input user'
    elif unit_price is None:
        damage_detail = 'Belum dihitung: harga satuan tidak tersedia'
        status = 'Harga satuan tidak tersedia (isi kolom Harga Satuan atau sesuaikan sektor/aset)'
    elif quantity is None or quantity < 0:
        damage_detail = 'Belum dihitung: jumlah terkena tidak tercatat atau tidak valid'
        status = 'Jumlah terkena tidak tercatat atau tidak valid'
    elif coefficient is None:
        damage_detail = 'Belum dihitung: tingkat kerusakan belum diklasifikasikan'
        status = 'Tingkat kerusakan belum diklasifikasikan'
    else:
        damage = quantity * unit_price * coefficient
        damage_origin = 'hitung'
        damage_detail = (
            f'{_format_number(quantity)} {unit_label} x {format_rupiah(unit_price)} '
            f'x {_format_percent(coefficient)} ({coefficient_label}) = {format_rupiah(damage)}'
        )
        status = (
            'Terhitung dari harga satuan input user'
            if price_origin == 'input'
            else 'Terhitung dengan harga acuan sektor; verifikasi acuan'
        )

    loss = None
    loss_origin = None
    input_loss = _input_amount(row, LOSS_INPUT_COLUMNS)
    if input_loss is not None:
        loss = input_loss
        loss_origin = 'input'
        loss_detail = f'Nilai kerugian dari data input user = {format_rupiah(loss)}'
    elif damage is not None:
        loss = damage * LOSS_PROXY_RATIO
        loss_origin = 'proksi'
        loss_detail = (
            f'{_format_percent(LOSS_PROXY_RATIO)} x {format_rupiah(damage)} (estimasi kerusakan) '
            f'= {format_rupiah(loss)}; proksi, bukan nilai kerugian terukur'
        )
    else:
        loss_detail = 'Belum dihitung: tidak ada nilai kerugian input dan estimasi kerusakan belum tersedia'

    return {
        'Harga Satuan (Rp)': format_rupiah(unit_price),
        'Sumber Harga Satuan': price_source,
        'Dasar Acuan': basis,
        'Koefisien Kerusakan': coefficient,
        'Estimasi Kerusakan (Rp)': format_rupiah(damage),
        'Rincian Kerusakan': damage_detail,
        'Estimasi Kerugian (Rp)': format_rupiah(loss),
        'Rincian Kerugian': loss_detail,
        'Status Estimasi': status,
        '_harga_satuan_numeric': unit_price,
        '_estimasi_kerusakan_numeric': damage,
        '_kerugian_unit_numeric': loss,
        '_sumber_harga': price_origin,
        '_sumber_kerusakan': damage_origin,
        '_sumber_kerugian': loss_origin,
    }


def estimate_dataframe(dataframe):
    """
    Add unit price, damage, and loss estimates (with per-row explanation) to the data.

    Calculation Formula (dipakai hanya jika nilai tidak diisi user):
    - Estimasi Kerusakan = Jumlah Terkena x Harga Satuan x Koefisien Kerusakan
    - Estimasi Kerugian  = 15% x Estimasi Kerusakan (proksi)
    """
    result = dataframe.copy()
    if result.empty:
        for column in ESTIMATE_COLUMNS:
            result[column] = pd.Series(dtype='object')
        return result

    estimates = [estimate_row(row) for _, row in result.iterrows()]
    for column in ESTIMATE_COLUMNS:
        result[column] = [estimate[column] for estimate in estimates]
    return result


def total_numeric(dataframe, column):
    values = pd.to_numeric(dataframe[column], errors='coerce').dropna() if column in dataframe else pd.Series(dtype=float)
    values = values[values.map(math.isfinite)]
    return float(values.sum()), int(values.count())