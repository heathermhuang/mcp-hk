"""First-class discovery of connected query services; never a government mirror."""

import unicodedata

from .sources import SOURCES, available_packs

DISPLAY = {
    "addresses": (
        "Hong Kong address lookup",
        "香港地址查詢",
        "Find a building or street address, then explore its neighbourhood.",
        "搜尋大廈或街道地址，再查看附近資料。",
        "address addresses ALS 地址 大廈 街道 neighbourhood",
        "/demo",
        "Find an address",
        "查詢地址",
    ),
    "restaurants": (
        "Licensed restaurants",
        "持牌食肆",
        "Find licensed restaurants near a Hong Kong address, with licence and source details.",
        "先選擇香港地址，查看附近持牌食肆、牌照及來源。",
        "restaurants food FEHD 食肆 餐廳 餐厅 飲食 牌照 附近",
        "/demo",
        "Find nearby restaurants",
        "尋找附近食肆",
    ),
    "population": (
        "District population and density",
        "地區人口及密度",
        "Look up an address to see its district population, density and statistical reference year.",
        "查詢地址所屬地區的人口、密度及統計參考年份。",
        "population district statistics census 人口 地區 地区 統計 统计 密度",
        "/demo",
        "Explore district statistics",
        "查看地區統計",
    ),
    "seehouse": (
        "SeeHouse Hong Kong buildings and property listings",
        "SeeHouse 睇樓：香港大廈及樓盤資料",
        "Search buildings, read source-linked sale and rental listings, and inspect observed asking-price changes and coverage.",
        "搜尋大廈、查看附原始來源的買賣及租盤，以及叫價變動紀錄和資料覆蓋範圍。",
        "seehouse see.house seehouse.hk 睇樓 睇楼 樓盤 楼盘 地產 地产 物業 物业 大廈 大厦 買樓 买楼 租樓 租楼 property properties housing buildings sale rental asking prices",
        "/properties",
        "Search buildings and listings",
        "搜尋大廈及樓盤",
    ),
    "platehk": (
        "Plate.hk vehicle registration auction history",
        "Plate.hk 車牌拍賣紀錄",
        "Search historical Hong Kong plate auction results and original publications. Historical prices, not current valuations.",
        "搜尋香港車牌歷史拍賣結果及原始文件；成交紀錄並非現時估值。",
        "plate.hk plate hk platehk plates vehicle registration auctions auction history 車牌 车牌 拍賣 拍卖 成交 牌價 牌价",
        "/plates",
        "Search auction records",
        "搜尋拍賣紀錄",
    ),
}


DISPLAY["enigma"] = (
    "Hong Kong archival organisations and relationships",
    "香港機構及關係歷史資料",
    "Search David Webb's original Enigma archive: organisation names, officer appointments and SFC relationships. Historical observations, not current verification.",
    "搜尋 David Webb 原始 Enigma 檔案中的機構名稱、職位及證監會關係；歷史紀錄並非現況核實。",
    "enigma webb companies company organisations officers licence SFC archive 公司 機構 董事 牌照 歷史",
    "/companies",
    "Search archival organisations",
    "搜尋機構歷史資料",
)


def entries():
    result = []
    for pack in available_packs():
        key = pack["id"]
        title, zh, description, description_zh, aliases, url, action, action_zh = (
            DISPLAY[key]
        )
        result.append(
            {
                **pack,
                "id": "mcp:" + key,
                "packId": key,
                "title": title,
                "titleZhHant": zh,
                "description": description,
                "descriptionZhHant": description_zh,
                "keywords": aliases,
                "entryKind": "connected_service",
                "catalogue": "mcp.hk",
                "capability": "connected_query",
                "sourceUrl": SOURCES[key]["sourceUrl"],
                "attribution": SOURCES[key]["attribution"],
                "action": {"url": url, "label": action, "labelZhHant": action_zh},
                "access": {
                    "http": pack["http"],
                    "tools": pack["tools"],
                    "scope": "Connected query interface; source freshness is checked separately.",
                },
            }
        )
    return result


def normalise(text):
    return unicodedata.normalize("NFKC", text).casefold().strip()


def matching(q):
    terms = normalise(q).split()
    return [
        entry
        for entry in entries()
        if all(
            t
            in normalise(
                " ".join(
                    str(entry.get(k, ""))
                    for k in (
                        "id",
                        "title",
                        "titleZhHant",
                        "provider",
                        "description",
                        "descriptionZhHant",
                        "keywords",
                    )
                )
            )
            for t in terms
        )
    ]


def get(dataset_id):
    return next((e for e in entries() if e["id"] == dataset_id), None)
