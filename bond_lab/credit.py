"""Kredi riski katmanı: rating spread'leri, spread'li fiyatlama, Z-spread.

Şirket tahvilleri, aynı vadedeki devlet tahvilinden (risksiz eğriden)
daha yüksek getiriyle işlem görür; aradaki fark **kredi spread'i**dir.
Bu modül üç aracı sunar:

    * :data:`RATING_SPREAD_BP` — kredi notu → temsili spread (baz puan)
      tablosu (yatırım yapılabilir AAA...BBB ve spekülatif BB/B).
    * :func:`spreadli_fiyat` — risksiz spot eğri + sabit spread ile
      şirket tahvili fiyatlama.
    * :func:`z_spread_bul` — gözlenen fiyattan Z-spread çözümü (spot
      eğrinin her noktasına eklenen sabit spread'i sayısal kök bulmayla
      çıkarır).

Spread'ler temsilidir (uzun dönem ABD şirket tahvili ortalamalarına
yakın seviyeler); gerçek işlem için güncel piyasa verisi kullanılmalıdır.
"""

from __future__ import annotations

from scipy.optimize import brentq

from bond_lab.bond import Tahvil
from bond_lab.yield_curve import GetiriEgrisi

#: Kredi notu → temsili spread (baz puan). Kaynak: uzun dönem ortalama
#: seviyelerden esinlenen TEMSİLİ değerler (gerçek kotasyon değildir).
RATING_SPREAD_BP: dict[str, float] = {
    "AAA": 45.0,
    "AA": 65.0,
    "A": 95.0,
    "BBB": 150.0,
    "BB": 300.0,
    "B": 500.0,
}


def rating_spreadi(rating: str) -> float:
    """Kredi notuna karşılık temsili spread'i ONDALIK olarak döndürür.

    Args:
        rating: ``"AAA"``, ``"AA"``, ``"A"``, ``"BBB"``, ``"BB"`` veya
            ``"B"`` (büyük/küçük harf duyarsız).

    Returns:
        Spread, ondalık (örn. BBB için 0.0150).

    Raises:
        ValueError: Rating tabloda yoksa.
    """
    anahtar = rating.strip().upper()
    if anahtar not in RATING_SPREAD_BP:
        raise ValueError(f"Bilinmeyen rating '{rating}'. Geçerli: {sorted(RATING_SPREAD_BP)}")
    return RATING_SPREAD_BP[anahtar] / 10000.0


def spreadli_fiyat(tahvil: Tahvil, egri: GetiriEgrisi, spread: float) -> float:
    """Risksiz spot eğri + sabit spread ile kirli fiyat.

    Her nakit akışı ``(1 + z(t) + s)^(-t)`` faktörüyle iskonto edilir;
    ``s`` tüm vadelere aynı eklenen (Z-spread tanımıyla uyumlu) spread'dir.

    Args:
        tahvil: Fiyatlanacak tahvil.
        egri: Risksiz spot getiri eğrisi.
        spread: Sabit spread, ondalık (0.015 = 150bp).

    Returns:
        Kirli fiyat.

    Raises:
        ValueError: Herhangi bir vadede 1 + z + s <= 0 olursa.
    """
    fiyat = 0.0
    for t, cf in tahvil.nakit_akislari():
        taban = 1.0 + egri.spot_oran(t) + spread
        if taban <= 0.0:
            raise ValueError("1 + spot + spread pozitif olmalıdır.")
        fiyat += cf * taban ** (-t)
    return fiyat


def rating_ile_fiyat(tahvil: Tahvil, egri: GetiriEgrisi, rating: str) -> float:
    """Kredi notuna karşılık gelen temsili spread ile kirli fiyat."""
    return spreadli_fiyat(tahvil, egri, rating_spreadi(rating))


def z_spread_bul(
    tahvil: Tahvil,
    egri: GetiriEgrisi,
    fiyat: float,
    temiz: bool = True,
    tol: float = 1e-12,
) -> float:
    """Gözlenen fiyattan Z-spread'i çözer.

    Z-spread, spot eğrinin HER noktasına eklendiğinde tahvilin bugünkü
    değerini piyasa fiyatına eşitleyen sabit spread'dir. Fiyat spread'in
    kesin azalan fonksiyonu olduğundan kök tektir; ``brentq`` ile
    (-%90, +%500) aralığında aranır.

    Args:
        tahvil: Tahvil.
        egri: Risksiz spot eğri.
        fiyat: Gözlenen fiyat.
        temiz: True ise fiyat temiz kabul edilip işlemiş faiz eklenir.
        tol: Kök bulma toleransı.

    Returns:
        Z-spread, ondalık (negatif olabilir: eğrinin altında fiyatlama).

    Raises:
        ValueError: Fiyat pozitif değilse veya kök aralıkta bulunamazsa.
    """
    hedef = fiyat + (tahvil.islemis_faiz() if temiz else 0.0)
    if hedef <= 0:
        raise ValueError("Fiyat pozitif olmalıdır.")

    def fark(s: float) -> float:
        return spreadli_fiyat(tahvil, egri, s) - hedef

    alt, ust = -0.90, 5.0
    # brentq işaret değişimi ister; uçlarda aynı işaretse fiyat aralık dışıdır.
    if fark(alt) * fark(ust) > 0:
        raise ValueError("Z-spread (-%90, +%500) aralığında bulunamadı; fiyat eğriyle tutarsız.")
    return float(brentq(fark, alt, ust, xtol=tol, maxiter=200))


def spread_duyarliligi(tahvil: Tahvil, egri: GetiriEgrisi, spread: float, bp: float = 1.0) -> float:
    """Spread DV01'i: spread'in ``bp`` baz puan artmasının fiyat etkisi.

    Merkezi fark ile hesaplanır; işaret negatiftir (spread artışı fiyatı
    düşürür), mutlak değer döndürülür.
    """
    h = bp / 10000.0
    yukari = spreadli_fiyat(tahvil, egri, spread + h)
    asagi = spreadli_fiyat(tahvil, egri, spread - h)
    return abs(yukari - asagi) / 2.0
