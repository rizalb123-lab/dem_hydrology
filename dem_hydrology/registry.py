# -*- coding: utf-8 -*-
"""
Registri analisis: satu sumber kebenaran untuk dialog, pipeline, Excel, dan PDF.
Setiap analisis memuat nama asli (Inggris), kelompok, parameter yang bisa diubah,
keluaran, rumus, batasan, dan kunci pustaka (references.py).
"""
from collections import OrderedDict

from .references import REFS
from . import i18n


def P(key, label, typ, default, lo=None, hi=None, step=None, unit="", help="", choices=None):
    return dict(key=key, label=label, type=typ, default=default, min=lo, max=hi, step=step,
                unit=unit, help=help, choices=choices)


def A(key, group, name, desc, outputs, refs, formula="", limits="", params=None):
    return dict(key=key, group=group, name=name, desc=desc, outputs=outputs, refs=refs,
                formula=formula, limits=limits, params=params or [])


G_PRE = "1. Pra-pemrosesan DEM"
G_TER = "2. Morfologi Permukaan (Terrain)"
G_FLOW = "3. Arah dan Akumulasi Aliran (Flow Routing)"
G_NET = "4. Jaringan Sungai (Stream Network)"
G_BAS = "5. Daerah Aliran Sungai (Watershed)"
G_IDX = "6. Indeks Hidro-Topografi"
G_FLD = "7. Genangan dan Banjir (Berbasis Topografi)"
G_CMP = "8. Indeks Komposit (Turunan Gabungan Keluaran DEM)"

GROUPS = [G_PRE, G_TER, G_FLOW, G_NET, G_BAS, G_IDX, G_FLD, G_CMP]

# parameter inti yang berlaku untuk seluruh proses
CORE_PARAMS = [
    P("buffer_m", "Buffer DEM di luar batas studi", "float", 1000.0, 0, 20000, 100, "m",
      "DEM dipotong lebih luas dari batas studi agar luas tangkapan hulu yang berada di luar batas ikut "
      "terhitung. Hasil tetap dipotong pada batas studi."),
    P("max_cells", "Maksimum jumlah sel analisis", "float", 4.0, 0.2, 40, 0.5, "juta sel",
      "Bila DEM lebih rapat, grid dikecilkan otomatis (resampling) agar proses tetap wajar."),
    P("fill_slope_deg", "Kemiringan minimum saat pengisian cekungan", "float", 0.01, 0.0, 1.0, 0.005, "derajat",
      "Memaksa gradien kecil pada area datar agar arah aliran terdefinisi (setara Wang & Liu 2006)."),
    P("stream_thr_ha", "Ambang luas tangkapan sungai", "float", 25.0, 0.1, 100000, 5, "ha",
      "Sel dengan luas tangkapan hulu >= ambang dianggap sungai. Sesuaikan dengan peta sungai/citra. "
      "Dipakai oleh seluruh analisis jaringan sungai, DAS, HAND, dan turunannya."),
]

ANALYSES = OrderedDict()


def add(a):
    ANALYSES[a["key"]] = a


# ----------------------------------------------------------------------------- 1. Pra-pemrosesan
add(A("fill", G_PRE, "Fill Sinks (Priority-Flood)",
      "Mengisi cekungan palsu dan memberi gradien minimum pada area datar sehingga setiap sel punya jalur "
      "keluar. Hasilnya (Conditioned DEM) menjadi dasar seluruh analisis aliran.",
      [("filled_dem", "Filled DEM (Conditioned)", "raster")],
      ["barnes2014", "wang2006", "garbrecht1997"],
      "Priority-Flood: sel dipanen dari titik keluar menuju hulu menurut elevasi terendah; z_baru = max(z, z_tetangga + e), "
      "e = tan(kemiringan minimum) x jarak.",
      "Cekungan sungguhan (danau, rawa, kolam) ikut terisi. Kemiringan paksa pada area datar luas dapat menaikkan "
      "elevasi hingga beberapa meter; jangan memakai Filled DEM untuk elevasi, hanya untuk aliran."))
add(A("depressions", G_PRE, "Sink / Depression Analysis",
      "Menemukan cekungan tertutup pada DEM dan menghitung kedalaman, luas, serta volumenya.",
      [("sink_depth", "Sink Depth", "raster"), ("depressions", "Depressions (Polygon)", "vector_poly")],
      ["barnes2014", "wang2006"],
      "Kedalaman = DEM terisi (tanpa gradien paksa) - DEM asli. Volume = jumlah(kedalaman) x luas sel.",
      "Pada DEM resolusi kasar atau DSM, banyak cekungan adalah artefak (kanopi, bangunan, kesalahan interpolasi).",
      [P("min_depth", "Kedalaman minimum cekungan", "float", 0.1, 0.0, 50, 0.05, "m",
         "Cekungan yang lebih dangkal dari ini diabaikan.")]))

# ----------------------------------------------------------------------------- 2. Terrain
add(A("slope", G_TER, "Slope",
      "Kemiringan lereng dari DEM, dikelaskan menurut kriteria kelas lereng yang lazim dipakai dalam tata ruang.",
      [("slope_pct", "Slope (%)", "raster"), ("slope_class", "Slope Class", "raster")],
      ["horn1981", "mentan1980"],
      "tan b = sqrt((dz/dx)^2 + (dz/dy)^2) dengan kernel Horn 3x3; slope% = 100 tan b.",
      "Akurasi bergantung resolusi dan jenis DEM (DSM menaikkan kemiringan di vegetasi/bangunan).",
      [P("breaks", "Batas kelas lereng (%)", "floatlist", "8,15,25,45", help="Default: SK Mentan 837/1980.")]))
add(A("aspect", G_TER, "Aspect",
      "Arah hadap lereng (azimut arah menurun), dikelaskan 8 arah mata angin.",
      [("aspect", "Aspect", "raster")], ["horn1981"],
      "Aspect = atan2(-dz/dx, -dz/dy) (azimut kompas); sel datar diberi kelas Flat.",
      "Tidak bermakna pada area datar."))
add(A("hillshade", G_TER, "Hillshade",
      "Bayangan relief untuk membaca bentuk permukaan.",
      [("hillshade", "Hillshade", "raster")], ["horn1981"],
      "Hillshade = 255 (cos(zenit) cos(b) + sin(zenit) sin(b) cos(az - aspek)).",
      "Hanya visualisasi, bukan besaran fisik.",
      [P("azimuth", "Azimut sumber cahaya", "float", 315.0, 0, 360, 5, "derajat"),
       P("altitude", "Tinggi sumber cahaya", "float", 45.0, 5, 90, 5, "derajat"),
       P("z_factor", "Pengali vertikal (Z factor)", "float", 1.0, 0.1, 20, 0.1, "x")]))
add(A("curvature", G_TER, "Curvature (Profile & Plan)",
      "Kelengkungan permukaan: profil (searah lereng, mengontrol percepatan aliran) dan plan (melintang lereng, "
      "mengontrol konvergensi/divergensi aliran). Positif = cembung, negatif = cekung.",
      [("profile_curvature", "Profile Curvature", "raster"), ("plan_curvature", "Plan Curvature", "raster")],
      ["zevenbergen1987"],
      "Polinom orde-2 pada jendela 3x3; satuan 100/m.",
      "Sensitif terhadap derau DEM; pertimbangkan penghalusan DEM bila hasil terlalu bising."))
add(A("tpi", G_TER, "Topographic Position Index (TPI)",
      "Selisih elevasi sel terhadap rata-rata elevasi lingkungannya: positif = punggungan, negatif = lembah.",
      [("tpi", "TPI", "raster")], ["weiss2001"],
      "TPI = z - rata-rata(z dalam lingkaran berjari-jari R).",
      "Hasil bergantung pada jari-jari yang dipilih (skala bentang alam).",
      [P("radius_m", "Jari-jari lingkungan", "float", 300.0, 20, 20000, 10, "m")]))
add(A("tri", G_TER, "Terrain Ruggedness Index (TRI)",
      "Ukuran kekasaran permukaan: akar jumlah kuadrat selisih elevasi sel dengan 8 tetangganya.",
      [("tri", "TRI", "raster")], ["riley1999"], "TRI = sqrt(jumlah (z_tetangga - z_pusat)^2).",
      "Tergantung ukuran sel."))
add(A("landform", G_TER, "Landform Classification (TPI)",
      "Klasifikasi 10 bentuk lahan dari TPI terstandar pada dua skala dan kemiringan.",
      [("landform", "Landform Classification", "raster")], ["weiss2001"],
      "Kelas ditentukan dari TPI skala kecil dan besar terstandar (batas -1 dan +1 simpangan baku) dan kemiringan.",
      "Skala kecil/besar harus sesuai ukuran bentuk lahan di kawasan.",
      [P("r_small", "Jari-jari skala kecil", "float", 100.0, 20, 5000, 10, "m"),
       P("r_large", "Jari-jari skala besar", "float", 500.0, 50, 20000, 10, "m"),
       P("flat_deg", "Batas kemiringan dataran", "float", 5.0, 0.5, 30, 0.5, "derajat")]))

# ----------------------------------------------------------------------------- 3. Flow routing
add(A("flow_dir_d8", G_FLOW, "Flow Direction (D8)",
      "Arah aliran ke satu tetangga dengan penurunan terbesar. Kode arah gaya ESRI.",
      [("flow_dir_d8", "Flow Direction (D8)", "raster")], ["ocallaghan1984", "jenson1988"],
      "Penerima = tetangga dengan (z_pusat - z_tetangga) / jarak maksimum. Kode: 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE.",
      "Aliran hanya ke satu sel sehingga cenderung membentuk jalur paralel di lereng terbuka."))
add(A("flow_acc_d8", G_FLOW, "Flow Accumulation / Catchment Area (D8)",
      "Luas tangkapan hulu setiap sel (upslope contributing area) dengan arah aliran D8.",
      [("catchment_area_d8", "Catchment Area (D8)", "raster")], ["ocallaghan1984", "jenson1988"],
      "A = jumlah sel di hulu (termasuk sel itu) x luas sel. Satuan: ha.",
      "Luas hanya mencakup bagian DEM yang dimuat; gunakan buffer agar hulu di luar batas studi ikut terhitung."))
add(A("flow_dinf", G_FLOW, "D-Infinity Flow Direction and Specific Catchment Area",
      "Arah aliran kontinu (sudut) dan pembagian aliran ke dua tetangga; menghasilkan luas tangkapan spesifik (SCA).",
      [("dinf_angle", "D-Infinity Flow Direction", "raster"), ("dinf_sca", "D-Infinity Specific Catchment Area", "raster")],
      ["tarboton1997"],
      "Sudut = arah lereng terbesar pada 8 segitiga fasetnya; proporsi ke dua penerima menurut sudut. SCA = A / lebar sel (m2/m).",
      "Lebih realistis di lereng terbuka daripada D8, tetapi mendifusikan aliran di alur sempit."))
add(A("flow_mfd", G_FLOW, "Multiple Flow Direction (MFD) Catchment Area",
      "Aliran dibagi ke semua tetangga yang lebih rendah menurut kemiringan; cocok untuk lereng dan indeks kebasahan.",
      [("mfd_area", "Catchment Area (MFD)", "raster"), ("mfd_sca", "Specific Catchment Area (MFD)", "raster")],
      ["quinn1991", "freeman1991"],
      "Proporsi f_i = (tan b_i^p L_i) / jumlah(...). Quinn: L = 0,5 (kardinal) dan 0,354 (diagonal) sel; Freeman: tanpa L. SCA = A / jumlah L.",
      "Menyebar di sepanjang alur sehingga luas tangkapan sungai terlihat 'kabur'; sungai sebaiknya diekstraksi dari D8.",
      [P("method", "Metode bobot", "choice", "quinn", choices=[("quinn", "Quinn et al. (1991)"), ("freeman", "Freeman (1991)")]),
       P("p", "Eksponen kemiringan p", "float", 1.1, 0.5, 10, 0.1, "", "Freeman (1991) menyarankan 1,1.")]))
add(A("flow_length", G_FLOW, "Flow Path Length",
      "Jarak aliran menuju titik keluar (downstream) dan jarak aliran terpanjang ke hulu (upstream) menurut D8.",
      [("flow_len_down", "Flow Length (Downstream)", "raster"), ("flow_len_up", "Flow Length (Upstream, longest)", "raster")],
      ["jenson1988"],
      "Jumlah jarak langkah D8 (sel atau sel x sqrt2) sepanjang jalur aliran.",
      "Titik keluar adalah tepi DEM/area valid, bukan selalu muara sebenarnya."))

# ----------------------------------------------------------------------------- 4. Jaringan sungai
add(A("stream_network", G_NET, "Stream Network, Strahler Order and Shreve Magnitude",
      "Mengekstraksi jaringan sungai dari ambang luas tangkapan, lalu memberi orde Strahler, magnitudo Shreve, "
      "panjang, dan kemiringan tiap ruas (link).",
      [("stream_lines", "Stream Network (Strahler Order)", "vector_line"),
       ("strahler_raster", "Strahler Order", "raster"), ("shreve_raster", "Shreve Magnitude", "raster")],
      ["ocallaghan1984", "strahler1957", "shreve1966", "montgomery1992"],
      "Sungai: A >= ambang. Strahler: orde naik satu bila dua ruas berorde sama bertemu. Shreve: jumlah sumber di hulu.",
      "Jaringan hasil DEM mengikuti ambang yang dipilih, bukan sungai nyata; validasi dengan citra atau peta RBI."))

# ----------------------------------------------------------------------------- 5. DAS
add(A("subbasins", G_BAS, "Sub-Watershed Delineation (Strahler order >= N)",
      "Membagi area menjadi sub-DAS: setiap ruas sungai berorde >= N dengan seluruh DAS lokal ruas berorde lebih rendah "
      "yang bermuara kepadanya. N = 1 menghasilkan DAS lokal tiap ruas.",
      [("subbasins", "Sub-Watersheds", "vector_poly")],
      ["strahler1957", "jenson1988"],
      "Setiap sel dilabeli ruas sungai tempat alirannya bermuara, lalu ruas berorde < N digabung ke ruas hilirnya.",
      "Batas sub-DAS mengikuti pembagian sel D8 (bergerigi) dan bergantung ambang sungai.",
      [P("min_order", "Orde Strahler minimum (N)", "int", 3, 1, 10, 1, "",
         "Makin besar N, makin sedikit dan makin luas sub-DAS.")]))
add(A("watershed_points", G_BAS, "Watershed from Pour Points",
      "DAS dari titik outlet yang ditentukan pengguna (layer titik). Titik di-snap ke sel dengan akumulasi tertinggi di "
      "sekitarnya; DAS yang bersarang dihitung penuh.",
      [("pour_points", "Pour Points (snapped)", "vector_point"), ("watersheds", "Watersheds", "vector_poly")],
      ["jenson1988"],
      "DAS = seluruh sel yang jalur alirannya melewati sel outlet.",
      "Butuh layer titik pada tab Data.",
      [P("snap_m", "Radius snapping titik ke sungai", "float", 100.0, 0, 5000, 10, "m",
         "Titik dipindah ke sel beraliran tertinggi dalam radius ini; titik yang digeser terlalu jauh dilaporkan.")]))
add(A("basin_morphometry", G_BAS, "Basin Morphometry and Hypsometry",
      "Parameter morfometri tiap DAS/sub-DAS (area, keliling, panjang, bentuk, relief, kerapatan drainase, rasio "
      "percabangan, kemiringan alur utama, waktu konsentrasi) dan kurva hipsometrik.",
      [("morphometry", "Morphometry Table", "table")],
      ["horton1932", "horton1945", "strahler1952", "strahler1957", "schumm1956", "miller1953", "gravelius1914",
       "melton1957", "pike1971", "smith1950", "faniran1968", "kirpich1940", "giandotti1934", "taylor1952"],
      "Rf = A/Lb^2; Re = 1,128 sqrt(A)/Lb; Rc = 4 pi A/P^2; Kc = 0,2821 P/sqrt(A); Dd = jumlah L / A; Fs = N/A; "
      "Rb = Nu/Nu+1; Rr = H/Lb; Rn = H Dd; HI = (z_rata2 - z_min)/(z_maks - z_min); "
      "tc Kirpich = 0,01947 L^0,77 S^-0,385 (menit, L m); tc Giandotti = (4 sqrt(A) + 1,5 L)/(0,8 sqrt(H)) (jam).",
      "Perlu sub-DAS atau DAS titik terhitung. Nilai tc rumus empiris: gunakan sebagai pembanding, bukan satu-satunya dasar."))

# ----------------------------------------------------------------------------- 6. Indeks hidro-topografi
SCA_CH = [("mfd", "MFD (Quinn)"), ("dinf", "D-Infinity"), ("d8", "D8")]
add(A("twi", G_IDX, "Topographic Wetness Index (TWI)",
      "Indeks kecenderungan sel menjadi jenuh air: makin tinggi makin banyak air terkumpul dan makin landai.",
      [("twi", "Topographic Wetness Index", "raster")],
      ["beven1979", "moore1991", "sorensen2006"],
      "TWI = ln(a / tan b); a = luas tangkapan spesifik (m2/m), b = kemiringan lokal.",
      "Dihitung dari topografi saja: tidak memuat tanah, hujan, atau drainase buatan.",
      [P("sca_source", "Sumber luas tangkapan spesifik", "choice", "mfd", choices=SCA_CH),
       P("tan_min", "Batas bawah tan b", "float", 0.001, 0.0001, 0.05, 0.0005, "", "Mencegah pembagian nol di area datar.")]))
add(A("spi", G_IDX, "Stream Power Index (SPI)",
      "Daya erosif aliran permukaan: tinggi di alur curam dengan luas tangkapan besar.",
      [("spi", "Stream Power Index", "raster")], ["moore1991"],
      "SPI = a x tan b.", "Indikator relatif, bukan daya aliran sebenarnya.",
      [P("sca_source", "Sumber luas tangkapan spesifik", "choice", "mfd", choices=SCA_CH)]))
add(A("sti", G_IDX, "Sediment Transport Index (STI)",
      "Kapasitas pengangkutan sedimen relatif (padanan faktor LS untuk lanskap kompleks).",
      [("sti", "Sediment Transport Index", "raster")], ["moore1986", "moore1991"],
      "STI = (a / 22,13)^0,6 (sin b / 0,0896)^1,3.", "Bernilai 1 pada lereng baku USLE (9 %, 22,13 m).",
      [P("sca_source", "Sumber luas tangkapan spesifik", "choice", "mfd", choices=SCA_CH)]))
add(A("ls", G_IDX, "LS Factor (RUSLE)",
      "Faktor panjang-kemiringan lereng untuk pendugaan erosi tanah RUSLE, dihitung per sel.",
      [("ls_factor", "LS Factor", "raster")],
      ["desmet1996", "mccool1987", "mccool1989", "nearing1997", "renard1997"],
      "L = [(A_in + D^2)^(m+1) - A_in^(m+1)] / [D^(m+2) x^m 22,13^m]; m = beta/(1+beta); S McCool et al. (1987) atau Nearing (1997).",
      "Hanya satu faktor RUSLE; bukan tingkat erosi. Pada lereng sangat curam (> 50 %) hasil kurang terverifikasi.",
      [P("s_method", "Faktor kemiringan S", "choice", "mccool", choices=[("mccool", "McCool et al. (1987)"), ("nearing", "Nearing (1997)")]),
       P("ls_max", "Batas atas LS (0 = tanpa batas)", "float", 0.0, 0, 500, 5, ""),
       P("breaks", "Batas kelas LS", "floatlist", "1,5,10,20", help="Kelas bersifat indikatif.")]))
add(A("hand", G_IDX, "Height Above Nearest Drainage (HAND)",
      "Tinggi tiap sel di atas sel sungai tempat jalur alirannya bermuara; jarak aliran dan jarak lurus ke sungai.",
      [("hand", "HAND", "raster"), ("flow_dist_stream", "Flow Distance to Stream", "raster"),
       ("euclid_dist_stream", "Euclidean Distance to Stream", "raster")],
      ["renno2008", "nobre2011"],
      "HAND = z(sel) - z(sel sungai tujuan di sepanjang jalur D8).",
      "Bergantung ambang sungai; di dataran sangat datar jalur alirannya tidak stabil."))
add(A("drainage_density", G_IDX, "Drainage Density (Kernel)",
      "Kerapatan sungai (km/km2) dalam lingkaran di sekitar tiap sel.",
      [("drainage_density", "Drainage Density", "raster")], ["horton1932"],
      "Dd = panjang sungai dalam lingkaran / luas lingkaran.",
      "Bergantung ambang ekstraksi sungai.",
      [P("radius_m", "Jari-jari kernel", "float", 1000.0, 100, 20000, 100, "m")]))
add(A("travel_time", G_IDX, "Time of Concentration (Isochrone)",
      "Waktu tempuh air dari tiap sel ke titik keluar (peta isochrone) dan fungsi luas-waktu (time-area).",
      [("travel_time", "Travel Time (Isochrone)", "raster")],
      ["maidment1993", "nrcs1986", "manning1891"],
      "t = jumlah(panjang langkah / V). Lereng: V = k sqrt(S) (TR-55); sungai: V = R^(2/3) S^(1/2) / n (Manning).",
      "Kecepatan memakai asumsi tetap (k, n, R); nilai absolut bersifat indikatif, pola relatif lebih andal.",
      [P("k_hill", "Koefisien k lereng", "float", 4.9178, 0.5, 10, 0.1, "m/s",
         "TR-55: 4,92 tanah terbuka/ladang, 6,20 berperkerasan."),
       P("manning_n", "Manning n sungai", "float", 0.035, 0.01, 0.2, 0.005),
       P("hyd_radius", "Jari-jari hidrolik sungai R", "float", 0.5, 0.05, 10, 0.05, "m"),
       P("s_min", "Kemiringan minimum", "float", 0.001, 0.0001, 0.05, 0.0005, "m/m"),
       P("bin_min", "Lebar kelas waktu", "float", 10.0, 1, 600, 1, "menit")]))

# ----------------------------------------------------------------------------- 7. Genangan dan banjir
add(A("hand_flood", G_FLD, "HAND Flood Inundation Scenario",
      "Zona genangan berdasarkan beberapa skenario tinggi muka air di atas dasar sungai, dari HAND. Tiap sel diberi "
      "tinggi muka air terendah yang menggenanginya; luas, rata-rata kedalaman, dan volume per skenario masuk tabel.",
      [("hand_flood", "HAND Flood Inundation Zones", "raster")],
      ["nobre2011", "nobre2016"],
      "Genangan bila HAND <= tinggi muka air; kedalaman = muka air - HAND.",
      "Bukan model hidrolika: tidak memuat debit, hujan, atau bangunan air. Gunakan untuk penapisan awal.",
      [P("stages", "Tinggi muka air (pisahkan koma)", "floatlist", "1,2,5,10", help="Meter di atas dasar sungai.")]))
add(A("bathtub", G_FLD, "Bathtub Inundation (Sea Level / Low-lying)",
      "Genangan wilayah rendah pada ketinggian muka air tertentu, hanya yang terhubung ke tepi DEM (laut/muara).",
      [("bathtub", "Bathtub Inundation Depth", "raster")], ["poulter2008"],
      "Genangan = sel dengan z <= level yang terhubung 8-arah ke tepi domain; kedalaman = level - z.",
      "Tidak memodelkan dinamika air; DEM harus memuat tepi laut/muara pada tepinya.",
      [P("level", "Muka air terhadap datum DEM", "float", 1.0, -10, 100, 0.1, "m"),
       P("connected", "Hanya sel yang terhubung ke tepi DEM", "bool", True)]))

# ----------------------------------------------------------------------------- 8. Komposit
FLOOD_F = [("hand", "HAND (rendah = rawan)"), ("slope", "Kemiringan (landai = rawan)"),
           ("twi", "TWI (tinggi = rawan)"), ("acc", "Luas tangkapan (besar = rawan)"),
           ("dist", "Jarak aliran ke sungai (dekat = rawan)")]
add(A("flood_index", G_CMP, "Topographic Flood Susceptibility Index",
      "Skor kerawanan banjir dari gabungan HAND, kemiringan, TWI, luas tangkapan, dan jarak ke sungai.",
      [("flood_index", "Flood Susceptibility Index", "raster")],
      ["samela2017", "manfreda2011", "nobre2011"],
      "Skor = jumlah(w_i x n_i) / jumlah(w_i); n_i adalah faktor ternormalisasi 0-1 (persentil 2-98).",
      "Indeks relatif berbasis topografi. Bobot bawaan sama (netral); ubah sesuai kajian lokal/AHP dan validasi dengan "
      "riwayat banjir.",
      [P("w_" + k, "Bobot " + lb, "float", 1.0, 0, 10, 0.5) for k, lb in FLOOD_F] +
      [P("breaks", "Batas kelas indeks", "floatlist", "0.2,0.4,0.6,0.8")]))
REC_F = [("slope", "Kemiringan (landai = baik)"), ("twi", "TWI (tinggi = baik)"),
         ("dd", "Kerapatan drainase (rendah = baik)"), ("tri", "TRI (halus = baik)")]
add(A("recharge_index", G_CMP, "Topographic Recharge (Infiltration) Potential Index",
      "Skor potensi resapan dari sisi topografi: lereng landai, area penampung air, drainase jarang, permukaan halus.",
      [("recharge_index", "Recharge Potential Index", "raster")],
      ["magesh2012", "rahmati2015"],
      "Skor = jumlah(w_i x n_i) / jumlah(w_i).",
      "Tidak memuat tanah, geologi, atau tutupan lahan: lengkapi dengan lapisan tersebut sebelum dipakai untuk penetapan kawasan resapan.",
      [P("w_" + k, "Bobot " + lb, "float", 1.0, 0, 10, 0.5) for k, lb in REC_F] +
      [P("breaks", "Batas kelas indeks", "floatlist", "0.2,0.4,0.6,0.8")]))
ERO_F = [("ls", "Faktor LS (tinggi = rawan)"), ("spi", "SPI (tinggi = rawan)"), ("slope", "Kemiringan (curam = rawan)")]
add(A("erosion_index", G_CMP, "Topographic Erosion Susceptibility Index",
      "Skor kerawanan erosi dari sisi topografi: faktor LS, SPI, dan kemiringan.",
      [("erosion_index", "Erosion Susceptibility Index", "raster")],
      ["desmet1996", "moore1991", "renard1997"],
      "Skor = jumlah(w_i x n_i) / jumlah(w_i).",
      "Bukan pendugaan kehilangan tanah (tanpa R, K, C, P).",
      [P("w_" + k, "Bobot " + lb, "float", 1.0, 0, 10, 0.5) for k, lb in ERO_F] +
      [P("breaks", "Batas kelas indeks", "floatlist", "0.2,0.4,0.6,0.8")]))


def defaults():
    d = {"core": {p["key"]: p["default"] for p in CORE_PARAMS}}
    for k, a in ANALYSES.items():
        d[k] = {p["key"]: p["default"] for p in a["params"]}
    return d


def refs_for(keys):
    return [(k, REFS[k]) for k in keys if k in REFS]


# Prasyarat (hanya untuk tampilan; pipeline menghitungnya otomatis bila belum dipilih)
DEPENDS = {
    "depressions": [], "slope": [], "aspect": [], "hillshade": [], "curvature": [], "tpi": [], "tri": [],
    "landform": ["slope"], "flow_dir_d8": ["fill"], "flow_acc_d8": ["fill", "flow_dir_d8"],
    "flow_dinf": ["fill"], "flow_mfd": ["fill"], "flow_length": ["fill", "flow_dir_d8"],
    "stream_network": ["fill", "flow_acc_d8"], "subbasins": ["stream_network"],
    "watershed_points": ["fill", "flow_acc_d8"],
    "basin_morphometry": ["stream_network", "subbasins", "slope", "flow_length"],
    "twi": ["slope", "flow_mfd"], "spi": ["slope", "flow_mfd"], "sti": ["slope", "flow_mfd"],
    "ls": ["slope", "flow_acc_d8"], "hand": ["stream_network"], "drainage_density": ["stream_network"],
    "travel_time": ["stream_network", "slope"], "hand_flood": ["hand"], "bathtub": [],
    "flood_index": ["hand", "slope", "twi", "flow_acc_d8"],
    "recharge_index": ["slope", "twi", "drainage_density", "tri"],
    "erosion_index": ["ls", "spi", "slope"],
}

PRESETS = OrderedDict([
    ("Paket DAS dan sungai", ["fill", "flow_dir_d8", "flow_acc_d8", "flow_length", "stream_network", "subbasins",
                               "watershed_points", "basin_morphometry", "drainage_density", "travel_time"]),
    ("Paket banjir", ["fill", "slope", "flow_acc_d8", "stream_network", "hand", "twi", "travel_time", "hand_flood",
                      "bathtub", "flood_index"]),
    ("Paket erosi", ["fill", "slope", "flow_acc_d8", "ls", "spi", "sti", "erosion_index"]),
    ("Paket resapan", ["fill", "slope", "tri", "twi", "drainage_density", "recharge_index"]),
    ("Paket morfologi permukaan", ["slope", "aspect", "hillshade", "curvature", "tpi", "tri", "landform"]),
])


DEFAULT_PRESET = "Paket DAS dan sungai"
_LC = {}


def L():
    """Registry with every user-visible text translated into the active language (cached)."""
    key = (i18n.language(), i18n.VERSION, i18n.RECORD)
    if key not in _LC or i18n.RECORD:
        _LC.clear()
        _LC[key] = dict(
            ANALYSES=OrderedDict((k, i18n.localize(a)) for k, a in ANALYSES.items()),
            GROUPS=[i18n.tr(g) for g in GROUPS],
            CORE_PARAMS=i18n.localize(CORE_PARAMS),
            PRESETS=OrderedDict((i18n.tr(k), v) for k, v in PRESETS.items()),
            DEFAULT_PRESET=i18n.tr(DEFAULT_PRESET),
        )
    return _LC[key]
