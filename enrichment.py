"""
CoinGecko enrichment: volume, market cap, price, categories.
Uses the free public API (no key required).
"""

import asyncio
import aiohttp
import time
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

_cache: Dict[str, Tuple[Any, float]] = {}
CG_BASE = "https://api.coingecko.com/api/v3"
COINS_LIST_TTL = 3600   # 1 hour
MARKET_TTL = 300        # 5 minutes
DETAIL_TTL = 3600       # 1 hour


async def _get(url: str, key: str, ttl: int) -> Optional[Any]:
    now = time.time()
    if key in _cache:
        data, ts = _cache[key]
        if now - ts < ttl:
            return data
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
        ) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    _cache[key] = (data, now)
                    return data
                if r.status == 429:
                    logger.warning("CoinGecko rate limit; sleeping 60 s")
                    await asyncio.sleep(60)
    except Exception as e:
        logger.error("CG fetch error %s: %s", url, e)
    return None


async def coins_list() -> Dict[str, List[str]]:
    """Returns {SYMBOL: [cg_id, ...]} — free tier, cached 1 h."""
    data = await _get(f"{CG_BASE}/coins/list", "cg_list", COINS_LIST_TTL)
    if not data:
        return {}
    sym_map: Dict[str, List[str]] = {}
    for coin in data:
        sym = coin.get("symbol", "").upper()
        cid = coin.get("id", "")
        if sym and cid:
            sym_map.setdefault(sym, []).append(cid)
    return sym_map


# Prefer well-known IDs when a symbol maps to multiple coins
_PREFERRED_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "ADA": "cardano", "AVAX": "avalanche-2",
    "DOT": "polkadot", "DOGE": "dogecoin", "LINK": "chainlink",
    "MATIC": "matic-network", "UNI": "uniswap", "ATOM": "cosmos",
    "LTC": "litecoin", "BCH": "bitcoin-cash", "NEAR": "near",
    "APT": "aptos", "OP": "optimism", "ARB": "arbitrum",
    "SUI": "sui", "TON": "the-open-network", "INJ": "injective-protocol",
    "SEI": "sei-network", "TIA": "celestia", "PEPE": "pepe",
    "WLD": "worldcoin-wld", "SHIB": "shiba-inu", "BONK": "bonk",
    "FLOKI": "floki", "NOT": "notcoin", "ORDI": "ordinals",
}


def _best_id(sym: str, ids: List[str]) -> str:
    if sym in _PREFERRED_IDS:
        pid = _PREFERRED_IDS[sym]
        if pid in ids:
            return pid
    # Prefer exact name match (lower priority IDs tend to be clones)
    for cid in ids:
        if cid == sym.lower():
            return cid
    return ids[0]


async def market_data(coin_ids: List[str]) -> Dict[str, dict]:
    """Batch-fetch market data for up to 250 coin IDs per request."""
    if not coin_ids:
        return {}
    result: Dict[str, dict] = {}
    batch_size = 200
    for i in range(0, len(coin_ids), batch_size):
        batch = coin_ids[i : i + batch_size]
        ids_str = ",".join(batch)
        url = (
            f"{CG_BASE}/coins/markets?vs_currency=usd&ids={ids_str}"
            f"&per_page={batch_size}&sparkline=false"
            f"&price_change_percentage=24h"
        )
        data = await _get(url, f"cg_markets_{hash(ids_str)}", MARKET_TTL)
        if data:
            for coin in data:
                cid = coin.get("id")
                if cid:
                    result[cid] = {
                        "total_volume": coin.get("total_volume") or 0,
                        "market_cap": coin.get("market_cap") or 0,
                        "price": coin.get("current_price") or 0,
                        "price_change_24h": coin.get("price_change_percentage_24h") or 0,
                        "name": coin.get("name", ""),
                        "image": coin.get("image", ""),
                    }
        if i + batch_size < len(coin_ids):
            await asyncio.sleep(1.2)
    return result


async def coin_categories(cg_id: str) -> List[str]:
    url = (
        f"{CG_BASE}/coins/{cg_id}"
        "?localization=false&tickers=false&market_data=false"
        "&community_data=false&developer_data=false&sparkline=false"
    )
    data = await _get(url, f"cg_detail_{cg_id}", DETAIL_TTL)
    if not data:
        return []
    return [c for c in data.get("categories", []) if c]


async def enrich(symbols: List[str], fetch_categories: bool = False) -> Dict[str, dict]:
    """
    Enrich symbols with CoinGecko volume, market cap, price, optional categories.
    Returns {SYMBOL: {...}}
    """
    sym_map = await coins_list()

    sym_to_id: Dict[str, str] = {}
    for sym in symbols:
        ids = sym_map.get(sym.upper(), [])
        if ids:
            sym_to_id[sym.upper()] = _best_id(sym.upper(), ids)

    if not sym_to_id:
        return {}

    mdata = await market_data(list(sym_to_id.values()))

    result: Dict[str, dict] = {}
    for sym, cid in sym_to_id.items():
        md = mdata.get(cid, {})
        result[sym] = {
            "cg_id": cid,
            "name": md.get("name", sym),
            "image": md.get("image", ""),
            "volume_24h": md.get("total_volume", 0),
            "market_cap": md.get("market_cap", 0),
            "price": md.get("price", 0),
            "price_change_24h": md.get("price_change_24h", 0),
            "categories": [],
        }

    # Optionally fetch categories for top tokens by volume (rate-limit aware)
    if fetch_categories:
        sorted_syms = sorted(
            [(s, d) for s, d in result.items() if d.get("cg_id")],
            key=lambda x: x[1].get("volume_24h", 0),
            reverse=True,
        )[:60]
        for i, (sym, data) in enumerate(sorted_syms):
            cats = await coin_categories(data["cg_id"])
            result[sym]["categories"] = cats
            if (i + 1) % 5 == 0:
                await asyncio.sleep(2)

    return result
