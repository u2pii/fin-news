# -*- coding: utf-8 -*-
"""财经日历 + 新闻抓取 → data.json
   日历：Nasdaq（有未来数据）
   新闻：Google News 中文（GitHub 上可访问）→ WSJ / CoinTelegraph 兜底
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.json")
TZ = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept": "*/*"}


def get(url, timeout=25, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(6 if getattr(e, "code", None) == 429 else 2 * (i + 1))
    raise last


# ============================================================
# 事件中文名 + 影响
# ============================================================
# 关键词: (中文名, 重要性, 高于预期, 低于预期)
EV = {
    "fomc": ("美联储议息会议", "极高", "偏鹰→美元↑ 美股↓ 黄金↓ BTC↓", "偏鸽→美元↓ 美股↑ 黄金↑ BTC↑"),
    "federal funds rate": ("美联储利率决议", "极高", "加息→美元↑ 风险资产↓", "降息→美元↓ 风险资产↑"),
    "fed chair": ("美联储主席讲话", "极高", "偏鹰→美元↑ 风险资产↓", "偏鸽→美元↓ 风险资产↑"),
    "fomc member": ("美联储官员讲话", "中", "偏鹰→美元↑", "偏鸽→美元↓"),
    "fed": ("美联储", "高", "偏鹰→美元↑", "偏鸽→美元↓"),
    "interest rate decision": ("利率决议", "极高", "加息→本币↑ 股市↓", "降息→本币↓ 股市↑"),
    "rate statement": ("利率声明", "极高", "偏鹰→本币↑", "偏鸽→本币↓"),
    "monetary policy statement": ("货币政策声明", "极高", "收紧→本币↑", "宽松→本币↓"),
    "monetary policy": ("货币政策", "高", "收紧→本币↑", "宽松→本币↓"),
    "cpi": ("消费者物价指数 CPI", "极高", "通胀高→加息预期↑ 美元↑ 美股↓ 黄金↓ BTC↓", "通胀低→降息预期↑ 美元↓ 风险资产↑"),
    "core cpi": ("核心 CPI", "极高", "核心通胀高→降息更难 风险资产↓", "核心通胀低→降息预期↑ 风险资产↑"),
    "core inflation": ("核心通胀", "极高", "通胀高→紧缩预期", "通胀低→宽松预期"),
    "ppi": ("生产者物价指数 PPI", "中", "高于预期→通胀压力↑ 债券收益率↑", "低于预期→通胀压力↓"),
    "non-farm": ("非农就业报告", "极高", "就业强→美元↑ 降息推迟 美股↓ BTC↓", "就业弱→降息预期↑ 美元↓ 风险资产↑"),
    "nonfarm": ("非农就业报告", "极高", "就业强→美元↑ 降息推迟 美股↓ BTC↓", "就业弱→降息预期↑ 美元↓ 风险资产↑"),
    "payrolls": ("就业人数", "高", "强→美元↑", "弱→美元↓"),
    "unemployment rate": ("失业率", "高", "失业率升→降息预期↑ 债券↑", "失业率降→美元↑"),
    "unemployment claims": ("失业金申请", "中", "申领增多→就业走弱 降息预期↑", "申领减少→就业强"),
    "jobless claims": ("初请失业金", "中", "增多→降息预期↑", "减少→就业强"),
    "average hourly earnings": ("平均时薪", "高", "薪资涨→通胀压力↑ 美元↑", "薪资降→通胀压力↓"),
    "gdp": ("GDP 增速", "高", "增长强→美元↑ 股市↑", "增长弱→降息预期↑ 股市↓"),
    "retail sales": ("零售销售", "高", "消费强→美元↑", "消费弱→衰退担忧"),
    "pmi": ("PMI 采购经理人指数", "高", "扩张→风险资产↑", "收缩→风险资产↓"),
    "ism manufacturing": ("ISM 制造业", "高", "扩张→美元↑ 工业品↑", "收缩→避险↑"),
    "ism services": ("ISM 服务业", "中", "扩张→经济强", "收缩→衰退担忧"),
    "manufacturing pmi": ("制造业 PMI", "高", "扩张→风险资产↑", "收缩→风险资产↓"),
    "services pmi": ("服务业 PMI", "中", "扩张→经济强", "收缩→衰退担忧"),
    "trade balance": ("贸易帐", "低", "顺差扩大→本币↑", "逆差扩大→本币↓"),
    "exports": ("出口", "低", "增长→本币↑", "下滑→本币↓"),
    "imports": ("进口", "低", "增长→内需强", "下滑→内需弱"),
    "industrial production": ("工业生产", "中", "增长→经济强", "下滑→经济弱"),
    "consumer confidence": ("消费者信心", "中", "强→消费↑", "弱→消费↓"),
    "business confidence": ("企业信心", "低", "强→投资↑", "弱→投资↓"),
    "durable goods": ("耐用品订单", "低", "强→制造业强", "弱→制造业弱"),
    "building permits": ("营建许可", "低", "强→地产强", "弱→地产弱"),
    "housing starts": ("新屋开工", "低", "强→地产强", "弱→地产弱"),
    "crude oil inventories": ("原油库存", "中", "库存增→油价↓", "库存减→油价↑"),
    "eia": ("EIA 能源库存", "中", "库存增→油价↓", "库存减→油价↑"),
    "opec": ("OPEC 会议", "高", "减产→油价↑", "增产→油价↓"),
    "treasury": ("国债拍卖", "中", "需求弱→收益率↑ 成长股↓", "需求强→收益率↓ 成长股↑"),
    "bank holiday": ("银行假日", "休市", "市场休市", "市场休市"),
    "holiday": ("休市日", "休市", "流动性低", "流动性低"),
    "adp": ("ADP 就业", "中", "强→非农预期↑", "弱→非农预期↓"),
    "current account": ("经常帐", "低", "—", "—"),
    "budget balance": ("财政收支", "低", "—", "—"),
    "inflation": ("通胀", "极高", "通胀高→紧缩预期 风险资产↓", "通胀低→宽松预期 风险资产↑"),
    "employment": ("就业", "中", "强→美元↑", "弱→美元↓"),
    "wages": ("工资", "中", "涨→通胀压力", "降→通胀缓解"),
    "zEW": ("ZEW 经济景气", "低", "高→欧元↑", "低→欧元↓"),
    "ifo": ("IFO 商业景气", "低", "高→欧元↑", "低→欧元↓"),
    "retail": ("零售", "中", "强→消费↑", "弱→消费↓"),
    "price index": ("价格指数", "中", "高→通胀压力", "低→通胀缓解"),
    "pce": ("PCE 物价指数", "极高", "高→美联储更鹰 风险资产↓", "低→降息预期↑ 风险资产↑"),
    "services": ("服务业", "中", "强→经济好", "弱→经济差"),
    "manufacturing": ("制造业", "中", "强→经济好", "弱→经济差"),
    "confidence": ("信心指数", "低", "强→乐观", "弱→悲观"),
    "balance": ("余额", "低", "—", "—"),
}

COUNTRY = {
    "United States": "美国", "China": "中国", "Euro Zone": "欧元区", "Eurozone": "欧元区",
    "Japan": "日本", "United Kingdom": "英国", "Germany": "德国", "France": "法国",
    "Australia": "澳大利亚", "Canada": "加拿大", "Switzerland": "瑞士",
    "New Zealand": "新西兰", "Hong Kong": "中国香港", "Singapore": "新加坡",
    "South Korea": "韩国", "India": "印度", "Brazil": "巴西", "Mexico": "墨西哥",
    "Russia": "俄罗斯", "Italy": "意大利", "Spain": "西班牙", "Netherlands": "荷兰",
    "Sweden": "瑞典", "Norway": "挪威", "Denmark": "丹麦", "Poland": "波兰",
    "Turkey": "土耳其", "South Africa": "南非", "Indonesia": "印尼",
    "Malaysia": "马来西亚", "Thailand": "泰国", "Philippines": "菲律宾",
    "Vietnam": "越南", "Saudi Arabia": "沙特", "Israel": "以色列",
    "Ireland": "爱尔兰", "Portugal": "葡萄牙", "Greece": "希腊", "Austria": "奥地利",
    "Belgium": "比利时", "Finland": "芬兰", "Czech Republic": "捷克", "Hungary": "匈牙利",
    "Argentina": "阿根廷", "Chile": "智利", "Colombia": "哥伦比亚", "Peru": "秘鲁",
}

LEVEL_ORDER = {"极高": 0, "高": 1, "中": 2, "低": 3, "休市": 4}


def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = (s.replace("&nbsp;", "").replace("&amp;", "&").replace("&#039;", "'")
         .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    return s.strip()


def translate_event(name):
    low = (name or "").lower()
    for kw in sorted(EV, key=len, reverse=True):
        if kw.lower() in low:
            cn, level, up, dn = EV[kw]
            return cn, level, up, dn
    return name, "中", "公布值高于预期 → 关注短线波动", "公布值低于预期 → 关注短线波动"


# ============================================================
# 一、日历：Nasdaq 未来 N 天
# ============================================================
def fetch_nasdaq_calendar(days=8):
    events = []
    now = datetime.now(TZ)
    for k in range(-30, days + 1):
        d = (now + timedelta(days=k)).strftime("%Y-%m-%d")
        url = f"https://api.nasdaq.com/api/calendar/economicevents?date={d}"
        try:
            raw = get(url, timeout=20, retries=2)
            j = json.loads(raw.decode("utf-8", "ignore"))
            rows = (j.get("data") or {}).get("rows") or []
        except Exception as e:
            print(f"  {d} 失败 {str(e)[:40]}", file=sys.stderr)
            time.sleep(1)
            continue
        for r in rows:
            nm = clean(r.get("eventName"))
            if not nm:
                continue
            gmt = (r.get("gmt") or "").strip()
            try:
                hh, mm = gmt.split(":")
                dt = datetime.strptime(d, "%Y-%m-%d").replace(
                    hour=int(hh), minute=int(mm), tzinfo=timezone.utc).astimezone(TZ)
            except Exception:
                dt = datetime.strptime(d, "%Y-%m-%d").replace(hour=12, tzinfo=TZ)
            cn, level, up, dn = translate_event(nm)
            country = COUNTRY.get(clean(r.get("country")), clean(r.get("country")))
            events.append({
                "name_en": nm, "name": cn, "level": level,
                "up": up, "dn": dn,
                "country": country,
                "date": dt.strftime("%Y-%m-%d"),
                "weekday": "周" + "一二三四五六日"[dt.weekday()],
                "time": dt.strftime("%H:%M"),
                "ts": dt.timestamp(),
                "forecast": clean(r.get("consensus")),
                "previous": clean(r.get("previous")),
                "actual": clean(r.get("actual")),
            })
        time.sleep(0.5)

    # 去重
    seen, uniq = set(), []
    for e in events:
        k = (e["name_en"], e["date"], e["time"], e["country"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    uniq.sort(key=lambda x: (x["ts"], LEVEL_ORDER.get(x["level"], 9)))
    return uniq


# ============================================================
# 二、新闻
# ============================================================
def parse_rss(raw, source, lang):
    items = []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return items
    for it in root.iter("item"):
        def t(tag):
            el = it.find(tag)
            return (el.text or "") if el is not None else ""
        title = clean(t("title"))
        link = (t("link") or "").strip()
        if not title or not link:
            continue
        pub = t("pubDate") or t("{http://purl.org/dc/elements/1.1/}date")
        ts = None
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
            try:
                dd = datetime.strptime(pub.strip(), fmt)
                if dd.tzinfo is None:
                    dd = dd.replace(tzinfo=timezone.utc)
                ts = dd.timestamp()
                break
            except Exception:
                continue
        items.append({"title": title, "link": link, "source": source,
                      "lang": lang, "ts": ts or time.time()})
    return items


SOURCES = [
    ("Google 新闻·美联储", "https://news.google.com/rss/search?q=%E7%BE%8E%E8%81%94%E5%82%A8&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("Google 新闻·利率", "https://news.google.com/rss/search?q=%E5%8A%A0%E6%81%AF+OR+%E9%99%8D%E6%81%AF&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("Google 新闻·通胀", "https://news.google.com/rss/search?q=%E9%80%9A%E8%83%80+OR+CPI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("Google 新闻·A股", "https://news.google.com/rss/search?q=A%E8%82%A1+OR+%E5%A4%AE%E8%A1%8C&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("Google 新闻·加密", "https://news.google.com/rss/search?q=%E6%AF%94%E7%89%B9%E5%B8%81+OR+%E5%8A%A0%E5%AF%86%E8%B4%A7%E5%B8%81&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("Google 新闻·全球市场", "https://news.google.com/rss/search?q=%E7%BE%8E%E8%82%A1+OR+%E9%BB%84%E9%87%91+OR+%E6%B2%B9%E4%BB%B7&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "zh"),
    ("华尔街日报", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "en"),
    ("CoinTelegraph", "https://cointelegraph.com/rss", "en"),
]


def fetch_news():
    out = []
    for name, url, lang in SOURCES:
        try:
            items = parse_rss(get(url, timeout=20, retries=2), name, lang)
            print(f"  {name}: {len(items)}", file=sys.stderr)
            out.extend(items)
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:50]}", file=sys.stderr)
        time.sleep(0.5)
    seen, uniq = set(), []
    for it in out:
        k = re.sub(r"\W", "", it["title"])[:24]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    uniq.sort(key=lambda x: -x["ts"])
    return uniq


# ============================================================
MAJOR = {"美国", "中国", "欧元区", "日本", "英国", "德国", "法国", "加拿大", "澳大利亚", "瑞士"}


def curate(events):
    """过滤 + 去重：只保留值得关注的事件"""
    out = []
    for e in events:
        lv, c = e["level"], e["country"]
        keep = (lv == "极高") or (lv == "高" and c in MAJOR)
        if not keep:
            continue
        out.append(e)
    # 同一时间同一名称只留一条（取预期值最完整的）
    seen = {}
    for e in out:
        k = (e["date"], e["time"], e["name"], e["country"])
        if k not in seen:
            seen[k] = e
        else:
            old = seen[k]
            if len(e.get("forecast") or "") > len(old.get("forecast") or ""):
                seen[k] = e
    res = list(seen.values())
    res.sort(key=lambda x: (x["ts"], LEVEL_ORDER.get(x["level"], 9)))
    return res


def main():
    print("抓日历...", file=sys.stderr)
    events = fetch_nasdaq_calendar(8)
    print(f"  原始 {len(events)} 条", file=sys.stderr)
    events = curate(events)
    print(f"  精选 {len(events)} 条", file=sys.stderr)

    print("抓新闻...", file=sys.stderr)
    news = fetch_news()

    now = time.time()
    fut7 = [e for e in events if 0 <= e["ts"] - now <= 7 * 86400]
    payload = {
        "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "events": events,
        "news": news,
        "counts": {
            "events_future7": len(fut7),
            "events_high": sum(1 for e in fut7 if e["level"] in ("极高", "高")),
            "news_7d": sum(1 for n in news if now - n["ts"] <= 7 * 86400),
            "news_30d": sum(1 for n in news if now - n["ts"] <= 30 * 86400),
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("完成:", json.dumps(payload["counts"], ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
