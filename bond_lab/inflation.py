"""Enflasyona endeksli tahvil değerlemesi (TÜFE endeksli DİBS benzeri).

Enflasyona endeksli tahvillerde anapara, ihraçtan itibaren gerçekleşen
TÜFE artışıyla (endeks oranı) düzeltilir; kupon da düzeltilmiş anapara
üzerinden ödenir. Bu modül:

    * :func:`endeks_orani` — referans/baz TÜFE'den endeks oranı.
    * :class:`EndeksliTahvil` — reel şartlarla tanımlanan tahvil;
      düzeltilmiş nakit akışları ve nominal değerleme.
    * Fisher denklemi: :func:`fisher_nominal`, :func:`fisher_reel` —
      reel getiri ↔ nominal getiri dönüşümü (tam ve yaklaşık biçim).
    * :func:`basit_degerleme` — reel getiri + beklenen enflasyonla
      nominal fiyat (endeks oranını da hesaba katan basit değerleme).

Basitleştirmeler: gerçek TÜFE serisi yerine "gerçekleşen endeks oranı"
tek katsayı olarak verilir; gecikme (indexation lag) ihmal edilir; taban
(deflasyon) koruması opsiyoneldir.
"""

from __future__ import annotations

from dataclasses import dataclass

from bond_lab.bond import NakitAkisi, Tahvil
from bond_lab.pricing import kirli_fiyat


# ----------------------------------------------------------------------
# Fisher denklemi
# ----------------------------------------------------------------------
def fisher_nominal(reel: float, enflasyon: float, tam: bool = True) -> float:
    """Reel getiri ve beklenen enflasyondan nominal getiri (Fisher).

    Tam biçim: ``(1+n) = (1+r)(1+π)``; yaklaşık biçim: ``n ≈ r + π``.

    Args:
        reel: Reel getiri (ondalık).
        enflasyon: Beklenen enflasyon (ondalık).
        tam: True ise tam çarpımsal biçim, False ise toplamsal yaklaşım.
    """
    if tam:
        return (1.0 + reel) * (1.0 + enflasyon) - 1.0
    return reel + enflasyon


def fisher_reel(nominal: float, enflasyon: float, tam: bool = True) -> float:
    """Nominal getiri ve enflasyondan reel getiri (Fisher'in tersi).

    Tam biçim: ``r = (1+n)/(1+π) − 1``; yaklaşık biçim: ``r ≈ n − π``.

    Raises:
        ValueError: Tam biçimde 1 + enflasyon <= 0 ise.
    """
    if tam:
        if 1.0 + enflasyon <= 0:
            raise ValueError("1 + enflasyon pozitif olmalıdır.")
        return (1.0 + nominal) / (1.0 + enflasyon) - 1.0
    return nominal - enflasyon


def endeks_orani(guncel_tufe: float, baz_tufe: float) -> float:
    """Endeks oranı = güncel TÜFE / ihraçtaki (baz) TÜFE.

    Raises:
        ValueError: TÜFE değerlerinden biri pozitif değilse.
    """
    if guncel_tufe <= 0 or baz_tufe <= 0:
        raise ValueError("TÜFE endeks değerleri pozitif olmalıdır.")
    return guncel_tufe / baz_tufe


# ----------------------------------------------------------------------
# Endeksli tahvil
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class EndeksliTahvil:
    """TÜFE'ye endeksli tahvil (reel şartlarla tanımlanır).

    Attributes:
        reel_nominal: İhraçtaki (endekslenmemiş) nominal değer.
        reel_kupon_orani: REEL yıllık kupon oranı (ondalık; endeksli
            DİBS'lerde tipik olarak düşüktür, örn. %2-4).
        vade_yil: Vadeye kalan süre (yıl).
        frekans: Yılda kupon sayısı.
        endeks_orani: Bugüne kadar GERÇEKLEŞEN endeks oranı
            (güncel TÜFE / baz TÜFE); 1.0 = ihraç günü.
        taban_koruma: True ise vadede anapara, endeks 1'in altına düşse
            bile reel nominalin altında ödenmez (deflasyon tabanı).
        isim: Opsiyonel etiket.
    """

    reel_nominal: float = 100.0
    reel_kupon_orani: float = 0.03
    vade_yil: float = 5.0
    frekans: int = 2
    endeks_orani: float = 1.0
    taban_koruma: bool = True
    isim: str = ""

    def __post_init__(self) -> None:
        if self.reel_nominal <= 0:
            raise ValueError("Reel nominal pozitif olmalıdır.")
        if self.reel_kupon_orani < 0:
            raise ValueError("Reel kupon oranı negatif olamaz.")
        if self.vade_yil <= 0:
            raise ValueError("Vade pozitif olmalıdır.")
        if self.endeks_orani <= 0:
            raise ValueError("Endeks oranı pozitif olmalıdır.")

    @property
    def duzeltilmis_anapara(self) -> float:
        """Bugünkü endekslenmiş anapara = reel nominal × endeks oranı."""
        return self.reel_nominal * self.endeks_orani

    def _reel_tahvil(self) -> Tahvil:
        """Reel şartlarla eşdeğer klasik tahvil (nakit akışı şablonu)."""
        return Tahvil(
            nominal=self.reel_nominal,
            kupon_orani=self.reel_kupon_orani,
            vade_yil=self.vade_yil,
            frekans=self.frekans,
            isim=self.isim or "Endeksli tahvil (reel)",
        )

    def nakit_akislari_nominal(self, beklenen_enflasyon: float) -> list[NakitAkisi]:
        """Beklenen enflasyonla PROJEKTE edilmiş nominal (TL) nakit akışları.

        Her t anındaki akış, reel akışın ``endeks_orani × (1+π)^t`` ile
        büyütülmüş halidir. Taban koruması varsa vadedeki anapara bileşeni
        reel nominalin altına düşürülmez.

        Args:
            beklenen_enflasyon: Yıllık beklenen enflasyon (ondalık).

        Returns:
            (zaman_yil, nominal_tutar) listesi.
        """
        reel = self._reel_tahvil()
        akislar: list[NakitAkisi] = []
        son_t = reel.nakit_akislari()[-1][0]
        for t, cf in reel.nakit_akislari():
            faktor = self.endeks_orani * (1.0 + beklenen_enflasyon) ** t
            tutar = cf * faktor
            if self.taban_koruma and t == son_t:
                # Vade akışı = kupon + anapara; anapara kısmına taban uygula.
                kupon = reel.kupon_tutari * faktor if not reel.sifir_kuponlu else 0.0
                anapara = self.reel_nominal * faktor
                anapara = max(anapara, self.reel_nominal)
                tutar = kupon + anapara
            akislar.append((t, tutar))
        return akislar

    # ------------------------------------------------------------------
    # Değerleme
    # ------------------------------------------------------------------
    def reel_fiyat(self, reel_getiri: float) -> float:
        """Reel getiriyle iskonto edilmiş REEL kirli fiyat.

        Endeksli tahvilin standart kotasyonudur: reel akışlar reel
        getiriyle iskonto edilir; sonuç endekssiz (reel) fiyattır.
        """
        return kirli_fiyat(self._reel_tahvil(), reel_getiri)

    def nominal_fiyat(self, reel_getiri: float) -> float:
        """Bugünkü NOMİNAL (TL) kirli fiyat = reel fiyat × endeks oranı.

        Endekslemenin çarpımsallığı sayesinde beklenen enflasyon fiyattan
        bağımsızdır (nominal akışları nominal getiriyle iskonto etmekle
        aynı sonucu verir); enflasyon yalnızca GETİRİ ayrışımında rol oynar.
        """
        return self.reel_fiyat(reel_getiri) * self.endeks_orani

    def __str__(self) -> str:
        ad = self.isim or "Endeksli tahvil"
        return (
            f"{ad}: reel nominal={self.reel_nominal:g}, reel kupon="
            f"%{self.reel_kupon_orani * 100:.2f}, vade={self.vade_yil:g} yıl, "
            f"endeks={self.endeks_orani:.4f}"
        )


def basit_degerleme(tahvil: EndeksliTahvil, reel_getiri: float, beklenen_enflasyon: float) -> dict:
    """Endeksli tahvilin özet değerlemesi (Türkçe anahtarlı sözlük).

    Args:
        tahvil: Endeksli tahvil.
        reel_getiri: Piyasa reel getirisi (ondalık).
        beklenen_enflasyon: Yıllık beklenen enflasyon (ondalık).

    Returns:
        Sözlük: reel fiyat, nominal fiyat, düzeltilmiş anapara, Fisher
        ile bulunan eşdeğer nominal getiri ve projekte ilk/son akışlar.
    """
    akislar = tahvil.nakit_akislari_nominal(beklenen_enflasyon)
    return {
        "reel_fiyat": tahvil.reel_fiyat(reel_getiri),
        "nominal_fiyat": tahvil.nominal_fiyat(reel_getiri),
        "duzeltilmis_anapara": tahvil.duzeltilmis_anapara,
        "nominal_esdeger_getiri": fisher_nominal(reel_getiri, beklenen_enflasyon),
        "ilk_akis": akislar[0],
        "son_akis": akislar[-1],
    }
