"""Build data/universe/universe.json: the S&P 500 (from data/universe/sp500.json) plus popular names outside it.

Each entry: ticker, name, sector, industry, cik, index, slug. Run when the index changes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketdata import DATA, sec_ticker_map  # noqa: E402

# Popular names outside the S&P 500 that readers ask about. (ticker, display name, sector, industry)
EXTRAS = [
    ("TSM", "Taiwan Semiconductor", "Information Technology", "Semiconductors"),
    ("ASML", "ASML", "Information Technology", "Semiconductor Equipment"),
    ("ARM", "Arm Holdings", "Information Technology", "Semiconductors"),
    ("MRVL", "Marvell Technology", "Information Technology", "Semiconductors"),
    ("ALAB", "Astera Labs", "Information Technology", "Semiconductors"),
    ("CRDO", "Credo Technology", "Information Technology", "Semiconductors"),
    ("COHR", "Coherent", "Information Technology", "Electronic Components"),
    ("LITE", "Lumentum", "Information Technology", "Communications Equipment"),
    ("CLS", "Celestica", "Information Technology", "Electronic Manufacturing Services"),
    ("CRWV", "CoreWeave", "Information Technology", "Internet Services & Infrastructure"),
    ("NBIS", "Nebius Group", "Information Technology", "Internet Services & Infrastructure"),
    ("SNOW", "Snowflake", "Information Technology", "Application Software"),
    ("NET", "Cloudflare", "Information Technology", "Internet Services & Infrastructure"),
    ("MDB", "MongoDB", "Information Technology", "Application Software"),
    ("ZS", "Zscaler", "Information Technology", "Systems Software"),
    ("TEAM", "Atlassian", "Information Technology", "Application Software"),
    ("SHOP", "Shopify", "Information Technology", "Internet Services & Infrastructure"),
    ("PATH", "UiPath", "Information Technology", "Application Software"),
    ("AI", "C3.ai", "Information Technology", "Application Software"),
    ("IONQ", "IonQ", "Information Technology", "Computer Hardware"),
    ("RGTI", "Rigetti Computing", "Information Technology", "Computer Hardware"),
    ("QBTS", "D-Wave Quantum", "Information Technology", "Computer Hardware"),
    ("SOUN", "SoundHound AI", "Information Technology", "Application Software"),
    ("MSTR", "Strategy", "Information Technology", "Application Software"),
    ("FIG", "Figma", "Information Technology", "Application Software"),
    ("RBRK", "Rubrik", "Information Technology", "Systems Software"),
    ("SAP", "SAP", "Information Technology", "Application Software"),
    ("SONY", "Sony Group", "Consumer Discretionary", "Consumer Electronics"),
    ("SPOT", "Spotify", "Communication Services", "Movies & Entertainment"),
    ("RDDT", "Reddit", "Communication Services", "Interactive Media & Services"),
    ("SNAP", "Snap", "Communication Services", "Interactive Media & Services"),
    ("PINS", "Pinterest", "Communication Services", "Interactive Media & Services"),
    ("ROKU", "Roku", "Communication Services", "Movies & Entertainment"),
    ("BIDU", "Baidu", "Communication Services", "Interactive Media & Services"),
    ("BABA", "Alibaba", "Consumer Discretionary", "Broadline Retail"),
    ("PDD", "PDD Holdings", "Consumer Discretionary", "Broadline Retail"),
    ("JD", "JD.com", "Consumer Discretionary", "Broadline Retail"),
    ("MELI", "MercadoLibre", "Consumer Discretionary", "Broadline Retail"),
    ("SE", "Sea Limited", "Consumer Discretionary", "Broadline Retail"),
    ("CPNG", "Coupang", "Consumer Discretionary", "Broadline Retail"),
    ("NIO", "NIO", "Consumer Discretionary", "Automobile Manufacturers"),
    ("RIVN", "Rivian", "Consumer Discretionary", "Automobile Manufacturers"),
    ("LCID", "Lucid Group", "Consumer Discretionary", "Automobile Manufacturers"),
    ("TM", "Toyota", "Consumer Discretionary", "Automobile Manufacturers"),
    ("CAVA", "Cava Group", "Consumer Discretionary", "Restaurants"),
    ("ONON", "On Holding", "Consumer Discretionary", "Footwear"),
    ("BIRK", "Birkenstock", "Consumer Discretionary", "Footwear"),
    ("DUOL", "Duolingo", "Consumer Discretionary", "Education Services"),
    ("DKNG", "DraftKings", "Consumer Discretionary", "Casinos & Gaming"),
    ("CHWY", "Chewy", "Consumer Discretionary", "Specialty Retail"),
    ("ETSY", "Etsy", "Consumer Discretionary", "Broadline Retail"),
    ("LYFT", "Lyft", "Industrials", "Passenger Ground Transportation"),
    ("GME", "GameStop", "Consumer Discretionary", "Specialty Retail"),
    ("CELH", "Celsius Holdings", "Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    ("HIMS", "Hims & Hers Health", "Health Care", "Health Care Services"),
    ("NVO", "Novo Nordisk", "Health Care", "Pharmaceuticals"),
    ("AZN", "AstraZeneca", "Health Care", "Pharmaceuticals"),
    ("NVS", "Novartis", "Health Care", "Pharmaceuticals"),
    ("TEM", "Tempus AI", "Health Care", "Health Care Technology"),
    ("SOFI", "SoFi Technologies", "Financials", "Consumer Finance"),
    ("AFRM", "Affirm", "Financials", "Transaction & Payment Processing Services"),
    ("UPST", "Upstart", "Financials", "Consumer Finance"),
    ("NU", "Nu Holdings", "Financials", "Diversified Banks"),
    ("CRCL", "Circle Internet Group", "Financials", "Transaction & Payment Processing Services"),
    ("TOST", "Toast", "Financials", "Transaction & Payment Processing Services"),
    ("HSBC", "HSBC", "Financials", "Diversified Banks"),
    ("UBS", "UBS", "Financials", "Diversified Capital Markets"),
    ("RKLB", "Rocket Lab", "Industrials", "Aerospace & Defense"),
    ("ASTS", "AST SpaceMobile", "Communication Services", "Alternative Carriers"),
    ("ACHR", "Archer Aviation", "Industrials", "Aerospace & Defense"),
    ("JOBY", "Joby Aviation", "Industrials", "Passenger Airlines"),
    ("OKLO", "Oklo", "Utilities", "Electric Utilities"),
    ("SMR", "NuScale Power", "Industrials", "Heavy Electrical Equipment"),
    ("CCJ", "Cameco", "Energy", "Coal & Consumable Fuels"),
    ("LEU", "Centrus Energy", "Energy", "Coal & Consumable Fuels"),
    ("TLN", "Talen Energy", "Utilities", "Independent Power Producers & Energy Traders"),
    ("SHEL", "Shell", "Energy", "Integrated Oil & Gas"),
    ("BP", "BP", "Energy", "Integrated Oil & Gas"),
    ("RIO", "Rio Tinto", "Materials", "Diversified Metals & Mining"),
    ("BHP", "BHP Group", "Materials", "Diversified Metals & Mining"),
    ("MP", "MP Materials", "Materials", "Diversified Metals & Mining"),
    ("AEM", "Agnico Eagle Mines", "Materials", "Gold"),
    ("GRAB", "Grab Holdings", "Industrials", "Passenger Ground Transportation"),
]

# Shorter names for the S&P 500 entries whose official names read badly in headlines.
SHORT = {
    "GOOGL": "Alphabet", "GOOG": "Alphabet (Class C)", "META": "Meta", "BRK.B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase", "UNH": "UnitedHealth", "PG": "Procter & Gamble", "AMZN": "Amazon",
    "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft", "TSLA": "Tesla", "AVGO": "Broadcom",
    "AMD": "AMD", "INTC": "Intel", "IBM": "IBM", "NFLX": "Netflix", "COST": "Costco",
    "WMT": "Walmart", "XOM": "Exxon Mobil", "CVX": "Chevron", "LLY": "Eli Lilly", "V": "Visa",
    "MA": "Mastercard", "HD": "Home Depot", "KO": "Coca-Cola", "PEP": "PepsiCo", "BAC": "Bank of America",
    "WFC": "Wells Fargo", "GS": "Goldman Sachs", "MS": "Morgan Stanley", "C": "Citigroup",
}


def clean_name(n: str) -> str:
    n = n.replace(" & Co.", "").replace(" (The)", "").strip()
    n = re.sub(r",? (Inc\.?|Incorporated|Corporation|Corp\.?|plc|PLC|Co\.|Company|Ltd\.?|Limited|N\.V\.|S\.A\.|L\.P\.|SE|AG)$", "", n.strip())
    n = re.sub(r",? (Inc\.?|Corporation|Corp\.?|plc|Co\.)$", "", n)
    n = re.sub(r"^The ", "", n)
    return n.replace(" & Co.", "").strip()


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main() -> None:
    sp = json.loads((DATA / "universe" / "sp500.json").read_text())
    sec = sec_ticker_map()
    out = []
    seen = set()
    for r in sp:
        t = r["ticker"]
        out.append({
            "ticker": t, "name": SHORT.get(t, clean_name(r["name"])), "legal_name": r["name"], "sector": r["sector"],
            "industry": r["industry"], "cik": r["cik"], "hq": r["hq"], "founded": r["founded"],
            "index": ["S&P 500"],
        })
        seen.add(t)
    missing = []
    for t, name, sector, industry in EXTRAS:
        if t in seen:
            continue
        s = sec.get(t)
        if not s:
            missing.append(t)
            continue
        out.append({"ticker": t, "name": name, "legal_name": s["name"], "sector": sector, "industry": industry,
                    "cik": s["cik"], "hq": "", "founded": "", "index": []})
        seen.add(t)
    out.sort(key=lambda u: u["ticker"])
    (DATA / "universe" / "universe.json").write_text(json.dumps(out, indent=0))
    print(len(out), "tickers;", "not at SEC:", missing)


if __name__ == "__main__":
    main()
