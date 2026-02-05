import streamlit as st
import requests
import pandas as pd
import time
import urllib3
from datetime import datetime
import io
import re
import logging

# --- 0. 环境设置 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="基金监控 Pro (自动识别版)",
    layout="wide",
    page_icon="🚀"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://fundf10.eastmoney.com/"
}

# 指数名称到代码的映射
INDEX_NAME_TO_CODE = {
    # 主要宽基指数
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "上证50": "sh000016",
    "创业板指": "sz399006",
    "深证成指": "sz399001",
    "中证1000": "sh000852",
    "科创50": "sh000688",
    "上证指数": "sh000001",
    "深证100": "sz399330",
    "中证800": "sh000906",
    "中证200": "sh000904",
    "中证100": "sh000903",
    "中证全指": "sh000985",
    "中证A股": "sh000985",
    "中证流通": "sh000902",

    # 行业指数
    "中证白酒": "sz399997",
    "中证医疗": "sz399989",
    "中证医药": "sh000933",
    "中证新能": "sh399808",
    "中证军工": "sh399967",
    "中证传媒": "sh399971",
    "中证计算机": "sh399935",
    "中证电子": "sh399811",
    "中证半导体": "sh399673",
    "中证芯片": "sh399673",
    "中证5G通信": "sh399994",
    "中证人工智能": "sh399971",
    "中证大数据": "sh399415",
    "中证云计算": "sh399413",
    "中证区块链": "sh399254",
    "中证金融科技": "sh399699",
    "中证银行": "sh399986",
    "中证证券": "sh399975",
    "券商": "sh399975",
    "证券": "sh399975",
    "中证保险": "sh399809",
    "中证地产": "sh399983",
    "中证有色": "sh399805",
    "中证煤炭": "sh399998",
    "中证钢铁": "sh399969",
    "中证基建": "sh399995",
    "中证农业": "sh399986",
    "中证消费": "sh399977",
    "中证红利": "sh000922",
    "中证环保": "sh399806",
    "中证TMT": "sh399998",
    "中证互联网": "sh399677",
    "中证游戏": "sh399418",
    "中证动漫游戏": "sh930901",
    "中证影视": "sh399418",
    "中证科技50策略": "sh000931",
    "中证科技": "sh000931",
    "中证科技50": "sh000931",

    # 主题指数
    "中证新能源车": "sh399976",
    "中证新能源": "sh399808",
    "中证光伏": "sh399618",
    "中证稀土": "sh399715",
    "中证创新药": "sh931152",
    "中证医疗器械": "sh931152",
    "中证生物科技": "sh399993",
    "中证养老": "sh399993",
    "中证食品饮料": "sh399996",
    "中证家用电器": "sh399996",

    # 港股指数
    "恒生指数": "r_hkHSI",
    "恒生科技": "r_hkHSTECH",
    "恒生国企": "r_hkHSCEI",
    "恒生医疗": "r_hkHSHKI",
    "恒生消费": "r_hkHSCSI",
    "恒生互联网": "r_hkHSIII",
    "港股通新经济": "r_hkHSNEI",

    # 美股指数 - 使用ETF作为替代
    "纳斯达克100": "s_usQQQ",
    "纳斯达克": "s_usQQQ",
    "纳斯达克综合": "s_usQQQ",
    "标普500": "s_usSPY",
    "标普500指数": "s_usSPY",
    "道琼斯": "s_usDIA",
    "道琼斯工业": "s_usDIA",
    "道琼斯指数": "s_usDIA",
    "罗素2000": "s_usIWM",

    # 中概股指数 - 使用ETF作为替代
    "中概互联网": "s_usKWEB",
    "中国互联网": "s_usKWEB",
    "中证海外中国互联网": "s_usKWEB",
    "中国互联": "s_usKWEB",
    "中概股": "s_usKWEB",
}


# --- 1. 工具函数 ---

def get_tencent_code(stock_code, fund_name):
    """转换股票代码为腾讯格式"""
    code = str(stock_code).strip()
    if '.' in code:
        code = code.split('.')[0]

    f_name = str(fund_name)
    is_overseas_fund = any(
        x in f_name for x in
        ["港", "恒生", "QDII", "海外", "互联网", "科技", "Nasdaq", "标普", "美股", "全球"])

    if code.isdigit():
        if is_overseas_fund and len(code) <= 5:
            return f"r_hk{code.zfill(5)}"
        else:
            full_code = code.zfill(6)
            if full_code.startswith(('6', '9')):
                return f"sh{full_code}"
            elif full_code.startswith(('0', '3')):
                return f"sz{full_code}"
            elif full_code.startswith(('4', '8')):
                return f"bj{full_code}"
            else:
                return f"sz{full_code}"

    if code.isalpha():
        return f"s_us{code.upper()}"

    return code


def extract_index_from_fund_name(fund_name):
    """从基金名称中提取指数名称"""
    if not fund_name:
        return None

    # 按长度降序排列，优先匹配更长的名称
    for index_name in sorted(INDEX_NAME_TO_CODE.keys(), key=len, reverse=True):
        if index_name in fund_name:
            return index_name
    return None


def is_garbage(text):
    """过滤杂质"""
    if not text or len(text) < 2:
        return True
    if re.match(r'^[0-9,.\-%]+$', text):
        return True
    garbage = ["详情", "行情", "股吧", "代码", "名称", "资讯", "比例", "序号", "占净值"]
    if any(x in text for x in garbage):
        return True
    return False


def safe_request(url, headers=None, max_retries=3, sleep_time=0.5):
    """通用重试请求函数"""
    for i in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=10, verify=False)
            if r.status_code == 200 and len(r.content) > 0:
                return r
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求失败 (尝试 {i + 1}/{max_retries}): {url[:50]}... 错误: {e}")
            if i == max_retries - 1:
                break
            time.sleep(sleep_time * (i + 1))
    return None


def get_tencent_quotes(tencent_codes):
    """获取腾讯行情（支持A股、港股、美股）"""
    if not tencent_codes:
        return {}

    def safe_float(v):
        try:
            if not v or v == '':
                return 0.0
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    res = {}
    code_list = list(tencent_codes)
    BATCH_SIZE = 60

    for i in range(0, len(code_list), BATCH_SIZE):
        batch_codes = code_list[i:i + BATCH_SIZE]
        url = f"http://qt.gtimg.cn/q={','.join(batch_codes)}"

        r = safe_request(url, headers={"Referer": "http://finance.qq.com/"}, max_retries=3)

        if r is None:
            continue

        try:
            content = r.content.decode('gbk', errors='ignore')
            lines = content.split(';')

            for line in lines:
                line = line.strip()
                if not line or '="' not in line:
                    continue

                try:
                    parts = line.split('="')
                    if len(parts) < 2:
                        continue

                    var_name = parts[0]
                    data_str = parts[1].rstrip('"')

                    # 提取代码
                    if '_sh' in var_name:
                        code = 'sh' + var_name.split('_sh')[1]
                    elif '_sz' in var_name:
                        code = 'sz' + var_name.split('_sz')[1]
                    elif '_hk' in var_name:
                        code = 'r_hk' + var_name.split('_hk')[1]
                    elif '_us' in var_name:
                        code = 's_us' + var_name.split('_us')[1]
                    else:
                        continue

                    # 解析数据字段
                    fields = data_str.split('~')
                    if len(fields) < 6:
                        continue

                    # 美股ETF: 字段5是涨跌幅%
                    if code.startswith('s_us'):
                        change_pct = safe_float(fields[5])
                        res[code] = change_pct
                    else:
                        # A股/港股: 字段32是涨跌幅%
                        change_pct = safe_float(fields[32]) if len(fields) > 32 else 0.0
                        res[code] = change_pct

                except Exception as e:
                    continue

        except Exception as e:
            continue

    return res


# --- 2. 核心抓取函数 ---

@st.cache_data(ttl=3600)
def fetch_fund_data(fund_code):
    """获取基金持仓数据"""
    url = f"http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline=200"

    r = safe_request(url, headers=HEADERS)

    if r is None:
        return None, "网络超时", "", False, None

    try:
        if 'content:"' not in r.text:
            return None, "接口拦截", "", False, None

        raw_html = r.text.split('content:"')[1].split('",')[0]
        raw_html = raw_html.replace(r'\"', '"').replace(r'\/', '/')

        # 1. 提取基金名称
        name_match = re.search(r"title='(.*?)'", raw_html)
        fund_name = name_match.group(1) if name_match else f"基金{fund_code}"

        # 2. 检查是否是ETF联接基金
        is_etf_link = "ETF联接" in fund_name

        # 3. 如果是ETF联接基金，从基金名称中提取跟踪的指数
        tracked_index = None
        if is_etf_link:
            tracked_index = extract_index_from_fund_name(fund_name)

        # 4. 物理截断：只保留第一个季度
        quarters = list(re.finditer(r'\d{4}年\d季度股票投资明细', raw_html))
        if len(quarters) > 1:
            raw_html = raw_html[:quarters[1].start()]

        date_match = re.search(r'截止至：(\d{4}-\d{2}-\d{2})', raw_html)
        report_date = date_match.group(1) if date_match else "最新"

        # 5. 解析表格
        dfs = pd.read_html(io.StringIO(raw_html))
        holdings = []

        for df in dfs:
            df = df.astype(str)
            for _, row in df.iterrows():
                vals = [str(v).strip() for v in row.values]
                if len(vals) < 5:
                    continue

                s_code, s_name, pct = None, None, 0.0
                c_idx = -1

                # 寻找代码锚点
                for i, v in enumerate(vals):
                    if v.isdigit() and 1 <= len(v) <= 6:
                        if i > 0 or len(v) >= 4:
                            s_code = v
                            c_idx = i
                            break
                    elif v.isalpha() and 1 < len(v) <= 5 and v.isupper():
                        s_code, c_idx = v, i
                        break

                if s_code and c_idx != -1:
                    if c_idx + 1 < len(vals) and not is_garbage(vals[c_idx + 1]):
                        s_name = vals[c_idx + 1]
                    elif c_idx - 1 >= 0 and not is_garbage(vals[c_idx - 1]):
                        s_name = vals[c_idx - 1]

                # 查找持仓占比
                for v in vals:
                    if '%' in v:
                        try:
                            pct = float(v.replace('%', '').replace(',', ''))
                            break
                        except:
                            pass

                if s_code and s_name and pct > 0:
                    tencent_code = get_tencent_code(s_code, fund_name)
                    holdings.append({
                        "名称": s_name,
                        "代码": s_code,
                        "持仓占比": pct,
                        "tencent_code": tencent_code
                    })

        if holdings:
            res_df = pd.DataFrame(holdings).drop_duplicates(subset=['代码'])
            res_df = res_df.sort_values(by='持仓占比', ascending=False).head(15)
            return res_df, fund_name, report_date, is_etf_link, tracked_index

    except Exception as e:
        logger.error(f"解析基金数据异常: {e}")
        return None, f"异常: {e}", "", False, None

    return None, "无数据", "", False, None


# --- 3. 界面逻辑 ---

with st.sidebar:
    st.header("⚙️ 监控列表管理")

    if 'fund_list' not in st.session_state:
        st.session_state.fund_list = ['011102', '010434', '161725', '020989']

    # 添加
    new_code = st.text_input("➕ 添加基金代码 (回车)")
    if new_code:
        c = new_code.strip()
        if c and c not in st.session_state.fund_list:
            st.session_state.fund_list.append(c)
            st.rerun()

    st.markdown("---")
    # 快速移除
    st.subheader("🗑️ 快速移除")
    updated_list = st.multiselect(
        "点击代码旁的 x 移除基金:",
        options=st.session_state.fund_list,
        default=st.session_state.fund_list
    )
    if updated_list != st.session_state.fund_list:
        st.session_state.fund_list = updated_list
        st.rerun()

    freq = st.slider("刷新频率 (秒)", 5, 60, 15)

    # 调试信息
    st.markdown("---")
    st.subheader("🔍 调试信息")
    show_debug = st.checkbox("显示调试日志")

st.title("🚀 基金持仓实时穿透监控 (自动识别版)")
st.markdown(f"最后更新: `{datetime.now().strftime('%H:%M:%S')}`")

# 获取数据
fund_results = {}
all_tencent_codes = set()
all_index_codes = set()

# 进度条
progress_bar = st.progress(0)
for idx, code in enumerate(st.session_state.fund_list):
    df, name, date, is_etf_link, tracked_index = fetch_fund_data(code)
    time.sleep(0.3)

    fund_results[code] = {
        "df": df,
        "name": name,
        "date": date,
        "is_etf_link": is_etf_link,
        "tracked_index": tracked_index
    }

    if df is not None and not is_etf_link:
        all_tencent_codes.update(df['tencent_code'].tolist())

    if is_etf_link and tracked_index:
        index_code = INDEX_NAME_TO_CODE.get(tracked_index)
        if index_code:
            all_index_codes.add(index_code)

    progress_bar.progress((idx + 1) / len(st.session_state.fund_list))

progress_bar.empty()

# 获取行情
all_codes = list(all_tencent_codes) + list(all_index_codes)
quotes = get_tencent_quotes(all_codes)

# 调试信息
if show_debug:
    st.subheader("调试日志")
    st.write(f"总股票/指数代码数: {len(all_codes)}")
    st.write(f"成功获取行情: {len(quotes)}")

    missing = set(all_codes) - set(quotes.keys())
    if missing:
        st.warning(f"未获取到行情 ({len(missing)}个): {list(missing)[:10]}")

# 渲染
if not st.session_state.fund_list:
    st.info("列表为空，请在侧边栏添加。")
else:
    cols = st.columns(3)
    for i, code in enumerate(st.session_state.fund_list):
        with cols[i % 3]:
            data = fund_results.get(code)

            if not data or data['df'] is None:
                with st.container(border=True):
                    st.error(f"基金 {code} 加载失败")
                    st.caption(f"原因: {data['name'] if data else '未知'}")
                continue

            df = data['df'].copy()
            is_etf_link = data.get('is_etf_link', False)
            tracked_index = data.get('tracked_index', '')

            # 判断是否是ETF联接基金
            if is_etf_link:
                # ETF联接基金：使用指数涨跌幅
                if tracked_index:
                    index_code = INDEX_NAME_TO_CODE.get(tracked_index)
                    if index_code:
                        est = quotes.get(index_code, 0.0)
                        etf_note = f"📊 ETF联接基金 (跟踪{tracked_index})"
                    else:
                        est = 0.0
                        etf_note = f"⚠️ 指数'{tracked_index}'未找到对应代码"
                else:
                    est = 0.0
                    etf_note = "⚠️ 未能识别跟踪指数"
            else:
                # 普通基金：使用持仓加权计算
                df['涨跌'] = df['tencent_code'].map(lambda x: quotes.get(x, 0.0))
                total_w = df['持仓占比'].sum()
                est = (df['涨跌'] * df['持仓占比']).sum() / total_w if total_w > 0 else 0
                etf_note = None

            with st.container(border=True):
                color = "#ff4b4b" if est >= 0 else "#09ab3b"
                st.subheader(data['name'])
                st.caption(f"代码: {code} | 截止日期: {data['date']}")

                if etf_note:
                    st.caption(etf_note)

                st.markdown(f"<h1 style='color:{color};text-align:center;'>{est:+.2f}%</h1>",
                            unsafe_allow_html=True)

                # 显示持仓表格
                if is_etf_link:
                    # ETF联接基金显示提示信息
                    st.info(
                        "ETF联接基金主要投资于目标ETF，不直接持有股票。已根据跟踪指数计算估算涨跌幅。")
                else:
                    # 普通基金显示持仓
                    valid_quotes = df[df['涨跌'] != 0].shape[0]
                    total_stocks = df.shape[0]

                    if valid_quotes < total_stocks:
                        st.caption(f"⚠️ 行情获取: {valid_quotes}/{total_stocks}")

                    st.dataframe(
                        df[['名称', '代码', '持仓占比', '涨跌']],
                        column_config={
                            "持仓占比": st.column_config.NumberColumn(format="%.2f%%"),
                            "涨跌": st.column_config.NumberColumn(format="%.2f%%")
                        },
                        hide_index=True,
                        width='stretch',
                        height=400
                    )

time.sleep(freq)
st.rerun()
