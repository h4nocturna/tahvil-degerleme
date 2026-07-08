"""Gün sayım (day count) konvansiyonları ve tarih araçları.

Gerçek piyasa uygulamasında işlemiş faiz, yıl kesri ve iskonto süreleri
takvim tarihlerine ve piyasaya özgü gün sayım kurallarına göre hesaplanır.
Bu modül en yaygın dört konvansiyonu uygular:

    * ``ACT/365F``  — gerçek gün / 365 (sabit). TL piyasasında yaygındır.
    * ``ACT/360``   — gerçek gün / 360. Para piyasası (ABD, EUR) kuralı.
    * ``30/360``    — 30/360 US (Bond Basis). ABD şirket/belediye tahvilleri.
    * ``ACT/ACT``   — basitleştirilmiş ISDA: her takvim yılının payı kendi
      gün sayısına (365/366) bölünür. Devlet tahvillerinde yaygındır.

Ayrıca takas (valör) tarihi kaydırma (T+1/T+2, hafta sonu atlama) ve
tarih bazlı işlemiş faiz hesabı içerir. Tüm fonksiyonlar
:class:`datetime.date` ile çalışır.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

#: Desteklenen gün sayım konvansiyonu adları.
GECERLI_KONVANSIYONLAR = ("ACT/365F", "ACT/360", "30/360", "ACT/ACT")


# ----------------------------------------------------------------------
# Yıl kesri (year fraction)
# ----------------------------------------------------------------------
def _gun_30_360_us(baslangic: date, bitis: date) -> int:
    """30/360 US (Bond Basis) kuralına göre gün sayısı.

    Kurallar:
        * Başlangıç günü 31 ise 30'a çekilir.
        * Bitiş günü 31 ve başlangıç günü (düzeltme sonrası) 30 ise
          bitiş de 30'a çekilir.
    """
    d1, d2 = baslangic.day, bitis.day
    if d1 == 31:
        d1 = 30
    if d2 == 31 and d1 == 30:
        d2 = 30
    return 360 * (bitis.year - baslangic.year) + 30 * (bitis.month - baslangic.month) + (d2 - d1)


def _yil_kesri_act_act(baslangic: date, bitis: date) -> float:
    """Basitleştirilmiş ACT/ACT (ISDA): yıl bazında parçalayarak toplar.

    Her takvim yılına düşen gerçek gün sayısı, o yılın uzunluğuna
    (artık yılda 366, diğerlerinde 365) bölünür ve paylar toplanır.
    """
    if baslangic.year == bitis.year:
        yil_gun = 366 if calendar.isleap(baslangic.year) else 365
        return (bitis - baslangic).days / yil_gun
    toplam = 0.0
    # İlk yılın kalan kısmı
    ilk_yil_sonu = date(baslangic.year + 1, 1, 1)
    ilk_gun = 366 if calendar.isleap(baslangic.year) else 365
    toplam += (ilk_yil_sonu - baslangic).days / ilk_gun
    # Aradaki tam yıllar
    toplam += float(bitis.year - baslangic.year - 1)
    # Son yılın geçen kısmı
    son_yil_basi = date(bitis.year, 1, 1)
    son_gun = 366 if calendar.isleap(bitis.year) else 365
    toplam += (bitis - son_yil_basi).days / son_gun
    return toplam


def yil_kesri(baslangic: date, bitis: date, konvansiyon: str = "ACT/365F") -> float:
    """İki tarih arasındaki yıl kesrini verilen konvansiyona göre hesaplar.

    Args:
        baslangic: Dönem başlangıç tarihi.
        bitis: Dönem bitiş tarihi (``baslangic``'tan önce olamaz).
        konvansiyon: ``"ACT/365F"``, ``"ACT/360"``, ``"30/360"`` veya
            ``"ACT/ACT"``.

    Returns:
        Yıl kesri (ondalık; örn. 6 ay ≈ 0.5).

    Raises:
        ValueError: Konvansiyon tanınmıyorsa veya bitis < baslangic ise.
    """
    if bitis < baslangic:
        raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
    k = konvansiyon.strip().upper()
    if k not in GECERLI_KONVANSIYONLAR:
        raise ValueError(f"Konvansiyon {GECERLI_KONVANSIYONLAR} içinden olmalıdır.")
    if k == "ACT/365F":
        return (bitis - baslangic).days / 365.0
    if k == "ACT/360":
        return (bitis - baslangic).days / 360.0
    if k == "30/360":
        return _gun_30_360_us(baslangic, bitis) / 360.0
    return _yil_kesri_act_act(baslangic, bitis)


# ----------------------------------------------------------------------
# Takas / valör tarihi
# ----------------------------------------------------------------------
def is_gunu_mu(tarih: date) -> bool:
    """Tarih hafta içi mi? (Basitleştirme: resmî tatiller hariç tutulmaz.)"""
    return tarih.weekday() < 5  # 0=Pzt ... 4=Cum


def sonraki_is_gunu(tarih: date) -> date:
    """Tarihi, hafta sonuna denk geliyorsa ileriye, ilk iş gününe taşır."""
    while not is_gunu_mu(tarih):
        tarih += timedelta(days=1)
    return tarih


def valor_tarihi(islem_tarihi: date, takas_gunu: int = 2) -> date:
    """İşlem tarihinden takas (valör) tarihini hesaplar (T+1, T+2 ...).

    Hafta sonları iş günü sayılmaz: her adımda bir sonraki iş gününe
    ilerlenir. Örn. Cuma günü T+2 işlem → valör Salı.

    Args:
        islem_tarihi: İşlemin yapıldığı tarih.
        takas_gunu: Kaç iş günü sonra takas (0 = aynı gün, 1 = T+1, ...).

    Returns:
        Valör (takas) tarihi.

    Raises:
        ValueError: takas_gunu negatifse.
    """
    if takas_gunu < 0:
        raise ValueError("Takas günü negatif olamaz.")
    tarih = sonraki_is_gunu(islem_tarihi)
    for _ in range(takas_gunu):
        tarih = sonraki_is_gunu(tarih + timedelta(days=1))
    return tarih


# ----------------------------------------------------------------------
# Kupon takvimi ve tarih bazlı işlemiş faiz
# ----------------------------------------------------------------------
def _ay_geri_al(tarih: date, ay: int) -> date:
    """Tarihi `ay` ay geriye taşır; gün ay sonunu aşarsa kırpar."""
    toplam_ay = tarih.year * 12 + (tarih.month - 1) - ay
    yil, ay_indeks = divmod(toplam_ay, 12)
    yeni_ay = ay_indeks + 1
    son_gun = calendar.monthrange(yil, yeni_ay)[1]
    return date(yil, yeni_ay, min(tarih.day, son_gun))


def kupon_tarihleri(vade_tarihi: date, frekans: int, valor: date) -> list[date]:
    """Vadeden geriye giderek valörden SONRAKİ kupon tarihlerini üretir.

    Kupon takvimi vade tarihinden geriye ``12/frekans`` aylık adımlarla
    kurulur (piyasa uygulamasındaki 'geriye doğru takvim' kuralı).

    Args:
        vade_tarihi: İtfa tarihi (son kupon + anapara).
        frekans: Yılda kupon sayısı (1, 2, 4, 12).
        valor: Valör tarihi; bu tarihten sonraki kuponlar listelenir.

    Returns:
        Artan sıralı kupon tarihleri listesi (vade dahil).

    Raises:
        ValueError: Vade valörden önceyse veya frekans geçersizse.
    """
    if frekans not in (1, 2, 4, 12):
        raise ValueError("Frekans 1, 2, 4 veya 12 olmalıdır.")
    if vade_tarihi <= valor:
        raise ValueError("Vade tarihi valörden sonra olmalıdır.")
    adim_ay = 12 // frekans
    tarihler: list[date] = []
    t = vade_tarihi
    while t > valor:
        tarihler.append(t)
        t = _ay_geri_al(t, adim_ay)
    return sorted(tarihler)


def onceki_ve_sonraki_kupon(vade_tarihi: date, frekans: int, valor: date) -> tuple[date, date]:
    """Valör tarihini çevreleyen (önceki kupon, sonraki kupon) çiftini verir.

    Önceki kupon tarihi ihraç öncesine de düşebilir; işlemiş faiz hesabı
    için dönem başlangıcı olarak kullanılır.
    """
    sonrakiler = kupon_tarihleri(vade_tarihi, frekans, valor)
    sonraki = sonrakiler[0]
    onceki = _ay_geri_al(sonraki, 12 // frekans)
    return onceki, sonraki


def islemis_faiz_tarihli(
    nominal: float,
    kupon_orani: float,
    frekans: int,
    vade_tarihi: date,
    valor: date,
    konvansiyon: str = "ACT/ACT",
) -> float:
    """Gerçek takvim tarihleriyle işlemiş (birikmiş) faiz hesaplar.

    Formül: ``kupon_tutarı × yıl_kesri(önceki_kupon, valör) /
    yıl_kesri(önceki_kupon, sonraki_kupon)`` — pay ve payda aynı
    konvansiyonla ölçülür (piyasadaki 'dönem oranı' kuralı).

    Args:
        nominal: Nominal değer.
        kupon_orani: Yıllık kupon oranı (ondalık).
        frekans: Yılda kupon sayısı.
        vade_tarihi: İtfa tarihi.
        valor: Valör (takas) tarihi.
        konvansiyon: Gün sayım konvansiyonu.

    Returns:
        İşlemiş faiz tutarı (nominal ile aynı birimde).
    """
    if kupon_orani == 0.0:
        return 0.0
    onceki, sonraki = onceki_ve_sonraki_kupon(vade_tarihi, frekans, valor)
    gecen = yil_kesri(onceki, valor, konvansiyon)
    donem = yil_kesri(onceki, sonraki, konvansiyon)
    if donem <= 0:
        return 0.0
    kupon_tutari = nominal * kupon_orani / frekans
    return kupon_tutari * min(max(gecen / donem, 0.0), 1.0)
