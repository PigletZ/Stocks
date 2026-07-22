from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging

import pandas as pd
import tushare as ts

from ..config import settings


logger = logging.getLogger(__name__)


# ETF 品类规则：按优先级从高到低匹配，命中即返回
# 规则格式：(关键词列表, 品类名称)
ETF_CATEGORY_RULES: List[tuple] = [
    # 海外宽基
    (["纳斯达克100"], "海外-纳斯达克100"),
    (["纳斯达克"], "海外-纳斯达克"),
    (["标普500"], "海外-标普500"),
    (["标普"], "海外-标普"),
    (["道琼斯"], "海外-道琼斯"),
    (["恒生科技"], "港股-恒生科技"),
    (["恒生"], "港股-恒生"),
    (["港股通"], "港股-港股通"),
    (["日经"], "海外-日经"),
    (["德国"], "海外-德国"),
    (["法国"], "海外-法国"),
    (["英国"], "海外-英国"),
    (["越南"], "海外-越南"),
    (["印度"], "海外-印度"),
    (["韩国"], "海外-韩国"),
    (["东南亚"], "海外-东南亚"),
    # A股宽基
    (["沪深300"], "宽基-沪深300"),
    (["中证500"], "宽基-中证500"),
    (["中证1000"], "宽基-中证1000"),
    (["中证2000"], "宽基-中证2000"),
    (["国证2000"], "宽基-国证2000"),
    (["上证50"], "宽基-上证50"),
    (["科创50"], "宽基-科创50"),
    (["创业板指"], "宽基-创业板指"),
    (["创业板50"], "宽基-创业板50"),
    (["深证100"], "宽基-深证100"),
    (["深证50"], "宽基-深证50"),
    (["中证800"], "宽基-中证800"),
    (["上证指数"], "宽基-上证指数"),
    (["深证成指"], "宽基-深证成指"),
    (["深证综指"], "宽基-深证综指"),
    (["上证180"], "宽基-上证180"),
    (["中证A50"], "宽基-中证A50"),
    (["MSCI"], "宽基-MSCI"),
    # 商品
    (["黄金"], "商品-黄金"),
    (["原油"], "商品-原油"),
    (["豆粕"], "商品-豆粕"),
    (["有色金属"], "商品-有色金属"),
    (["能源化工"], "商品-能源化工"),
    (["白银"], "商品-白银"),
    (["商品"], "商品"),
    # 债券/货币/REITs
    (["国债"], "债券-国债"),
    (["政金债"], "债券-政金债"),
    (["企业债"], "债券-企业债"),
    (["公司债"], "债券-公司债"),
    (["可转债"], "债券-可转债"),
    (["短融"], "债券-短融"),
    (["同业存单"], "货币-同业存单"),
    (["货币"], "货币"),
    (["REITs"], "REITs"),
    # 行业/主题
    (["半导体", "芯片"], "科技-半导体"),
    (["集成电路"], "科技-半导体"),
    (["人工智能", "AI"], "科技-人工智能"),
    (["计算机"], "科技-计算机"),
    (["通信"], "科技-通信"),
    (["5G"], "科技-5G"),
    (["电子"], "科技-电子"),
    (["传媒"], "传媒"),
    (["游戏"], "传媒-游戏"),
    (["影视"], "传媒-影视"),
    (["云计算", "云"], "科技-云计算"),
    (["大数据"], "科技-大数据"),
    (["物联网"], "科技-物联网"),
    (["工业互联网"], "科技-工业互联网"),
    (["机器人"], "制造-机器人"),
    (["机床"], "制造-机床"),
    (["工程机械"], "制造-工程机械"),
    (["电力"], "公用事业-电力"),
    (["电网"], "公用事业-电网"),
    (["环保"], "环保"),
    (["新能源"], "新能源"),
    (["光伏"], "新能源-光伏"),
    (["电池"], "新能源-电池"),
    (["储能"], "新能源-储能"),
    (["锂电"], "新能源-锂电"),
    (["新能源汽车", "新能源车"], "汽车-新能源"),
    (["汽车"], "汽车"),
    (["智能电车"], "汽车-智能电车"),
    (["医药"], "医药"),
    (["医疗"], "医药-医疗"),
    (["生物"], "医药-生物"),
    (["创新药"], "医药-创新药"),
    (["中药"], "医药-中药"),
    (["医疗器械"], "医药-医疗器械"),
    (["疫苗"], "医药-疫苗"),
    (["CXO"], "医药-CXO"),
    (["银行"], "金融-银行"),
    (["证券", "券商"], "金融-券商"),
    (["保险"], "金融-保险"),
    (["金融科技"], "金融-金融科技"),
    (["地产", "房地产"], "房地产"),
    (["基建"], "基建"),
    (["建材"], "建材"),
    (["钢铁"], "周期-钢铁"),
    (["煤炭"], "周期-煤炭"),
    (["石油"], "能源-石油"),
    (["天然气"], "能源-天然气"),
    (["有色"], "周期-有色"),
    (["稀土"], "周期-稀土"),
    (["化工"], "周期-化工"),
    (["农业"], "农业"),
    (["畜牧", "养殖"], "农业-养殖"),
    (["粮食"], "农业-粮食"),
    (["食品饮料"], "消费-食品饮料"),
    (["白酒"], "消费-白酒"),
    (["家电"], "消费-家电"),
    (["旅游"], "消费-旅游"),
    (["消费"], "消费"),
    (["军工", "国防"], "军工"),
    (["航空航天"], "军工-航空航天"),
    (["船舶"], "军工-船舶"),
    (["物流"], "物流"),
    (["红利"], "策略-红利"),
    (["低波动"], "策略-低波动"),
    (["价值"], "策略-价值"),
    (["成长"], "策略-成长"),
    (["质量"], "策略-质量"),
    (["ESG"], "策略-ESG"),
    (["基本面"], "策略-基本面"),
    (["等权"], "策略-等权"),
]


def _extract_category(name: str, benchmark: str) -> str:
    """根据 ETF 名称和跟踪标的提取品类/主题。

    规则基于关键词匹配，无法覆盖全部 ETF，未命中返回"其他"。
    """
    text = f"{name or ''} {benchmark or ''}"
    for keywords, category in ETF_CATEGORY_RULES:
        for kw in keywords:
            if kw in text:
                return category
    return "其他"


class EtfService:
    """ETF 数据服务"""

    def __init__(self):
        self._tushare_pro = None
        self._etf_list_cache: Optional[pd.DataFrame] = None
        self._etf_list_cache_time: Optional[datetime] = None

    def _get_tushare_pro(self):
        """使用 Tushare token 初始化 Pro 接口"""
        if not hasattr(self, "_tushare_pro") or self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError(
                    "Tushare token 未配置，请检查 /etc/kimi/stocks/base.conf 中的 [tushare]"
                )
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    @staticmethod
    def _ts_code_to_code(ts_code: str) -> str:
        """将 Tushare ts_code 转换为纯数字代码"""
        return ts_code.split(".")[0] if ts_code else ""

    def _fetch_trade_dates(self, start: date, end: date) -> List[date]:
        """获取 A 股交易日列表（ETF 与 A 股交易日一致）"""
        try:
            df = self._get_tushare_pro().trade_cal(
                exchange="SSE",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            df = df[df["is_open"] == 1]
            dates = sorted(df["cal_date"].astype(str).tolist())
            return [datetime.strptime(d, "%Y%m%d").date() for d in dates]
        except Exception:
            # fallback：仅剔除周末
            dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    dates.append(current)
                current += timedelta(days=1)
            return dates

    def _get_previous_trade_date(self, target_date: date) -> Optional[date]:
        """获取 target_date 之前最近的一个交易日"""
        try:
            start = target_date - timedelta(days=14)
            dates = self._fetch_trade_dates(start, target_date)
            for d in reversed(dates):
                if d < target_date:
                    return d
        except Exception:
            pass
        return None

    def _fetch_etf_basic_list(self) -> pd.DataFrame:
        """从 Tushare 获取 ETF 基础列表"""
        try:
            df = self._get_tushare_pro().fund_basic(market="E")
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.copy()
            df["code"] = df["ts_code"].astype(str).apply(self._ts_code_to_code)
            return df
        except Exception as e:
            logger.warning("获取 ETF 基础列表失败: %s", e)
            return pd.DataFrame()

    def _fetch_etf_daily_for_date(self, target_date: date) -> pd.DataFrame:
        """从 Tushare 获取指定交易日的全市场 ETF 日线"""
        try:
            date_str = target_date.strftime("%Y%m%d")
            df = self._get_tushare_pro().fund_daily(trade_date=date_str)
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.copy()
            df["code"] = df["ts_code"].astype(str).apply(self._ts_code_to_code)
            return df
        except Exception as e:
            logger.warning("获取 ETF 日线 %s 失败: %s", target_date, e)
            return pd.DataFrame()

    def _get_etf_list_with_cache(self) -> pd.DataFrame:
        """获取 ETF 基础列表，带 1 小时内存缓存"""
        now = datetime.utcnow()
        if (
            self._etf_list_cache is not None
            and self._etf_list_cache_time is not None
            and (now - self._etf_list_cache_time).seconds < 3600
        ):
            return self._etf_list_cache

        df = self._fetch_etf_basic_list()
        self._etf_list_cache = df
        self._etf_list_cache_time = now
        return df

    def fetch_etf_list(
        self,
        sort_by: str = "change_pct",
        order: str = "desc",
        offset: int = 0,
        limit: int = 50,
        category: str = "",
    ) -> dict:
        """获取 ETF 列表，支持按品类、涨幅、成交额等排序与分页。

        默认自动回退到最近有数据的交易日。
        """
        target_date = date.today()
        df_daily = self._fetch_etf_daily_for_date(target_date)
        if df_daily is None or df_daily.empty:
            prev_date = self._get_previous_trade_date(target_date)
            if prev_date:
                df_daily = self._fetch_etf_daily_for_date(prev_date)

        effective_date = target_date if df_daily is not None and not df_daily.empty else None

        df_basic = self._get_etf_list_with_cache()
        if df_basic.empty:
            return {"total": 0, "items": [], "effective_date": effective_date.isoformat() if effective_date else None}

        # 合并日线数据
        df = df_basic.merge(df_daily, on="code", how="left", suffixes=("", "_daily"))

        # 标准化字段
        df["close"] = pd.to_numeric(df.get("close"), errors="coerce")
        df["pct_chg"] = pd.to_numeric(df.get("pct_chg"), errors="coerce")
        df["amount"] = pd.to_numeric(df.get("amount"), errors="coerce")

        # 提取品类
        df["category"] = df.apply(
            lambda r: _extract_category(str(r.get("name", "")), str(r.get("benchmark", ""))),
            axis=1,
        )

        # 品类筛选
        if category:
            df = df[df["category"].str.contains(category, na=False)]

        # 排序
        valid_sort = {
            "change_pct": "pct_chg",
            "amount": "amount",
            "close": "close",
            "name": "name",
            "category": "category",
        }
        sort_col = valid_sort.get(sort_by, "pct_chg")
        ascending = order.lower() == "asc"
        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=ascending, na_position="last")

        total = len(df)
        df = df.iloc[offset : offset + limit]

        items = []
        for _, row in df.iterrows():
            items.append({
                "code": str(row.get("code", "")),
                "name": str(row.get("name", "")),
                "management": str(row.get("management", "")),
                "fund_type": str(row.get("fund_type", "")),
                "benchmark": str(row.get("benchmark", "")),
                "category": str(row.get("category", "")),
                "close": float(row["close"]) if pd.notna(row.get("close")) else 0.0,
                "change_pct": float(row["pct_chg"]) if pd.notna(row.get("pct_chg")) else 0.0,
                "amount": float(row["amount"]) if pd.notna(row.get("amount")) else 0.0,
            })

        return {
            "total": total,
            "items": items,
            "effective_date": effective_date.isoformat() if effective_date else None,
        }

    def fetch_etf_categories(self) -> List[str]:
        """获取所有 ETF 品类列表（按出现频次降序）"""
        df_basic = self._get_etf_list_with_cache()
        if df_basic.empty:
            return []

        df_basic = df_basic.copy()
        df_basic["category"] = df_basic.apply(
            lambda r: _extract_category(str(r.get("name", "")), str(r.get("benchmark", ""))),
            axis=1,
        )
        categories = df_basic["category"].value_counts().index.tolist()
        return categories

    def _resolve_effective_date(self, target_date: date) -> Optional[date]:
        """确定有效交易日，当天无数据时回退到上一交易日"""
        df = self._fetch_etf_daily_for_date(target_date)
        if df is not None and not df.empty:
            return target_date
        prev_date = self._get_previous_trade_date(target_date)
        if prev_date:
            df = self._fetch_etf_daily_for_date(prev_date)
            if df is not None and not df.empty:
                return prev_date
        return None

    def _get_lookback_trade_dates(
        self,
        effective_date: date,
        windows: List[int],
    ) -> Dict[int, Optional[date]]:
        """根据交易日历，计算 effective_date 前推 N 个交易日的日期"""
        dates = self._fetch_trade_dates(
            effective_date - timedelta(days=60), effective_date
        )
        if effective_date not in dates:
            return {w: None for w in windows}

        idx = dates.index(effective_date)
        return {w: dates[idx - w] if idx >= w else None for w in windows}

    def fetch_etf_gainers(
        self,
        target_date: Optional[date] = None,
        category: str = "",
        min_amount: float = 1000.0,
    ) -> dict:
        """获取 ETF 的 2日/5日/10日/20日涨幅榜前 10，支持按品类筛选。

        默认自动回退到最近有数据的交易日。
        min_amount 单位为万元，仅对 2 日榜生效（短窗口噪音大，过滤迷你基/妖基）。
        """
        d = target_date or date.today()
        effective_date = self._resolve_effective_date(d)
        if effective_date is None:
            return {
                "target_date": d.isoformat(),
                "effective_date": None,
                "two_day": [],
                "five_day": [],
                "ten_day": [],
                "twenty_day": [],
            }

        lookbacks = self._get_lookback_trade_dates(effective_date, [2, 5, 10, 20])
        two_base = lookbacks.get(2)
        five_base = lookbacks.get(5)
        ten_base = lookbacks.get(10)
        twenty_base = lookbacks.get(20)

        # 拉取所需日期的日线
        daily_map: Dict[date, pd.DataFrame] = {}
        for td in {effective_date, two_base, five_base, ten_base, twenty_base}:
            if td is None:
                continue
            daily_map[td] = self._fetch_etf_daily_for_date(td)

        # 合并基础信息
        df_basic = self._get_etf_list_with_cache()
        if df_basic.empty:
            return {
                "target_date": d.isoformat(),
                "effective_date": effective_date.isoformat(),
                "two_day": [],
                "five_day": [],
                "ten_day": [],
                "twenty_day": [],
            }

        df_basic = df_basic.copy()
        df_basic["category"] = df_basic.apply(
            lambda r: _extract_category(str(r.get("name", "")), str(r.get("benchmark", ""))),
            axis=1,
        )
        if category:
            df_basic = df_basic[df_basic["category"].str.contains(category, na=False)]

        code_name_map = dict(zip(df_basic["code"], df_basic["name"]))
        allowed_codes = set(df_basic["code"].astype(str).tolist())

        def _build_ranking(
            end_date: date,
            start_date: Optional[date],
            min_amount_wan: float = 0.0,
        ) -> List[dict]:
            if start_date is None:
                return []
            df_end = daily_map.get(end_date)
            df_start = daily_map.get(start_date)
            if df_end is None or df_start is None or df_end.empty or df_start.empty:
                return []

            # fund_daily 的 amount 单位为千元
            df_end = df_end.copy()
            df_end["amount"] = pd.to_numeric(df_end["amount"], errors="coerce").fillna(0)
            if min_amount_wan > 0:
                df_end = df_end[df_end["amount"] >= min_amount_wan * 10]

            end_quotes = df_end.set_index("code")[["close"]].rename(columns={"close": "close_end"})
            start_quotes = df_start.set_index("code")[["close"]].rename(columns={"close": "close_start"})
            merged = end_quotes.join(start_quotes, how="inner")
            merged = merged[(merged["close_end"] > 0) & (merged["close_start"] > 0)]
            merged["gain"] = (merged["close_end"] / merged["close_start"] - 1) * 100
            merged = merged.sort_values("gain", ascending=False)

            result = []
            for code, row in merged.iterrows():
                code_str = str(code)
                if code_str not in allowed_codes:
                    continue
                result.append({
                    "rank": len(result) + 1,
                    "code": code_str,
                    "name": str(code_name_map.get(code_str, "")),
                    "close": round(float(row["close_end"]), 3),
                    "gain": round(float(row["gain"]), 2),
                })
                if len(result) >= 10:
                    break
            return result

        return {
            "target_date": d.isoformat(),
            "effective_date": effective_date.isoformat(),
            "two_day": _build_ranking(effective_date, two_base, min_amount_wan=min_amount),
            "five_day": _build_ranking(effective_date, five_base),
            "ten_day": _build_ranking(effective_date, ten_base),
            "twenty_day": _build_ranking(effective_date, twenty_base),
        }
