"""
OKX Token Sourcing Dashboard — FastAPI backend
"""

import logging
from typing import List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from exchanges import EXCHANGES, fetch_all_listings
from enrichment import enrich

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="OKX Token Sourcing Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def root():
    return "static/index.html"


@app.get("/api/exchanges")
async def list_exchanges():
    """Return metadata for all supported exchanges."""
    out = []
    for eid, info in EXCHANGES.items():
        out.append(
            {
                "id": eid,
                "name": info["name"],
                "region": info["region"],
                "has_spot": info.get("spot") is not None,
                "has_perp": info.get("perp") is not None,
                "data_note": info.get("data_note", ""),
            }
        )
    return {"exchanges": out}


@app.get("/api/tokens")
async def get_tokens(
    exchanges: str = Query(..., description="Comma-separated exchange IDs, e.g. upbit,bithumb,binance"),
    product_type: str = Query("spot", description="spot | perp | both"),
    include_categories: bool = Query(False, description="Fetch sector categories (slower ~30-60 s extra)"),
    limit: int = Query(300, ge=1, le=1000),
):
    """
    Return tokens listed on *selected exchanges* that are NOT on OKX,
    enriched with CoinGecko volume, market cap, price, and optional categories.
    """
    selected: List[str] = [e.strip().lower() for e in exchanges.split(",") if e.strip()]
    unknown = [e for e in selected if e not in EXCHANGES]
    if unknown:
        return {"error": f"Unknown exchange(s): {unknown}", "tokens": []}
    if product_type not in ("spot", "perp", "both"):
        return {"error": "product_type must be spot | perp | both", "tokens": []}

    missing = await fetch_all_listings(selected, product_type)
    if not missing:
        return {
            "tokens": [],
            "total": 0,
            "product_type": product_type,
            "exchanges": selected,
            "message": "No tokens found (OKX already lists everything on the selected exchanges).",
        }

    symbols = list(missing.keys())
    enriched = await enrich(symbols, fetch_categories=include_categories)

    tokens = []
    for sym in symbols:
        info = missing[sym]
        cg = enriched.get(sym, {})
        tokens.append(
            {
                "symbol": sym,
                "name": cg.get("name") or sym,
                "image": cg.get("image", ""),
                "exchanges": info["exchanges"],
                "listing_types": info["listing_types"],
                "volume_24h": cg.get("volume_24h", 0),
                "market_cap": cg.get("market_cap", 0),
                "price": cg.get("price", 0),
                "price_change_24h": cg.get("price_change_24h", 0),
                "categories": cg.get("categories", []),
                "cg_id": cg.get("cg_id", ""),
                "volume_source": "CoinGecko" if cg.get("volume_24h") else "—",
            }
        )

    tokens.sort(key=lambda x: x["volume_24h"] or 0, reverse=True)

    return {
        "tokens": tokens[:limit],
        "total": len(tokens),
        "product_type": product_type,
        "exchanges": selected,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}
