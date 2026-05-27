"""
Exchange API clients for fetching spot and perpetual token listings.
Each function returns a Set[str] of normalized uppercase base symbols.
"""

import asyncio
import aiohttp
import time
import logging
from typing import Dict, Set, Optional, Any, List, Tuple

logger = logging.getLogger(__name__)

_cache: Dict[str, Tuple[Any, float]] = {}
EXCHANGE_TTL = 300  # 5 minutes


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


async def _get(url: str, key: str, ttl: int = EXCHANGE_TTL, headers: dict = None) -> Optional[Any]:
    now = time.time()
    if key in _cache:
        data, ts = _cache[key]
        if now - ts < ttl:
            return data
    merged_headers = {**_BROWSER_HEADERS, **(headers or {})}
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers=merged_headers,
        ) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    _cache[key] = (data, now)
                    return data
                logger.warning("HTTP %s: %s", r.status, url)
    except asyncio.TimeoutError:
        logger.error("Timeout: %s", url)
    except Exception as e:
        logger.error("Fetch error %s: %s", url, e)
    return None


# ── UPBIT ─────────────────────────────────────────────────────────────────────

async def upbit_spot() -> Set[str]:
    data = await _get("https://api.upbit.com/v1/market/all", "upbit_spot")
    if not data:
        return set()
    return {m["market"].split("-")[1].upper() for m in data if m.get("market", "").startswith("KRW-")}


# ── BITHUMB ───────────────────────────────────────────────────────────────────

async def bithumb_spot() -> Set[str]:
    data = await _get("https://api.bithumb.com/public/ticker/ALL_KRW", "bithumb_spot")
    if not data or data.get("status") != "0000":
        return set()
    return {k.upper() for k in data.get("data", {}) if k != "date"}


# ── BINANCE ───────────────────────────────────────────────────────────────────

BINANCE_QUOTE = {"USDT", "USDC", "BUSD", "BTC", "ETH", "BNB"}

async def binance_spot() -> Set[str]:
    data = await _get("https://api.binance.com/api/v3/exchangeInfo", "binance_spot")
    if not data:
        return set()
    return {
        s["baseAsset"].upper()
        for s in data.get("symbols", [])
        if s.get("status") == "TRADING" and s.get("quoteAsset") in BINANCE_QUOTE
    }


async def binance_perp() -> Set[str]:
    data = await _get("https://fapi.binance.com/fapi/v1/exchangeInfo", "binance_perp")
    if not data:
        return set()
    return {
        s["baseAsset"].upper()
        for s in data.get("symbols", [])
        if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"
    }


# ── OKX ───────────────────────────────────────────────────────────────────────

async def okx_spot() -> Set[str]:
    data = await _get(
        "https://www.okx.com/api/v5/public/instruments?instType=SPOT", "okx_spot"
    )
    if not data or data.get("code") != "0":
        return set()
    return {inst["baseCcy"].upper() for inst in data.get("data", [])}


async def okx_perp() -> Set[str]:
    data = await _get(
        "https://www.okx.com/api/v5/public/instruments?instType=SWAP", "okx_perp"
    )
    if not data or data.get("code") != "0":
        return set()
    return {
        inst["baseCcy"].upper()
        for inst in data.get("data", [])
        if inst.get("settleCcy", "").upper() in {"USDT", "USDC"}
    }


# ── BITGET ────────────────────────────────────────────────────────────────────

async def bitget_spot() -> Set[str]:
    data = await _get("https://api.bitget.com/api/v2/spot/public/symbols", "bitget_spot")
    if not data or data.get("code") != "00000":
        return set()
    return {s["baseCoin"].upper() for s in data.get("data", [])}


async def bitget_perp() -> Set[str]:
    tokens: Set[str] = set()
    for pt in ["USDT-FUTURES", "USDC-FUTURES"]:
        url = f"https://api.bitget.com/api/v2/mix/market/tickers?productType={pt}"
        data = await _get(url, f"bitget_perp_{pt}")
        if not data or data.get("code") != "00000":
            continue
        for t in data.get("data", []):
            sym = t.get("symbol", "")
            for suffix in ["USDT", "USDC", "PERP"]:
                sym = sym.replace(suffix, "")
            if sym:
                tokens.add(sym.upper())
    return tokens


# ── BYBIT ─────────────────────────────────────────────────────────────────────

async def _bybit_paginated(category: str, key_prefix: str) -> Set[str]:
    tokens: Set[str] = set()
    cursor = ""
    for _ in range(10):
        url = f"https://api.bybit.com/v5/market/instruments-info?category={category}&limit=1000"
        if cursor:
            url += f"&cursor={cursor}"
        data = await _get(url, f"{key_prefix}_{cursor or 'start'}", ttl=EXCHANGE_TTL)
        if not data or data.get("retCode") != 0:
            break
        result = data.get("result", {})
        for inst in result.get("list", []):
            if inst.get("quoteCoin", "").upper() in {"USDT", "USDC", "USD", "BTC", "ETH"}:
                tokens.add(inst["baseCoin"].upper())
        cursor = result.get("nextPageCursor", "")
        if not cursor:
            break
    return tokens


async def bybit_spot() -> Set[str]:
    return await _bybit_paginated("spot", "bybit_spot")


async def bybit_perp() -> Set[str]:
    return await _bybit_paginated("linear", "bybit_perp")


# ── COINBASE ──────────────────────────────────────────────────────────────────

COINBASE_QUOTE = {"USD", "USDT", "USDC", "EUR", "GBP", "BTC", "ETH"}

async def coinbase_spot() -> Set[str]:
    data = await _get("https://api.exchange.coinbase.com/products", "coinbase_spot")
    if not isinstance(data, list):
        return set()
    return {
        p["base_currency"].upper()
        for p in data
        if p.get("status") == "online" and p.get("quote_currency") in COINBASE_QUOTE
    }


# ── KRAKEN ────────────────────────────────────────────────────────────────────

_KRAKEN_MAP = {
    "XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XXLM": "XLM",
    "XLTC": "LTC", "XMLN": "MLN", "XREP": "REP", "XXMR": "XMR", "XZEC": "ZEC",
    "XETC": "ETC", "XXDG": "DOGE", "XICN": "ICN", "XREPV2": "REP",
}


def _norm_kraken(sym: str) -> str:
    if sym in _KRAKEN_MAP:
        return _KRAKEN_MAP[sym]
    if len(sym) == 4 and sym[0] in "XZ" and sym[1:].isalpha():
        return sym[1:]
    return sym.replace(".S", "").replace(".P", "")


KRAKEN_QUOTE = {"ZUSD", "ZEUR", "XXBT", "ZGBP", "ZCAD", "ZAUD", "USDT", "USDC"}


async def kraken_spot() -> Set[str]:
    data = await _get("https://api.kraken.com/0/public/AssetPairs", "kraken_spot")
    if not data or data.get("error"):
        return set()
    tokens: Set[str] = set()
    for _, info in data.get("result", {}).items():
        if ".d" in info.get("altname", "").lower():
            continue
        if info.get("quote") in KRAKEN_QUOTE:
            sym = _norm_kraken(info.get("base", ""))
            if sym and not sym.startswith("Z"):
                tokens.add(sym.upper())
    return tokens


async def kraken_perp() -> Set[str]:
    data = await _get(
        "https://futures.kraken.com/derivatives/api/v3/instruments", "kraken_perp"
    )
    if not data:
        return set()
    tokens: Set[str] = set()
    for inst in data.get("instruments", []):
        sym = inst.get("symbol", "")
        if not ("PF_" in sym or "PI_" in sym):
            continue
        sym = sym.replace("PF_", "").replace("PI_", "")
        for q in ["USDT", "USD", "EUR", "XBT", "GBP"]:
            if sym.endswith(q):
                sym = sym[: -len(q)]
                break
        sym = _norm_kraken(sym)
        if sym:
            tokens.add(sym.upper())
    return tokens


# ── REVOLUT ───────────────────────────────────────────────────────────────────
# Revolut is a retail crypto brokerage with no public exchange API.
# We attempt their internal endpoint and fall back to a curated static list.

_REVOLUT_STATIC = {
    "BTC", "ETH", "XRP", "LTC", "BCH", "XLM", "EOS", "TRX", "LINK", "XTZ",
    "SOL", "ADA", "DOT", "UNI", "MATIC", "DOGE", "SHIB", "AVAX", "ATOM",
    "ALGO", "NEAR", "ICP", "APT", "ARB", "OP", "SUI", "PEPE", "FLOKI",
    "BONK", "WLD", "PYTH", "JTO", "STRK", "ORDI", "SEI", "BLUR", "HBAR",
    "QNT", "SAND", "MANA", "AXS", "ENJ", "CHZ", "GALA", "IMX", "RNDR",
    "FET", "OCEAN", "AGIX", "CRV", "AAVE", "SNX", "MKR", "COMP", "YFI",
    "SUSHI", "1INCH", "FLOW", "THETA", "VET", "ZIL", "KAVA", "CELO",
    "DASH", "ZEC", "XMR", "ETC", "FIL", "LDO", "RPL", "NOT", "TON",
    "POLYX", "CFG", "FLR", "INJ", "OSMO", "TIA", "MEME", "NEIRO", "EIGEN",
    "HMSTR", "CATI", "DOGS", "NOTCOIN", "MAJOR",
}


async def revolut_spot() -> Set[str]:
    return _REVOLUT_STATIC.copy()


# ── BITVAVO ───────────────────────────────────────────────────────────────────

async def bitvavo_spot() -> Set[str]:
    data = await _get("https://api.bitvavo.com/v2/markets", "bitvavo_spot")
    if not isinstance(data, list):
        return set()
    return {
        m["market"].split("-")[0].upper()
        for m in data
        if m.get("status") == "trading" and "-" in m.get("market", "")
    }


# ── MEXC ──────────────────────────────────────────────────────────────────────

MEXC_QUOTE = {"USDT", "USDC", "BTC", "ETH"}


async def mexc_spot() -> Set[str]:
    data = await _get("https://api.mexc.com/api/v3/exchangeInfo", "mexc_spot")
    if not data:
        return set()
    return {
        s["baseAsset"].upper()
        for s in data.get("symbols", [])
        if s.get("status") == "ENABLED" and s.get("quoteAsset") in MEXC_QUOTE
    }


async def mexc_perp() -> Set[str]:
    data = await _get("https://contract.mexc.com/api/v1/contract/detail", "mexc_perp")
    if not data or data.get("code") != 200:
        return set()
    tokens: Set[str] = set()
    for c in data.get("data", []):
        sym = c.get("symbol", "")
        if "_USDT" in sym or "_USDC" in sym:
            tokens.add(sym.split("_")[0].upper())
    return tokens


# ── REGISTRY ──────────────────────────────────────────────────────────────────

EXCHANGES: Dict[str, Dict[str, Any]] = {
    "upbit":    {"name": "Upbit",    "region": "KR",     "spot": upbit_spot,    "perp": None},
    "bithumb":  {"name": "Bithumb",  "region": "KR",     "spot": bithumb_spot,  "perp": None},
    "binance":  {"name": "Binance",  "region": "Global", "spot": binance_spot,  "perp": binance_perp},
    "bitget":   {"name": "Bitget",   "region": "Global", "spot": bitget_spot,   "perp": bitget_perp},
    "bybit":    {"name": "Bybit",    "region": "Global", "spot": bybit_spot,    "perp": bybit_perp},
    "coinbase": {"name": "Coinbase", "region": "US",     "spot": coinbase_spot, "perp": None},
    "kraken":   {"name": "Kraken",   "region": "US",     "spot": kraken_spot,   "perp": kraken_perp},
    "revolut":  {"name": "Revolut",  "region": "EU",     "spot": revolut_spot,  "perp": None,
                 "data_note": "Static list (no public API)"},
    "bitvavo":  {"name": "Bitvavo",  "region": "EU",     "spot": bitvavo_spot,  "perp": None},
    "mexc":     {"name": "MEXC",     "region": "Global", "spot": mexc_spot,     "perp": mexc_perp},
}

# Tokens to always exclude (stablecoins, wrapped assets)
EXCLUDED = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "USDD", "FDUSD", "GUSD",
    "LUSD", "FRAX", "MIM", "SUSD", "HUSD", "UST", "USTC", "PYUSD", "CRVUSD",
    "GYEN", "EURS", "AGEUR", "USDK", "CUSD", "USDX", "OUSD", "DOLA",
    "WBTC", "WETH", "WBNB", "WMATIC", "WAVAX",
    "EUR", "USD", "GBP", "SGD", "AUD", "CAD", "JPY", "KRW", "HKD",
}


async def fetch_all_listings(
    selected: List[str],
    product_type: str,
) -> Dict[str, Dict]:
    """
    Returns tokens on selected exchanges but NOT on OKX.

    product_type: "spot" | "perp" | "both"

    Return shape:
        {SYMBOL: {"exchanges": [str], "listing_types": [str]}}
    """
    pts = ["spot", "perp"] if product_type == "both" else [product_type]

    # Gather OKX listings
    okx_fns = [okx_spot() if pt == "spot" else okx_perp() for pt in pts]
    okx_results = await asyncio.gather(*okx_fns, return_exceptions=True)
    okx_tokens: Set[str] = set()
    for r in okx_results:
        if isinstance(r, set):
            okx_tokens |= r

    # Gather selected exchange listings
    tasks: List[tuple] = []
    for ex in selected:
        info = EXCHANGES.get(ex)
        if not info:
            continue
        for pt in pts:
            fn = info.get(pt)
            if fn:
                tasks.append((ex, pt, fn()))

    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

    token_map: Dict[str, Dict] = {}
    for i, (ex, pt, _) in enumerate(tasks):
        r = results[i]
        if isinstance(r, Exception):
            logger.error("Error %s %s: %s", ex, pt, r)
            continue
        for sym in r:
            if sym in EXCLUDED:
                continue
            if sym not in token_map:
                token_map[sym] = {"exchanges": set(), "listing_types": set()}
            token_map[sym]["exchanges"].add(ex)
            token_map[sym]["listing_types"].add(pt)

    # Intersection: token must be listed on EVERY selected exchange
    # that actually supports the requested product type(s).
    relevant = [
        ex for ex in selected
        if any(EXCHANGES.get(ex, {}).get(pt) for pt in pts)
    ]

    missing = {}
    for sym, info in token_map.items():
        if sym in okx_tokens:
            continue
        if all(ex in info["exchanges"] for ex in relevant):
            missing[sym] = {
                "exchanges": sorted(info["exchanges"]),
                "listing_types": sorted(info["listing_types"]),
            }
    return missing
