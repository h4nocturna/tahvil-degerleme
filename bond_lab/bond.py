"""Tahvil (bono) tanımı ve nakit akışı üretimi.

Bu modül, sabit kuponlu ve sıfır kuponlu tahvilleri temsil eden
:class:`Tahvil` sınıfını içerir.

Zaman/vade kuralları:
    * Vade, valör (takas) tarihinden itibaren YIL cinsinden tutulur.
    * Kesirli vade desteklenir: örneğin ``vade_yil=4.75`` ve yıllık kupon,
      içinde bulunulan kupon döneminin %25'inin geçtiği anlamına gelir;
      işlemiş (birikmiş) faiz bu orandan türetilir.
    * Tarihlerle çalışmak için :meth:`Tahvil.tarihlerden` kurucusu
      basitleştirilmiş ACT/365 kuralını kullanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

#: Tek bir nakit akışı: (zaman_yil, tutar) çifti.
NakitAkisi = tuple[float, float]

#: Desteklenen kupon frekansları (yılda ödeme sayısı).
GECERLI_FREKANSLAR = (1, 2, 4, 12)


@dataclass(frozen=True)
class Tahvil:
    """Sabit kuponlu veya sıfır kuponlu tahvil.

    Attributes:
        nominal: Nominal (itibari) değer; vadede geri ödenen anapara.
        kupon_orani: YILLIK kupon oranı, ondalık biçimde (0.10 = %10).
            Sıfır kuponlu (iskontolu) tahvil için 0 verin.
        vade_yil: Valörden vadeye kalan süre, yıl cinsinden. Kesirli olabilir.
        frekans: Yılda kupon ödeme sayısı (1=yıllık, 2=6 aylık, 4=3 aylık, 12=aylık).
        isim: Raporlamada kullanılacak opsiyonel etiket.
    """

    nominal: float = 100.0
    kupon_orani: float = 0.0
    vade_yil: float = 1.0
    frekans: int = 1
    isim: str = ""

    def __post_init__(self) -> None:
        if self.nominal <= 0:
            raise ValueError("Nominal değer pozitif olmalıdır.")
        if self.kupon_orani < 0:
            raise ValueError("Kupon oranı negatif olamaz.")
        if self.vade_yil <= 0:
            raise ValueError("Vade pozitif olmalıdır.")
        if self.frekans not in GECERLI_FREKANSLAR:
            raise ValueError(f"Frekans {GECERLI_FREKANSLAR} değerlerinden biri olmalıdır.")

    # ------------------------------------------------------------------
    # Alternatif kurucular
    # ------------------------------------------------------------------
    @classmethod
    def tarihlerden(
        cls,
        nominal: float,
        kupon_orani: float,
        valor_tarihi: date,
        vade_tarihi: date,
        frekans: int = 1,
        isim: str = "",
    ) -> Tahvil:
        """Valör ve vade tarihlerinden tahvil kurar.

        Yıl kesri basitleştirilmiş ACT/365 kuralıyla hesaplanır:
        ``vade_yil = (vade_tarihi - valor_tarihi).days / 365``.

        Args:
            nominal: Nominal değer.
            kupon_orani: Yıllık kupon oranı (ondalık).
            valor_tarihi: Takas (yerleşim) tarihi.
            vade_tarihi: İtfa tarihi.
            frekans: Yılda kupon sayısı.
            isim: Opsiyonel etiket.

        Raises:
            ValueError: Vade tarihi valörden önce veya aynı gündeyse.
        """
        gun = (vade_tarihi - valor_tarihi).days
        if gun <= 0:
            raise ValueError("Vade tarihi valör tarihinden sonra olmalıdır.")
        return cls(
            nominal=nominal,
            kupon_orani=kupon_orani,
            vade_yil=gun / 365.0,
            frekans=frekans,
            isim=isim,
        )

    # ------------------------------------------------------------------
    # Temel özellikler
    # ------------------------------------------------------------------
    @property
    def sifir_kuponlu(self) -> bool:
        """Tahvil kuponsuz (sıfır kuponlu) mu?"""
        return self.kupon_orani == 0.0

    @property
    def donem(self) -> float:
        """Kupon dönemi uzunluğu, yıl cinsinden (örn. 6 aylık kupon için 0.5)."""
        return 1.0 / self.frekans

    @property
    def kupon_tutari(self) -> float:
        """Bir kupon döneminde ödenen tutar = nominal × kupon oranı / frekans."""
        return self.nominal * self.kupon_orani / self.frekans

    @property
    def kupon_sayisi(self) -> int:
        """Vadeye kadar kalan kupon ödemesi sayısı."""
        return max(math.ceil(self.vade_yil * self.frekans - 1e-9), 1)

    # ------------------------------------------------------------------
    # Nakit akışları
    # ------------------------------------------------------------------
    def nakit_akislari(self) -> list[NakitAkisi]:
        """Tahvilin kalan nakit akışlarını (zaman_yil, tutar) listesi olarak üretir.

        Son akış kupon + anaparayı içerir. Sıfır kuponlu tahvilde tek akış
        vardır: vadede nominal. Kesirli vadede ilk kupon, içinde bulunulan
        dönemin kalan kısmına denk gelir (0 < t_ilk <= dönem).
        """
        if self.sifir_kuponlu:
            return [(self.vade_yil, self.nominal)]
        n = self.kupon_sayisi
        akislar: list[NakitAkisi] = []
        for i in range(1, n + 1):
            t = self.vade_yil - (n - i) * self.donem
            tutar = self.kupon_tutari + (self.nominal if i == n else 0.0)
            akislar.append((t, tutar))
        return akislar

    @property
    def islemis_donem_orani(self) -> float:
        """İçinde bulunulan kupon döneminin geçmiş kısmı (0 ile 1 arasında).

        Vade, dönem uzunluğunun tam katıysa 0 döner (kupon günündeyiz).
        """
        if self.sifir_kuponlu:
            return 0.0
        ilk_kupon_zamani = self.vade_yil - (self.kupon_sayisi - 1) * self.donem
        oran = 1.0 - ilk_kupon_zamani / self.donem
        return min(max(oran, 0.0), 1.0)

    def islemis_faiz(self) -> float:
        """İşlemiş (birikmiş) faiz tutarı = kupon tutarı × geçen dönem oranı."""
        return self.kupon_tutari * self.islemis_donem_orani

    def __str__(self) -> str:
        ad = self.isim or "Tahvil"
        return (
            f"{ad}: nominal={self.nominal:g}, kupon=%{self.kupon_orani * 100:.2f}, "
            f"vade={self.vade_yil:.2f} yıl, frekans={self.frekans}"
        )
