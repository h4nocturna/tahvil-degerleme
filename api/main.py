"""Tahvil Laboratuvarı REST API — bond_lab motorunu Lovable frontend'e bağlar.

Çalıştırma:
    .venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000

Swagger: http://localhost:8000/docs
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bond_lab import (
    Tahvil,
    dv01,
    kirli_fiyat,
    konveksite,
    macaulay_durasyon,
    modifiye_durasyon,
    strateji_oner,
    temiz_fiyat,
    ytm_bul,
)
from bond_lab.market_data import dibs_ornek_egrisi, ust_ornek_egrisi

app = FastAPI(
    title="Tahvil Laboratuvarı API",
    description="Tahvil fiyatlama, risk ölçütleri ve strateji önerisi — bond_lab motoru.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://lovable.dev",
        "https://*.lovable.app",
        "https://*.lovableproject.com",
    ],
    allow_origin_regex=r"https://.*\.(lovable\.app|lovableproject\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TahvilGirdi(BaseModel):
    nominal: float = Field(100.0, gt=0, description="Nominal değer")
    kupon_orani: float = Field(0.35, ge=0, description="Yıllık kupon oranı (ondalık, 0.35 = %35)")
    vade_yil: float = Field(5.0, gt=0, description="Vade (yıl)")
    frekans: int = Field(2, ge=1, le=12, description="Yıllık kupon ödeme sayısı")
    mod: Literal["ytm_den_fiyat", "fiyattan_ytm"] = "ytm_den_fiyat"
    ytm: float | None = Field(0.42, description="YTM (ondalık) — mod=ytm_den_fiyat iken")
    temiz_fiyat: float | None = Field(None, gt=0, description="Temiz fiyat — mod=fiyattan_ytm iken")


class FiyatGetiriNokta(BaseModel):
    ytm_yuzde: float
    kirli_fiyat: float
    temiz_fiyat: float
    fiyat_farki_yuzde: float
    mevcut: bool


class FiyatlamaYanit(BaseModel):
    temiz_fiyat: float
    kirli_fiyat: float
    ytm_yuzde: float
    macaulay_durasyon: float
    modifiye_durasyon: float
    dv01: float
    konveksite: float
    fiyat_getiri: list[FiyatGetiriNokta]


class StratejiGirdi(BaseModel):
    beklenti: Literal["yukselecek", "dusecek", "sabit"]
    ufuk_yil: float = Field(5.0, gt=0)
    risk: Literal["dusuk", "orta", "yuksek"]


class StratejiYanit(BaseModel):
    strateji: str
    hedef_durasyon: float
    gerekce: str


class EgrisiNokta(BaseModel):
    vade_yil: float
    oran_yuzde: float


@app.get("/api/saglik")
def saglik() -> dict[str, str]:
    return {"durum": "ok", "motor": "bond_lab"}


@app.post("/api/fiyatla", response_model=FiyatlamaYanit)
def fiyatla(girdi: TahvilGirdi) -> FiyatlamaYanit:
    tahvil = Tahvil(
        nominal=girdi.nominal,
        kupon_orani=girdi.kupon_orani,
        vade_yil=girdi.vade_yil,
        frekans=girdi.frekans,
        isim="API tahvili",
    )
    try:
        if girdi.mod == "ytm_den_fiyat":
            if girdi.ytm is None:
                raise HTTPException(status_code=422, detail="YTM gerekli (mod=ytm_den_fiyat).")
            ytm = girdi.ytm
        else:
            if girdi.temiz_fiyat is None:
                raise HTTPException(status_code=422, detail="Temiz fiyat gerekli (mod=fiyattan_ytm).")
            ytm = ytm_bul(tahvil, girdi.temiz_fiyat, temiz=True)

        kirli = kirli_fiyat(tahvil, ytm)
        temiz = temiz_fiyat(tahvil, ytm)
        merkez = ytm * 100.0
        adim = 0.5
        alt = max(0.01, merkez - 15.0)
        ust = merkez + 15.0

        egrisi: list[FiyatGetiriNokta] = []
        import numpy as np

        for y_pct in np.arange(alt, ust + adim / 2, adim):
            y_dec = float(y_pct) / 100.0
            try:
                k = kirli_fiyat(tahvil, y_dec)
                t = temiz_fiyat(tahvil, y_dec)
            except ValueError:
                continue
            egrisi.append(
                FiyatGetiriNokta(
                    ytm_yuzde=float(y_pct),
                    kirli_fiyat=k,
                    temiz_fiyat=t,
                    fiyat_farki_yuzde=(k - kirli) / kirli * 100.0,
                    mevcut=abs(float(y_pct) - merkez) < adim / 2,
                )
            )

        return FiyatlamaYanit(
            temiz_fiyat=temiz,
            kirli_fiyat=kirli,
            ytm_yuzde=ytm * 100.0,
            macaulay_durasyon=macaulay_durasyon(tahvil, ytm),
            modifiye_durasyon=modifiye_durasyon(tahvil, ytm),
            dv01=dv01(tahvil, ytm),
            konveksite=konveksite(tahvil, ytm),
            fiyat_getiri=egrisi,
        )
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata)) from hata


@app.post("/api/strateji-oner", response_model=StratejiYanit)
def strateji_oner_api(girdi: StratejiGirdi) -> StratejiYanit:
    sonuc = strateji_oner(girdi.beklenti, girdi.ufuk_yil, girdi.risk)
    return StratejiYanit(
        strateji=sonuc.strateji,
        hedef_durasyon=sonuc.hedef_durasyon,
        gerekce=sonuc.gerekce,
    )


@app.get("/api/egri/{kaynak}", response_model=list[EgrisiNokta])
def ornek_egri(kaynak: Literal["dibs", "ust"]) -> list[EgrisiNokta]:
    paket = dibs_ornek_egrisi() if kaynak == "dibs" else ust_ornek_egrisi()
    egri = paket.spot_egri()
    return [
        EgrisiNokta(vade_yil=float(v), oran_yuzde=float(o) * 100.0)
        for v, o in zip(egri.vadeler, egri.oranlar, strict=True)
    ]
