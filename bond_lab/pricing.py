"""Tahvil fiyatlama fonksiyonları.

İçerik:
    * :func:`kirli_fiyat` / :func:`temiz_fiyat` — verilen YTM'den fiyat
      (işlemiş faiz dahil kirli fiyat ve işlemiş faiz hariç temiz fiyat).
    * :func:`ytm_bul` — fiyattan vadeye kadar getiri (YTM) çözümü;
      Newton-Raphson, başarısız olursa garantili bisection yedeği.
    * :func:`spot_egriden_fiyat` — spot (sıfır kuponlu) getiri eğrisinden fiyat.
    * :func:`cari_getiri` — cari getiri (yıllık kupon / temiz fiyat).

İskonto kuralı: yıllık YTM ``y`` ve frekans ``f`` için her (t, CF) akışı
``CF / (1 + y/f)^(f·t)`` ile bugüne indirgenir (dönemsel getiri = y/f,
dönem sayısı = f·t; kesirli dönem üsleri desteklenir).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from bond_lab.bond import Tahvil

if TYPE_CHECKING:  # yalnızca tip denetimi için; döngüsel import önlenir
    from bond_lab.yield_curve import GetiriEgrisi


def kirli_fiyat(tahvil: Tahvil, ytm: float) -> float:
    """Verilen yıllık YTM için kirli (brüt, işlemiş faiz dahil) fiyat.

    Args:
        tahvil: Fiyatlanacak tahvil.
        ytm: Yıllık vadeye kadar getiri (ondalık, 0.12 = %12).

    Returns:
        Kirli fiyat (nominal ile aynı birimde).

    Raises:
        ValueError: 1 + ytm/frekans <= 0 ise (iskonto tanımsız).
    """
    f = tahvil.frekans
    donemsel = ytm / f
    if donemsel <= -1.0:
        raise ValueError("Geçersiz getiri: 1 + ytm/frekans pozitif olmalıdır.")
    return sum(cf * (1.0 + donemsel) ** (-(f * t)) for t, cf in tahvil.nakit_akislari())


def temiz_fiyat(tahvil: Tahvil, ytm: float) -> float:
    """Verilen yıllık YTM için temiz fiyat = kirli fiyat − işlemiş faiz."""
    return kirli_fiyat(tahvil, ytm) - tahvil.islemis_faiz()


def cari_getiri(tahvil: Tahvil, fiyat_temiz: float) -> float:
    """Cari getiri = yıllık kupon tutarı / temiz fiyat.

    Sıfır kuponlu tahvilde 0 döner.

    Raises:
        ValueError: Temiz fiyat pozitif değilse.
    """
    if fiyat_temiz <= 0:
        raise ValueError("Temiz fiyat pozitif olmalıdır.")
    return tahvil.nominal * tahvil.kupon_orani / fiyat_temiz


def spot_egriden_fiyat(tahvil: Tahvil, egri: GetiriEgrisi) -> float:
    """Spot getiri eğrisinden kirli fiyat.

    Her nakit akışı kendi vadesine karşılık gelen spot oranla (eğrinin
    iskonto faktörüyle) bugüne indirgenir:
    ``P = Σ CF(t) · DF(t)``, ``DF(t) = (1 + z(t))^(-t)``.
    """
    return sum(cf * egri.iskonto_faktoru(t) for t, cf in tahvil.nakit_akislari())


def ytm_bul(
    tahvil: Tahvil,
    fiyat: float,
    temiz: bool = True,
    tahmin: float = 0.05,
    tol: float = 1e-10,
    maks_iter: int = 100,
) -> float:
    """Verilen fiyattan yıllık YTM'yi çözer.

    Önce Newton-Raphson denenir (analitik türevle); yakınsamaz veya tanım
    bölgesinden çıkarsa garantili bisection (ikiye bölme) yöntemine düşülür.
    Fiyat, getirinin kesin azalan fonksiyonu olduğundan kök tektir.

    Args:
        tahvil: Tahvil.
        fiyat: Gözlenen fiyat.
        temiz: True ise ``fiyat`` temiz fiyat kabul edilir ve işlemiş faiz
            eklenerek kirli fiyata çevrilir; False ise kirli fiyattır.
        tahmin: Newton-Raphson başlangıç değeri.
        tol: Fiyat farkı toleransı.
        maks_iter: Newton-Raphson iterasyon sınırı.

    Returns:
        Yıllık YTM (ondalık).

    Raises:
        ValueError: Fiyat pozitif değilse veya kök makul aralıkta bulunamazsa.
    """
    hedef_kirli = fiyat + (tahvil.islemis_faiz() if temiz else 0.0)
    if hedef_kirli <= 0:
        raise ValueError("Fiyat pozitif olmalıdır.")

    akislar = tahvil.nakit_akislari()
    f = tahvil.frekans
    alt_sinir = -f * (1.0 - 1e-9)  # 1 + y/f > 0 koşulu

    def fark(y: float) -> float:
        return kirli_fiyat(tahvil, y) - hedef_kirli

    def turev(y: float) -> float:
        d = y / f
        return sum(-t * cf * (1.0 + d) ** (-(f * t) - 1.0) for t, cf in akislar)

    # --- 1) Newton-Raphson ---
    y = max(tahmin, alt_sinir + 0.01)
    for _ in range(maks_iter):
        hata = fark(y)
        if abs(hata) < tol:
            return y
        d = turev(y)
        if d == 0.0 or not math.isfinite(d):
            break
        y_yeni = y - hata / d
        if not math.isfinite(y_yeni) or y_yeni <= alt_sinir or y_yeni > 1000.0:
            break
        y = y_yeni
    if abs(fark(y)) < tol:
        return y

    # --- 2) Bisection (garantili yedek) ---
    a = alt_sinir + 1e-6  # fiyat burada çok büyüktür -> fark(a) > 0
    b = 1.0
    while fark(b) > 0.0 and b < 512.0:
        b *= 2.0
    if fark(b) > 0.0:
        raise ValueError("YTM makul aralıkta (%-100 ile %51200) bulunamadı.")
    for _ in range(300):
        orta = 0.5 * (a + b)
        h = fark(orta)
        if abs(h) < tol or (b - a) < 1e-14:
            return orta
        if h > 0.0:
            a = orta
        else:
            b = orta
    return 0.5 * (a + b)
