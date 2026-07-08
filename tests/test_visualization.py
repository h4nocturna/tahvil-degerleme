"""Görselleştirme duman testleri: PNG dosyaları gerçekten üretiliyor mu?"""

from pathlib import Path

from bond_lab.bond import Tahvil
from bond_lab.strategies import bullet_portfoy, merdiven_portfoy, senaryo_analizi
from bond_lab.visualization import (
    fiyat_getiri_grafigi,
    getiri_egrisi_grafigi,
    nakit_akisi_grafigi,
    strateji_karsilastirma_grafigi,
)
from bond_lab.yield_curve import GetiriEgrisi


def test_tum_grafikler_png_uretir(tmp_path: Path):
    """Dört grafik fonksiyonu da boş olmayan PNG dosyası kaydetmeli."""
    egri = GetiriEgrisi([1, 2, 5, 10], [0.30, 0.28, 0.25, 0.23])
    merdiven = merdiven_portfoy(100_000, [1, 2, 5, 10], egri)
    bullet = bullet_portfoy(100_000, 5, egri)
    sonuclar = {
        "Merdiven": senaryo_analizi(merdiven),
        "Bullet": senaryo_analizi(bullet),
    }
    dosyalar = [
        fiyat_getiri_grafigi([Tahvil(100, 0.10, 5, 1, "5Y")], cikti_klasoru=tmp_path),
        getiri_egrisi_grafigi(egri, cikti_klasoru=tmp_path),
        strateji_karsilastirma_grafigi(sonuclar, cikti_klasoru=tmp_path),
        nakit_akisi_grafigi([merdiven, bullet], cikti_klasoru=tmp_path),
    ]
    for yol in dosyalar:
        assert yol.exists()
        assert yol.suffix == ".png"
        assert yol.stat().st_size > 1000  # boş dosya değil
