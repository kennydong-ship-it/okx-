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


@app.get("/api/demo")
async def demo_tokens():
    """Return realistic mock data for UI preview (no live API calls needed)."""
    tokens = [
        {"symbol":"HBAR","name":"Hedera","image":"https://assets.coingecko.com/coins/images/3688/small/hbar.png","exchanges":["upbit","bithumb","binance"],"listing_types":["spot"],"volume_24h":312_450_000,"market_cap":8_200_000_000,"price":0.082,"price_change_24h":4.32,"categories":["Layer 1 (L1)","Enterprise Blockchain"],"cg_id":"hedera-hashgraph","volume_source":"CoinGecko"},
        {"symbol":"XEC","name":"eCash","image":"https://assets.coingecko.com/coins/images/16646/small/Logo_200x200.png","exchanges":["upbit","bithumb"],"listing_types":["spot"],"volume_24h":187_300_000,"market_cap":950_000_000,"price":0.0000456,"price_change_24h":-1.8,"categories":["Cryptocurrency"],"cg_id":"ecash","volume_source":"CoinGecko"},
        {"symbol":"POLYX","name":"Polymesh","image":"https://assets.coingecko.com/coins/images/23496/small/0_0.png","exchanges":["upbit","bithumb","kraken"],"listing_types":["spot"],"volume_24h":145_600_000,"market_cap":380_000_000,"price":0.31,"price_change_24h":2.15,"categories":["Security Tokens","Regulated Blockchain"],"cg_id":"polymesh","volume_source":"CoinGecko"},
        {"symbol":"STEEM","name":"Steem","image":"https://assets.coingecko.com/coins/images/585/small/steem.png","exchanges":["upbit","bithumb","binance"],"listing_types":["spot"],"volume_24h":98_700_000,"market_cap":220_000_000,"price":0.24,"price_change_24h":-3.4,"categories":["Content Creation","Social"],"cg_id":"steem","volume_source":"CoinGecko"},
        {"symbol":"MVL","name":"MVL","image":"https://assets.coingecko.com/coins/images/5164/small/MVL.png","exchanges":["upbit","bithumb"],"listing_types":["spot"],"volume_24h":87_200_000,"market_cap":110_000_000,"price":0.0067,"price_change_24h":6.7,"categories":["Transportation","Real World Assets (RWA)"],"cg_id":"mass-vehicle-ledger","volume_source":"CoinGecko"},
        {"symbol":"BORA","name":"BORA","image":"https://assets.coingecko.com/coins/images/7444/small/BORA.png","exchanges":["upbit","bithumb"],"listing_types":["spot"],"volume_24h":76_500_000,"market_cap":195_000_000,"price":0.21,"price_change_24h":1.2,"categories":["Gaming","NFT"],"cg_id":"bora","volume_source":"CoinGecko"},
        {"symbol":"CTC","name":"Creditcoin","image":"https://assets.coingecko.com/coins/images/16559/small/creditcoin.jpeg","exchanges":["upbit","bithumb","bybit"],"listing_types":["spot","perp"],"volume_24h":65_400_000,"market_cap":260_000_000,"price":0.88,"price_change_24h":-0.9,"categories":["DeFi","Lending/Borrowing"],"cg_id":"creditcoin-2","volume_source":"CoinGecko"},
        {"symbol":"WAXP","name":"WAX","image":"https://assets.coingecko.com/coins/images/1372/small/WAX_Coin_Tickers_P_512px.png","exchanges":["upbit","binance","kraken"],"listing_types":["spot"],"volume_24h":58_900_000,"market_cap":430_000_000,"price":0.054,"price_change_24h":3.1,"categories":["Gaming","NFT","Metaverse"],"cg_id":"wax","volume_source":"CoinGecko"},
        {"symbol":"ORCA","name":"Orca","image":"https://assets.coingecko.com/coins/images/17547/small/Orca_Logo.png","exchanges":["coinbase","kraken","bybit"],"listing_types":["spot","perp"],"volume_24h":52_100_000,"market_cap":340_000_000,"price":3.41,"price_change_24h":5.8,"categories":["Decentralized Exchange (DEX)","Solana Ecosystem"],"cg_id":"orca","volume_source":"CoinGecko"},
        {"symbol":"BOME","name":"Book of Meme","image":"https://assets.coingecko.com/coins/images/36347/small/bome.png","exchanges":["binance","bybit","mexc"],"listing_types":["spot","perp"],"volume_24h":487_000_000,"market_cap":820_000_000,"price":0.0087,"price_change_24h":12.4,"categories":["Meme","Solana Ecosystem"],"cg_id":"book-of-meme","volume_source":"CoinGecko"},
        {"symbol":"NOT","name":"Notcoin","image":"https://assets.coingecko.com/coins/images/36135/small/notcoin.png","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":423_000_000,"market_cap":1_650_000_000,"price":0.0072,"price_change_24h":8.9,"categories":["TON Ecosystem","Gaming","Meme"],"cg_id":"notcoin","volume_source":"CoinGecko"},
        {"symbol":"EIGEN","name":"EigenLayer","image":"https://assets.coingecko.com/coins/images/33119/small/eigen.png","exchanges":["binance","coinbase","kraken","bybit"],"listing_types":["spot","perp"],"volume_24h":198_000_000,"market_cap":2_100_000_000,"price":3.21,"price_change_24h":-2.3,"categories":["Restaking","Ethereum Ecosystem","DeFi"],"cg_id":"eigenlayer","volume_source":"CoinGecko"},
        {"symbol":"SCR","name":"Scroll","image":"https://assets.coingecko.com/coins/images/34963/small/scroll.png","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":176_000_000,"market_cap":890_000_000,"price":0.89,"price_change_24h":-4.1,"categories":["Layer 2 (L2)","Zero Knowledge (ZK)","Ethereum Ecosystem"],"cg_id":"scroll","volume_source":"CoinGecko"},
        {"symbol":"CATI","name":"Catizen","image":"https://assets.coingecko.com/coins/images/39273/small/catizen.png","exchanges":["binance","bybit","bitget"],"listing_types":["spot","perp"],"volume_24h":154_000_000,"market_cap":560_000_000,"price":0.37,"price_change_24h":7.6,"categories":["TON Ecosystem","Gaming","Meme"],"cg_id":"catizen","volume_source":"CoinGecko"},
        {"symbol":"DOGS","name":"Dogs","image":"https://assets.coingecko.com/coins/images/39332/small/dogs.png","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":132_000_000,"market_cap":480_000_000,"price":0.00048,"price_change_24h":3.2,"categories":["TON Ecosystem","Meme"],"cg_id":"dogs-2","volume_source":"CoinGecko"},
        {"symbol":"HMSTR","name":"Hamster Kombat","image":"https://assets.coingecko.com/coins/images/39102/small/hamster-removebg-preview.png","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":118_000_000,"market_cap":720_000_000,"price":0.0048,"price_change_24h":-1.5,"categories":["TON Ecosystem","Gaming"],"cg_id":"hamster-kombat","volume_source":"CoinGecko"},
        {"symbol":"NEIRO","name":"First Neiro On Ethereum","image":"https://assets.coingecko.com/coins/images/39392/small/neiro.png","exchanges":["binance","bybit","mexc"],"listing_types":["spot","perp"],"volume_24h":289_000_000,"market_cap":610_000_000,"price":0.00062,"price_change_24h":15.3,"categories":["Meme","Ethereum Ecosystem"],"cg_id":"neiro-on-eth","volume_source":"CoinGecko"},
        {"symbol":"BLUR","name":"Blur","image":"https://assets.coingecko.com/coins/images/28453/small/blur.png","exchanges":["coinbase","kraken","bybit","bitget"],"listing_types":["spot","perp"],"volume_24h":95_000_000,"market_cap":680_000_000,"price":0.21,"price_change_24h":-0.8,"categories":["NFT","Marketplace","Ethereum Ecosystem"],"cg_id":"blur","volume_source":"CoinGecko"},
        {"symbol":"TNSR","name":"Tensor","image":"https://assets.coingecko.com/coins/images/35399/small/tensor.png","exchanges":["coinbase","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":87_000_000,"market_cap":310_000_000,"price":0.52,"price_change_24h":9.1,"categories":["NFT","Marketplace","Solana Ecosystem"],"cg_id":"tensor","volume_source":"CoinGecko"},
        {"symbol":"AEVO","name":"Aevo","image":"https://assets.coingecko.com/coins/images/34617/small/aevo.png","exchanges":["binance","coinbase","bybit","bitget"],"listing_types":["spot","perp"],"volume_24h":76_500_000,"market_cap":290_000_000,"price":0.82,"price_change_24h":-3.7,"categories":["Decentralized Exchange (DEX)","Options","DeFi"],"cg_id":"aevo-exchange","volume_source":"CoinGecko"},
        {"symbol":"ZETA","name":"ZetaChain","image":"https://assets.coingecko.com/coins/images/26718/small/zetachain.png","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":68_000_000,"market_cap":440_000_000,"price":0.64,"price_change_24h":2.4,"categories":["Layer 1 (L1)","Interoperability","Cross-Chain"],"cg_id":"zetachain","volume_source":"CoinGecko"},
        {"symbol":"ALT","name":"AltLayer","image":"https://assets.coingecko.com/coins/images/34601/small/altlayer.jpeg","exchanges":["binance","bybit","bitget","mexc"],"listing_types":["spot","perp"],"volume_24h":62_000_000,"market_cap":380_000_000,"price":0.21,"price_change_24h":-5.2,"categories":["Layer 2 (L2)","Restaking","Ethereum Ecosystem"],"cg_id":"altlayer","volume_source":"CoinGecko"},
        {"symbol":"MANTA","name":"Manta Network","image":"https://assets.coingecko.com/coins/images/34289/small/manta.png","exchanges":["binance","bybit","kraken","mexc"],"listing_types":["spot","perp"],"volume_24h":58_000_000,"market_cap":490_000_000,"price":0.94,"price_change_24h":1.8,"categories":["Layer 2 (L2)","Zero Knowledge (ZK)","Privacy"],"cg_id":"manta-network","volume_source":"CoinGecko"},
        {"symbol":"ACE","name":"Fusionist","image":"https://assets.coingecko.com/coins/images/33952/small/ace.png","exchanges":["binance","bybit","bitget"],"listing_types":["spot","perp"],"volume_24h":43_000_000,"market_cap":210_000_000,"price":2.14,"price_change_24h":4.6,"categories":["Gaming","Metaverse","NFT"],"cg_id":"fusionist","volume_source":"CoinGecko"},
        {"symbol":"POLS","name":"Polkastarter","image":"https://assets.coingecko.com/coins/images/12648/small/polkastarter.png","exchanges":["bitvavo","kraken","coinbase"],"listing_types":["spot"],"volume_24h":38_500_000,"market_cap":145_000_000,"price":0.98,"price_change_24h":-2.1,"categories":["Launchpad","DeFi","Polkadot Ecosystem"],"cg_id":"polkastarter","volume_source":"CoinGecko"},
        {"symbol":"GFI","name":"Goldfinch","image":"https://assets.coingecko.com/coins/images/19040/small/GFI_logo.png","exchanges":["coinbase","kraken"],"listing_types":["spot"],"volume_24h":12_300_000,"market_cap":87_000_000,"price":0.94,"price_change_24h":-0.4,"categories":["DeFi","Lending/Borrowing","Real World Assets (RWA)"],"cg_id":"goldfinch","volume_source":"CoinGecko"},
        {"symbol":"AUCTION","name":"Bounce Token","image":"https://assets.coingecko.com/coins/images/13860/small/1_KtgpRIJzuwfHe0Rl0avP_g.jpeg","exchanges":["bitvavo","kraken","bybit"],"listing_types":["spot"],"volume_24h":9_800_000,"market_cap":62_000_000,"price":15.4,"price_change_24h":3.8,"categories":["DeFi","NFT","Auction"],"cg_id":"auction","volume_source":"CoinGecko"},
    ]
    tokens.sort(key=lambda x: x["volume_24h"], reverse=True)
    return {
        "tokens": tokens,
        "total": len(tokens),
        "product_type": "spot+perp",
        "exchanges": ["upbit","bithumb","binance","bybit","bitget","coinbase","kraken","bitvavo","mexc"],
        "demo": True,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}
