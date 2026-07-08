"""Getiri eğrisi araçları.

İçerik:
    * :class:`GetiriEgrisi` — spot (sıfır kuponlu) oran eğrisi; doğrusal
      veya kübik interpolasyon, iskonto faktörü ve forward oran hesabı.
    * :meth:`GetiriEgrisi.bootstrap` — kuponlu tahvil fiyatlarından spot
      eğri çıkarımı (ardışık kök bulma ile klasik bootstrapping).
    * :func:`nelson_siegel_uydur` — Nelson-Siegel parametrik eğri uydurma
      (scipy.optimize.least_squares ile).

Oran kuralı: tüm spot oranlar YILLIK BİLEŞİK getiri olarak tutulur;
``DF(t) = (1 + z(t))^(-t)``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq, least_squares

from bond_lab.bond import NakitAkisi, Tahvil


class GetiriEgrisi:
    """Spot getiri eğrisi.

    Args:
        vadeler: Artan sıralı vade noktaları (yıl). En az 1 nokta.
        oranlar: Her vadeye karşılık yıllık bileşik spot oran (ondalık).
        interpolasyon: ``"dogrusal"`` veya ``"kubik"`` (doğal kübik spline).

    Not:
        Eğri, tanım aralığının dışında düz (flat) ekstrapolasyon yapar:
        ilk vadeden küçük t için ilk oran, son vadeden büyük t için son
        oran kullanılır. Bu, uç bölgelerde taşmayı önler.
    """

    def __init__(
        self,
        vadeler: Sequence[float],
        oranlar: Sequence[float],
        interpolasyon: str = "dogrusal",
    ) -> None:
        if len(vadeler) != len(oranlar):
            raise ValueError("Vade ve oran listeleri aynı uzunlukta olmalıdır.")
        if len(vadeler) == 0:
            raise ValueError("Eğri için en az bir nokta gereklidir.")
        if interpolasyon not in ("dogrusal", "kubik"):
            raise ValueError("interpolasyon 'dogrusal' veya 'kubik' olmalıdır.")
        v = np.asarray(vadeler, dtype=float)
        o = np.asarray(oranlar, dtype=float)
        sira = np.argsort(v)
        self.vadeler: np.ndarray = v[sira]
        self.oranlar: np.ndarray = o[sira]
        if np.any(np.diff(self.vadeler) <= 0):
            raise ValueError("Vade noktaları birbirinden farklı olmalıdır.")
        if np.any(self.vadeler <= 0):
            raise ValueError("Vade noktaları pozitif olmalıdır.")
        self.interpolasyon = interpolasyon
        self._spline: CubicSpline | None = (
            CubicSpline(self.vadeler, self.oranlar, bc_type="natural")
            if interpolasyon == "kubik" and len(self.vadeler) >= 2
            else None
        )

    # ------------------------------------------------------------------
    # Temel sorgular
    # ------------------------------------------------------------------
    def spot_oran(self, t: float) -> float:
        """t vadesindeki (yıl) yıllık bileşik spot oran."""
        if t <= 0:
            return float(self.oranlar[0])
        t_kirp = float(np.clip(t, self.vadeler[0], self.vadeler[-1]))
        if self._spline is not None:
            return float(self._spline(t_kirp))
        return float(np.interp(t_kirp, self.vadeler, self.oranlar))

    def iskonto_faktoru(self, t: float) -> float:
        """DF(t) = (1 + z(t))^(-t); t<=0 için 1."""
        if t <= 0:
            return 1.0
        return (1.0 + self.spot_oran(t)) ** (-t)

    def forward_oran(self, t1: float, t2: float) -> float:
        """t1 ile t2 arasındaki yıllık bileşik forward oran.

        ``(1+z2)^t2 = (1+z1)^t1 · (1+f)^(t2-t1)`` eşitliğinden çözülür.

        Raises:
            ValueError: t2 <= t1 veya t1 < 0 ise.
        """
        if t1 < 0 or t2 <= t1:
            raise ValueError("0 <= t1 < t2 olmalıdır.")
        df1 = self.iskonto_faktoru(t1)
        df2 = self.iskonto_faktoru(t2)
        return (df1 / df2) ** (1.0 / (t2 - t1)) - 1.0

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------
    @classmethod
    def bootstrap(
        cls,
        enstrumanlar: Sequence[tuple[Tahvil, float]],
        temiz: bool = True,
        interpolasyon: str = "dogrusal",
    ) -> GetiriEgrisi:
        """Kuponlu tahvil fiyatlarından spot eğri çıkarır.

        Tahviller vadeye göre sıralanır; her tahvil için, ara nakit
        akışları o ana kadar çözülmüş eğriyle iskonto edilir ve tahvilin
        SON vadesindeki spot oran, bugünkü değer piyasa fiyatına eşit
        olacak şekilde kök bulma (brentq) ile çözülür. Ara akış zamanı
        henüz bilinen aralıkta değilse çözülmekte olan pillar da dahil
        edilerek interpolasyon yapılır (iteratif bootstrap).

        Args:
            enstrumanlar: (tahvil, fiyat) çiftleri.
            temiz: True ise fiyatlar temiz kabul edilir ve işlemiş faiz
                eklenir; False ise kirli fiyattır.
            interpolasyon: Sonuç eğrisinin interpolasyon türü.

        Returns:
            Çözülmüş :class:`GetiriEgrisi`.

        Raises:
            ValueError: Enstrüman yoksa, vadeler çakışıyorsa veya kök
                makul aralıkta bulunamazsa.
        """
        if not enstrumanlar:
            raise ValueError("Bootstrap için en az bir enstrüman gereklidir.")
        sirali = sorted(enstrumanlar, key=lambda cift: cift[0].vade_yil)
        vadeler: list[float] = []
        oranlar: list[float] = []

        for tahvil, fiyat in sirali:
            if vadeler and math.isclose(tahvil.vade_yil, vadeler[-1], abs_tol=1e-9):
                raise ValueError(
                    f"Aynı vadede ({tahvil.vade_yil:g} yıl) birden fazla enstrüman var."
                )
            hedef = fiyat + (tahvil.islemis_faiz() if temiz else 0.0)
            akislar = tahvil.nakit_akislari()
            vade_t = tahvil.vade_yil

            def fiyat_farki(
                z_yeni: float,
                _vade: float = vade_t,
                _akislar: list[NakitAkisi] = akislar,
                _hedef: float = hedef,
            ) -> float:
                # Döngü değişkenleri varsayılan argümanla bağlanır (geç bağlanma önlenir).
                v = np.array(vadeler + [_vade])
                o = np.array(oranlar + [z_yeni])
                pv = 0.0
                for t, cf in _akislar:
                    t_kirp = float(np.clip(t, v[0], v[-1]))
                    z = float(np.interp(t_kirp, v, o))
                    pv += cf * (1.0 + z) ** (-t)
                return pv - _hedef

            try:
                z_cozum = brentq(fiyat_farki, -0.99, 10.0, xtol=1e-14, maxiter=200)
            except ValueError as hata:
                raise ValueError(
                    f"{tahvil.vade_yil:g} yıl vadeli enstrüman için spot oran "
                    f"(-%99, %1000) aralığında bulunamadı."
                ) from hata
            vadeler.append(vade_t)
            oranlar.append(float(z_cozum))

        return cls(vadeler, oranlar, interpolasyon=interpolasyon)

    def __repr__(self) -> str:
        noktalar = ", ".join(
            f"{v:g}y=%{o * 100:.2f}" for v, o in zip(self.vadeler, self.oranlar, strict=True)
        )
        return f"GetiriEgrisi({noktalar})"


# ----------------------------------------------------------------------
# Nelson-Siegel
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class NelsonSiegelSonuc:
    """Nelson-Siegel uydurma sonucu.

    Model: ``r(t) = b0 + b1·φ(t) + b2·(φ(t) − exp(−t/τ))``,
    ``φ(t) = (1 − exp(−t/τ)) / (t/τ)``.

    Attributes:
        beta0: Uzun vade seviyesi (t→∞ limiti).
        beta1: Kısa vade bileşeni (r(0) = beta0 + beta1).
        beta2: Orta vade "kamburluk" bileşeni.
        tau: Zaman ölçeği (yıl), pozitif.
        rmse: Uydurma hatası (kök ortalama kare hata).
    """

    beta0: float
    beta1: float
    beta2: float
    tau: float
    rmse: float

    def oran(self, t: float) -> float:
        """Modelin t (yıl) vadesindeki oranı."""
        return nelson_siegel_orani(t, self.beta0, self.beta1, self.beta2, self.tau)


def nelson_siegel_orani(t: float, beta0: float, beta1: float, beta2: float, tau: float) -> float:
    """Nelson-Siegel oran fonksiyonu; t=0 limiti beta0 + beta1'dir."""
    if tau <= 0:
        raise ValueError("tau pozitif olmalıdır.")
    if t <= 1e-12:
        return beta0 + beta1
    x = t / tau
    fi = (1.0 - math.exp(-x)) / x
    return beta0 + beta1 * fi + beta2 * (fi - math.exp(-x))


def nelson_siegel_uydur(
    vadeler: Sequence[float] | np.ndarray, oranlar: Sequence[float] | np.ndarray
) -> NelsonSiegelSonuc:
    """Gözlenen (vade, spot oran) noktalarına Nelson-Siegel eğrisi uydurur.

    scipy ``least_squares`` ile [beta0, beta1, beta2, tau] çözülür;
    tau > 0 kısıtı sınır (bounds) ile uygulanır.

    Args:
        vadeler: Vade noktaları (yıl), en az 4 nokta önerilir.
        oranlar: Karşılık gelen spot oranlar (ondalık).

    Returns:
        :class:`NelsonSiegelSonuc`.

    Raises:
        ValueError: Nokta sayısı 4'ten azsa.
    """
    v = np.asarray(vadeler, dtype=float)
    o = np.asarray(oranlar, dtype=float)
    if len(v) < 4:
        raise ValueError("Nelson-Siegel için en az 4 gözlem gereklidir.")

    def artiklar(p: np.ndarray) -> np.ndarray:
        b0, b1, b2, tau = p
        model = np.array([nelson_siegel_orani(t, b0, b1, b2, tau) for t in v])
        return model - o

    b0_0 = float(o[-1])
    b1_0 = float(o[0] - o[-1])
    baslangic = np.array([b0_0, b1_0, 0.0, 1.5])
    sonuc = least_squares(
        artiklar,
        baslangic,
        bounds=([-1.0, -1.0, -1.0, 1e-3], [1.0, 1.0, 1.0, 30.0]),
        method="trf",
    )
    b0, b1, b2, tau = (float(x) for x in sonuc.x)
    rmse = float(np.sqrt(np.mean(sonuc.fun**2)))
    return NelsonSiegelSonuc(beta0=b0, beta1=b1, beta2=b2, tau=tau, rmse=rmse)
