import csv
import base64
import json
import mimetypes
import os
import re

import folium
import requests
from folium import plugins

# Pusat peta Bali
BALI_LAT = -8.4095
BALI_LON = 115.1889

BALI_COORDS = {
    'denpasar': [-8.6705, 115.2126],
    'badung': [-8.5816, 115.1776],
    'buleleng': [-8.1120, 115.0882],
    'tabanan': [-8.4310, 115.0743],
    'gianyar': [-8.4419, 115.3090],
    'klungkung': [-8.5366, 115.4143],
    'bangli': [-8.2863, 115.3533],
    'karangasem': [-8.3759, 115.5458],
    'jembrana': [-8.3245, 114.6190],
    'tabanan': [-8.4310, 115.0743],
    'singaraja': [-8.1120, 115.0882],
    'bali': [BALI_LAT, BALI_LON],
}

BOUNDARY_URLS = {
    'Kabupaten/Kota': 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IDN_2.json',
    'Kecamatan': 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IDN_3.json',
    'Desa': 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IDN_4.json',
}
BOUNDARY_CACHE_FILES = {
    'Kabupaten/Kota': 'bali_boundaries_kabupaten.geojson',
    'Kecamatan': 'bali_boundaries_kecamatan.geojson',
    'Desa': 'bali_boundaries_desa.geojson',
}
_BOUNDARY_CACHE = {}


def _boundary_cache_path(level):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(repo_root, 'Library', BOUNDARY_CACHE_FILES[level])


def _normalize_location_name(value):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    text = text.lower()
    text = re.sub(r'\b(kabupaten|kab|kota|provinsi|kecamatan|kec|desa|kelurahan|kel)\b', ' ', text)
    return re.sub(r'[^a-z0-9]', '', text)


def _location_parts(item):
    return {
        'kabupaten': _normalize_location_name(
            item.get('kabupaten') or item.get('kabupaten_kota') or item.get('kota') or item.get('regency')
        ),
        'kecamatan': _normalize_location_name(
            item.get('kecamatan') or item.get('kec') or item.get('subdistrict')
        ),
        'desa': _normalize_location_name(
            item.get('desa') or item.get('kelurahan') or item.get('village')
        ),
    }


def _parse_numeric_coord(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    text = str(raw_value).strip()
    if not text:
        return None
    nums = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', text)
    if not nums:
        return None
    return float(nums[0])


def _parse_marker_count(item):
    """Return how many incidents a single input row represents."""
    for key in (
        'incident_count',
        'jumlah_bencana',
        'jumlah_bencana_terdampak',
        'affected_quantity',
        'jumlah_terdampak',
        'jumlah_kejadian',
        'jumlah_kasus',
    ):
        value = item.get(key)
        if value is None or not str(value).strip():
            continue
        numbers = re.findall(r'\d+(?:[.,]\d+)?', str(value))
        if numbers:
            count = int(float(numbers[0].replace(',', '.')))
            return max(count, 1)
    return 1


SEVERITY_ORDER = {'Tidak ada kejadian': 0, 'Tidak terdampak': 0, 'Ringan': 1, 'Sedang': 2, 'Berat': 3}
SEVERITY_PALETTE = {
    'Tidak ada kejadian': '#94a3b8',
    'Tidak terdampak': '#94a3b8',
    'Ringan': '#16a34a',
    'Sedang': '#eab308',
    'Berat': '#dc2626',
    'Tidak ada data': '#e2e8f0',
    'Campuran': '#64748b',
}


def _normalize_severity(value):
    text = str(value or '').strip().lower()
    if not text or text in ('nan', 'none', 'null', '-', '0'):
        return 'Tidak ada data'
    if any(term in text for term in ('tidak ada kejadian', 'tidak terjadi kejadian', 'nihil kejadian')):
        return 'Tidak ada kejadian'
    if any(term in text for term in (
            'tidak terdampak',
            'tidak terkena',
            'tidak ada kerusakan',
            'tidak ada kerusakan pasca kejadian',
            'tidak ditemukan kerusakan',
            'tidak ada dampak',
            'tanpa kerusakan',
            'tidak rusak',
            'nihil',
            'aman',
        )):
        return 'Tidak terdampak'
    if any(term in text for term in ('berat', 'tinggi', 'high', 'parah', 'severe')):
        return 'Berat'
    if any(term in text for term in ('ringan', 'rendah', 'low', 'minor')):
        return 'Ringan'
    if any(term in text for term in ('sedang', 'medium', 'moderate', 'cukup', 'normal')):
        return 'Sedang'
    return 'Tidak ada data'


def _get_normalized_severity(item):
    damage_value = _get_damage_value(item)
    if damage_value:
        return _normalize_severity(damage_value)
    event_value = item.get('disaster_type') or item.get('jenis_bencana') or item.get('kejadian') or ''
    event_severity = _normalize_severity(event_value)
    return event_severity if event_severity == 'Tidak ada kejadian' else 'Tidak ada data'


def _get_damage_value(item):
    for key in ('Tingkat_Kerusakan', 'damage_level', 'tingkat_kerusakan', 'severity'):
        value = item.get(key)
        if value is not None and str(value).strip():
            return value
    return ''


def resolve_location_coordinates(location, fallback=None):
    """Use OpenStreetMap Nominatim to get a live coordinate for the given location."""
    normalized = _normalize_location_name(location)
    if not normalized:
        return fallback

    lower_name = normalized.lower()
    for kab, coords in BALI_COORDS.items():
        if kab in lower_name:
            return tuple(coords)

    headers = {'User-Agent': 'DALA-SPK/1.0 (map integration)'}
    params = {
        'q': f"{normalized}, Bali, Indonesia",
        'format': 'jsonv2',
        'limit': 1,
    }

    try:
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params=params,
            headers=headers,
            timeout=8,
        )
        if response.ok:
            payload = response.json()
            if payload:
                return float(payload[0]['lat']), float(payload[0]['lon'])
    except Exception:
        pass

    return fallback


def _photo_data_uri(photo_path):
    if not photo_path:
        return ''
    if str(photo_path).startswith(('http://', 'https://', 'data:')):
        return str(photo_path)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    abs_path = str(photo_path) if os.path.isabs(str(photo_path)) else os.path.join(repo_root, str(photo_path))
    if not os.path.isfile(abs_path):
        return ''

    mime_type = mimetypes.guess_type(abs_path)[0] or 'application/octet-stream'
    try:
        with open(abs_path, 'rb') as image_file:
            encoded = base64.b64encode(image_file.read()).decode('ascii')
        return f'data:{mime_type};base64,{encoded}'
    except OSError:
        return ''


def _prepare_locations_for_map(data=None, filter_level='Semua'):
    locations_to_plot = []

    if data is not None:
        for idx, item in enumerate(data):
            damage_value = _get_damage_value(item)
            sev = _get_normalized_severity(item)

            locations_to_plot.append({
                'id': item.get('id', f"DOC-{idx+1}"),
                'asset': item.get('asset', 'Aset tidak diketahui'),
                'loc': item.get('location', item.get('lokasi', 'Lokasi Tidak Diketahui')),
                'kabupaten': item.get('kabupaten', item.get('kabupaten_kota', item.get('kota', item.get('regency', '')))),
                'kecamatan': item.get('kecamatan', item.get('kec', item.get('subdistrict', ''))),
                'desa': item.get('desa', item.get('kelurahan', item.get('village', ''))),
                'sec': item.get('sector', 'Lainnya'),
                'cost': item.get('cost', '0'),
                'incident_count': item.get('incident_count', item.get('jumlah_bencana', '1')),
                'affected_quantity': item.get('affected_quantity', item.get('jumlah_terdampak', '')),
                'asset_damage_est': item.get('asset_damage_est', '0'),
                'economic_loss_est': item.get('economic_loss_est', '0'),
                'sev': sev,
                'photo': item.get('photo', ''),
                'description': item.get('evidence', item.get('description', 'Tidak ada keterangan kerusakan')),
                'damage_level': damage_value,
                'disaster_type': item.get('disaster_type', 'Tidak diketahui'),
                'latitude': item.get('latitude', item.get('lat')),
                'longitude': item.get('longitude', item.get('lon')),
            })

    filtered = []
    for item in locations_to_plot:
        if filter_level != 'Semua' and item['sev'] != filter_level:
            continue
        lat = _parse_numeric_coord(item.get('latitude'))
        lon = _parse_numeric_coord(item.get('longitude'))

        item['lat'] = float(lat) if lat is not None else None
        item['lon'] = float(lon) if lon is not None else None
        filtered.append(item)

    return filtered


def _count_input_rows_for_map(data=None, filter_level='Semua'):
    """Count user input rows, keeping the map summary aligned with the data list."""
    if not data:
        return 0

    total = 0
    for item in data:
        severity = _get_normalized_severity(item)
        if filter_level == 'Semua' or severity == filter_level:
            total += 1
    return total


def _geometry_bounds(geometry):
    coordinates = geometry.get('coordinates', []) if geometry else []
    values = []

    def collect(items):
        if isinstance(items, (list, tuple)) and len(items) >= 2 and all(isinstance(value, (int, float)) for value in items[:2]):
            values.append((items[0], items[1]))
            return
        for item in items if isinstance(items, (list, tuple)) else []:
            collect(item)

    collect(coordinates)
    if not values:
        return None
    longitudes, latitudes = zip(*values)
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def _point_in_ring(point, ring):
    longitude, latitude = point
    inside = False
    for index in range(len(ring)):
        previous = ring[index - 1]
        current = ring[index]
        crosses_latitude = (current[1] > latitude) != (previous[1] > latitude)
        if crosses_latitude:
            edge_longitude = (previous[0] - current[0]) * (latitude - current[1]) / (previous[1] - current[1]) + current[0]
            if longitude < edge_longitude:
                inside = not inside
    return inside


def _point_in_geometry(point, geometry):
    if not geometry:
        return False
    geometry_type = geometry.get('type')
    coordinates = geometry.get('coordinates', [])
    if geometry_type == 'Polygon':
        return bool(coordinates) and _point_in_ring(point, coordinates[0])
    if geometry_type == 'MultiPolygon':
        return any(_point_in_ring(point, polygon[0]) for polygon in coordinates if polygon)
    return False


def _load_bali_boundaries(level):
    if level in _BOUNDARY_CACHE:
        return _BOUNDARY_CACHE[level]

    cache_path = _boundary_cache_path(level)
    payload = None
    try:
        with open(cache_path, 'r', encoding='utf-8') as cache_file:
            payload = json.load(cache_file)
    except (OSError, ValueError):
        try:
            response = requests.get(BOUNDARY_URLS[level], timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (OSError, requests.RequestException, ValueError):
            _BOUNDARY_CACHE[level] = None
            return None

    bali_features = [
        feature for feature in payload.get('features', [])
        if str(feature.get('properties', {}).get('NAME_1', '')).strip().casefold() == 'bali'
    ]
    boundary = {'type': 'FeatureCollection', 'features': bali_features}
    if bali_features and not os.path.exists(cache_path):
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as cache_file:
                json.dump(boundary, cache_file, ensure_ascii=False)
        except OSError:
            pass
    _BOUNDARY_CACHE[level] = boundary
    return boundary


def _boundary_name(feature, level):
    properties = feature.get('properties', {})
    if level == 'Desa':
        keys = ('NAME_4', 'NAME_3', 'NAME_2')
    elif level == 'Kecamatan':
        keys = ('NAME_3', 'NAME_2')
    else:
        keys = ('NAME_2',)
    names = [str(properties[key]) for key in keys if properties.get(key)]
    return ', '.join(names) if names else 'Wilayah Bali'


def _boundary_identifier(feature, level):
    properties = feature.get('properties', {})
    id_key = {'Kabupaten/Kota': 'GID_2', 'Kecamatan': 'GID_3', 'Desa': 'GID_4'}[level]
    return properties.get(id_key) or _boundary_name(feature, level)


def _matches_boundary_name(item, feature, level):
    properties = feature.get('properties', {})
    parts = _location_parts(item)
    expected = {
        'kabupaten': _normalize_location_name(properties.get('NAME_2')),
        'kecamatan': _normalize_location_name(properties.get('NAME_3')),
        'desa': _normalize_location_name(properties.get('NAME_4')),
    }
    if level == 'Kabupaten/Kota':
        candidate = parts['kabupaten']
        if not candidate:
            candidate = _normalize_location_name(item.get('loc'))
        return bool(candidate and candidate == expected['kabupaten'])
    if level == 'Kecamatan':
        return bool(
            parts['kabupaten'] and parts['kecamatan']
            and parts['kabupaten'] == expected['kabupaten']
            and parts['kecamatan'] == expected['kecamatan']
        )
    return bool(
        parts['kabupaten'] and parts['kecamatan'] and parts['desa']
        and parts['kabupaten'] == expected['kabupaten']
        and parts['kecamatan'] == expected['kecamatan']
        and parts['desa'] == expected['desa']
    )


def _matches_boundary_point(item, feature, bounds):
    if item['lat'] is None or item['lon'] is None:
        return False
    if not bounds:
        return False
    min_lon, min_lat, max_lon, max_lat = bounds
    if not (min_lon <= item['lon'] <= max_lon and min_lat <= item['lat'] <= max_lat):
        return False
    properties = feature.get('properties', {})
    parts = _location_parts(item)
    expected = {
        'kabupaten': _normalize_location_name(properties.get('NAME_2')),
        'kecamatan': _normalize_location_name(properties.get('NAME_3')),
        'desa': _normalize_location_name(properties.get('NAME_4')),
    }
    if any(value and value != expected[key] for key, value in parts.items()):
        return False
    return _point_in_geometry((item['lon'], item['lat']), feature.get('geometry'))


def _severity_rank(value):
    return SEVERITY_ORDER.get(value, 0)


def _dominant_severity(severity_counts):
    highest_count = max(severity_counts.values(), default=0)
    if highest_count == 0:
        return 'Tidak ada data'
    dominant = [severity for severity, count in severity_counts.items() if count == highest_count]
    return dominant[0] if len(dominant) == 1 else 'Campuran'


def _build_boundary_values(boundary, locations, level):
    severity_labels = ('Tidak ada kejadian', 'Tidak terdampak', 'Ringan', 'Sedang', 'Berat', 'Tidak ada data')
    if level == 'Kabupaten/Kota':
        key_fields = ('kabupaten',)
    elif level == 'Kecamatan':
        key_fields = ('kabupaten', 'kecamatan')
    else:
        key_fields = ('kabupaten', 'kecamatan', 'desa')

    feature_entries = []
    boundary_index = {}
    values = {}
    for feature in boundary.get('features', []):
        properties = feature.get('properties', {})
        boundary_id = _boundary_identifier(feature, level)
        key = tuple(_normalize_location_name(properties.get(name)) for name in (
            {'kabupaten': 'NAME_2', 'kecamatan': 'NAME_3', 'desa': 'NAME_4'}[field]
            for field in key_fields
        ))
        boundary_index[key] = boundary_id
        values[boundary_id] = dict.fromkeys(severity_labels, 0)
        feature_entries.append((feature, boundary_id, _geometry_bounds(feature.get('geometry'))))

    for item in locations:
        parts = _location_parts(item)
        key = tuple(parts[field] for field in key_fields)
        boundary_id = boundary_index.get(key) if all(key) else None
        if boundary_id is not None:
            values[boundary_id][item['sev']] += 1
            continue

        for feature, boundary_id, bounds in feature_entries:
            if _matches_boundary_point(item, feature, bounds):
                values[boundary_id][item['sev']] += 1

    values = {
        boundary_id: {
            'count': sum(severity_counts.values()),
            'severity': _severity_rank(_dominant_severity(severity_counts)),
            'dominant_severity': _dominant_severity(severity_counts),
            'severity_counts': severity_counts,
        }
        for boundary_id, severity_counts in values.items()
    }
    return values


def _add_boundary_layer(m, level, locations):
    boundary = _load_bali_boundaries(level)
    if not boundary or not boundary.get('features'):
        return

    values = _build_boundary_values(boundary, locations, level)
    for feature in boundary.get('features', []):
        name = _boundary_name(feature, level)
        boundary_id = _boundary_identifier(feature, level)
        value = values.get(boundary_id, {'count': 0, 'severity': 0, 'dominant_severity': 'Tidak ada data', 'severity_counts': {}})
        feature.setdefault('properties', {}).update({
            '_map_name': name,
            '_map_count': value['count'],
            '_map_severity': value.get('dominant_severity', 'Tidak ada data'),
            '_map_breakdown': ' | '.join(
                f'{severity}: {value.get("severity_counts", {}).get(severity, 0)}'
                for severity in ('Berat', 'Sedang', 'Ringan', 'Tidak terdampak', 'Tidak ada kejadian')
            ),
        })

    def style_function(feature):
        value = values.get(_boundary_identifier(feature, level), {'severity': 0, 'dominant_severity': 'Tidak ada data'})
        severity_name = value.get('dominant_severity', 'Tidak ada data')
        is_unreported = severity_name in {'Tidak ada data', 'Tidak ada kejadian', 'Tidak terdampak'}
        return {
            'fillColor': SEVERITY_PALETTE.get(severity_name, SEVERITY_PALETTE['Tidak ada data']),
            'color': '#475569',
            'weight': 1.1 if level == 'Kabupaten/Kota' else 0.55,
            'fillOpacity': 0.88 if is_unreported else (0.78 if level == 'Kabupaten/Kota' else 0.68),
        }

    def highlight_function(feature):
        return {'weight': 2.2, 'color': '#0f172a', 'fillOpacity': 0.55}

    folium.GeoJson(
        boundary,
        name=f'Choropleth {level}',
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=['_map_name', '_map_severity', '_map_count', '_map_breakdown'],
            aliases=['Wilayah', 'Klasifikasi dominan', 'Jumlah data input', 'Rincian tingkat kerusakan'],
            labels=True,
            localize=True,
            sticky=False,
            style='background-color: white; color: #0f172a; font-family: Arial; font-size: 12px; padding: 8px;',
        ),
    ).add_to(m)


def build_geojson(data=None, filter_level='Semua'):
    geojson = {'type': 'FeatureCollection', 'features': []}

    for item in _prepare_locations_for_map(data, filter_level):
        if item['lat'] is None or item['lon'] is None:
            continue
        geojson['features'].append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [item['lon'], item['lat']]
            },
            'properties': {
                'id': item.get('id', 'DOC-1'),
                'asset': item.get('asset', 'Aset tidak diketahui'),
                'location': item.get('loc', 'Lokasi Tidak Diketahui'),
                'kabupaten': item.get('kabupaten', ''),
                'kecamatan': item.get('kecamatan', ''),
                'desa': item.get('desa', ''),
                'sector': item.get('sec', 'Lainnya'),
                'cost': item.get('cost', '0'),
                'damage_level': item.get('damage_level') or 'Tidak ada data',
                'disaster_type': item.get('disaster_type', 'Tidak diketahui'),
                'severity': item.get('sev', 'Tidak ada data'),
            },
        })

    return geojson


def export_geojson(data=None, path=None, filter_level='Semua'):
    payload = build_geojson(data, filter_level)
    if path is None:
        return payload
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def export_csv(data=None, path=None, filter_level='Semua'):
    rows = []
    for item in _prepare_locations_for_map(data, filter_level):
        rows.append({
            'id': item.get('id', 'DOC-1'),
            'asset': item.get('asset', 'Aset tidak diketahui'),
            'location': item.get('loc', 'Lokasi Tidak Diketahui'),
            'kabupaten': item.get('kabupaten', ''),
            'kecamatan': item.get('kecamatan', ''),
            'desa': item.get('desa', ''),
            'sector': item.get('sec', 'Lainnya'),
            'cost': item.get('cost', '0'),
            'damage_level': item.get('damage_level') or 'Tidak ada data',
            'severity': item.get('sev', 'Tidak ada data'),
            'disaster_type': item.get('disaster_type', 'Tidak diketahui'),
            'latitude': item.get('lat'),
            'longitude': item.get('lon'),
        })

    if path is None:
        return rows

    with open(path, 'w', encoding='utf-8', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=['id', 'asset', 'location', 'kabupaten', 'kecamatan', 'desa', 'sector', 'cost', 'damage_level', 'severity', 'disaster_type', 'latitude', 'longitude'])
        writer.writeheader()
        writer.writerows(rows)
    return path


def create_location_map(filter_level='Semua', data=None):
    """
    Creates a Folium map centered on Bali using live OpenStreetMap tiles and a GIS dashboard style.
    filter_level: 'Semua', 'Berat', 'Sedang', 'Ringan', 'Tidak terdampak'
    """
    m = folium.Map(
        location=[BALI_LAT, BALI_LON],
        zoom_start=8.5,
        tiles='OpenStreetMap',
        control_scale=True,
    )

    plugins.Fullscreen(position='topright').add_to(m)
    plugins.MeasureControl(position='topright').add_to(m)

    locations_to_plot = _prepare_locations_for_map(data, filter_level)
    # Keep the initial Bali overview stable; users can zoom manually to a marker.

    _add_boundary_layer(m, 'Kabupaten/Kota', locations_to_plot)
    _add_boundary_layer(m, 'Kecamatan', locations_to_plot)
    _add_boundary_layer(m, 'Desa', locations_to_plot)

    legend_html = f"""
    <div style="position: fixed; bottom: 20px; right: 20px; z-index: 9999; background: rgba(15, 23, 42, 0.88); color: white; border-radius: 12px; padding: 12px 14px; font-family: Arial, sans-serif; font-size: 12px; border: 1px solid rgba(148, 163, 184, 0.3); box-shadow: 0 10px 25px rgba(15, 23, 42, 0.25);">
        <div style="font-weight:700; margin-bottom:8px;">Choropleth Wilayah</div>
        <div style="margin-bottom:8px; color:#cbd5e1;">Layer kabupaten, kecamatan, dan desa</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Berat']}; margin-right:8px;"></span>Berat</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Sedang']}; margin-right:8px;"></span>Sedang</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Ringan']}; margin-right:8px;"></span>Rendah / Ringan</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Tidak terdampak']}; margin-right:8px;"></span>Tidak terdampak / tidak rusak</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Tidak ada kejadian']}; margin-right:8px;"></span>Tidak ada kejadian</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Tidak ada data']}; border:1px solid #94a3b8; margin-right:8px;"></span>Tidak ada data</div>
        <div><span style="display:inline-block; width:22px; height:12px; background:{SEVERITY_PALETTE['Campuran']}; margin-right:8px;"></span>Campuran (jumlah seri)</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    summary_html = f"""
    <div style="position: fixed; top: 12px; left: 55px; z-index: 9999; background: rgba(15, 23, 42, 0.9); color: white; border-radius: 8px; padding: 8px 12px; font-family: Arial, sans-serif; font-size: 12px; box-shadow: 0 4px 12px rgba(15,23,42,0.25);">
        Jumlah data input: <b>{_count_input_rows_for_map(data, filter_level)}</b>
    </div>
    """
    m.get_root().html.add_child(folium.Element(summary_html))
    folium.LayerControl(position='topright').add_to(m)
    return m._repr_html_()
