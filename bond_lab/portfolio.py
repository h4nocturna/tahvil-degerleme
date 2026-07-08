"""Tahvil portföyü: pozisyonlar, ağırlıklı ölçütler ve nakit akışı takvimi.

Portföy ölçütleri piyasa değeri ağırlıklıdır: portföy durasyonu,
pozisyonların (modifiye) durasyonlarının piyasa değeri ağırlıklı
ortalamasıdır; konveksite ve getiri için de aynı kural geçerlidir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from bond_lab.bond import Tahvil
from bond_lab.pricing import kirli_fiyat
from bond_lab.risk import konveksite, macaulay_durasyon, modifiye_durasyon


@dataclass(frozen=True)
class Pozisyon:
    """Portföydeki tek bir tahvil pozisyonu.

    Attributes:
        tahvil: Tutulan tahvil.
        adet: Tahvil adedi (kesirli olabilir).
        ytm: Pozisyonun değerlemesinde kullanılan yıllık getiri.
    """

    tahvil: Tahvil
    adet: float
    ytm: float

    def __post_init__(self) -> None:
        if self.adet <= 0:
            raise ValueError("Pozisyon adedi pozitif olmalıdır.")

    @property
    def birim_fiyat(self) -> float:
        """Tek tahvilin kirli fiyatı."""
        return kirli_fiyat(self.tahvil, self.ytm)

    @property
    def piyasa_degeri(self) -> float:
        """Pozisyonun toplam piyasa değeri = adet × kirli fiyat."""
        return self.adet * self.birim_fiyat


@dataclass
class Portfoy:
    """Tahvil portföyü.

    Attributes:
        pozisyonlar: Pozisyon listesi.
        isim: Raporlamada kullanılacak opsiyonel etiket.
    """

    pozisyonlar: list[Pozisyon] = field(default_factory=list)
    isim: str = "Portföy"

    def ekle(self, pozisyon: Pozisyon) -> None:
        """Portföye pozisyon ekler."""
        self.pozisyonlar.append(pozisyon)

    # ------------------------------------------------------------------
    # Değer ve ağırlıklar
    # ------------------------------------------------------------------
    @property
    def toplam_deger(self) -> float:
        """Toplam piyasa değeri (kirli fiyatlarla)."""
        return sum(p.piyasa_degeri for p in self.pozisyonlar)

    def agirliklar(self) -> list[float]:
        """Piyasa değeri ağırlıkları (toplamı 1)."""
        toplam = self.toplam_deger
        if toplam <= 0:
            raise ValueError("Portföy değeri pozitif olmalıdır.")
        return [p.piyasa_degeri / toplam for p in self.pozisyonlar]

    def _agirlikli(self, olcut: Callable[[Tahvil, float], float]) -> float:
        """Verilen ölçütün piyasa değeri ağırlıklı ortalaması."""
        return sum(
            w * olcut(p.tahvil, p.ytm)
            for w, p in zip(self.agirliklar(), self.pozisyonlar, strict=True)
        )

    # ------------------------------------------------------------------
    # Ağırlıklı risk/getiri ölçütleri
    # ------------------------------------------------------------------
    def portfoy_macaulay_durasyon(self) -> float:
        """Piyasa değeri ağırlıklı Macaulay durasyonu (yıl)."""
        return self._agirlikli(macaulay_durasyon)

    def portfoy_modifiye_durasyon(self) -> float:
        """Piyasa değeri ağırlıklı modifiye durasyon."""
        return self._agirlikli(modifiye_durasyon)

    def portfoy_konveksite(self) -> float:
        """Piyasa değeri ağırlıklı konveksite."""
        return self._agirlikli(konveksite)

    def portfoy_getiri(self) -> float:
        """Piyasa değeri ağırlıklı ortalama getiri (yaklaşık portföy YTM'si)."""
        return sum(w * p.ytm for w, p in zip(self.agirliklar(), self.pozisyonlar, strict=True))

    # ------------------------------------------------------------------
    # Nakit akışları ve senaryo değerleme
    # ------------------------------------------------------------------
    def nakit_akisi_takvimi(self) -> list[tuple[float, float]]:
        """Tüm pozisyonların birleşik nakit akışı takvimi.

        Aynı zamana (1e-6 yıl hassasiyetle) düşen akışlar toplanır;
        sonuç zamana göre sıralı (zaman_yil, toplam_tutar) listesidir.
        """
        takvim: dict[float, float] = {}
        for p in self.pozisyonlar:
            for t, cf in p.tahvil.nakit_akislari():
                anahtar = round(t, 6)
                takvim[anahtar] = takvim.get(anahtar, 0.0) + cf * p.adet
        return sorted(takvim.items())

    def senaryo_degeri(self, kayma: Callable[[float], float]) -> float:
        """Getiri kayması senaryosu altında portföy değeri.

        Her pozisyon ``ytm + kayma(vade_yil)`` getirisiyle yeniden fiyatlanır.

        Args:
            kayma: Vadeye (yıl) göre getiri değişimi döndüren fonksiyon
                (ondalık; +0.01 = +100bp).
        """
        return sum(
            p.adet * kirli_fiyat(p.tahvil, p.ytm + kayma(p.tahvil.vade_yil))
            for p in self.pozisyonlar
        )

    def __str__(self) -> str:
        return (
            f"{self.isim}: {len(self.pozisyonlar)} pozisyon, "
            f"toplam değer={self.toplam_deger:,.2f}"
        )
