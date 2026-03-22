import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re
import yfinance as yf

if "GEMINI_API_KEY" not in st.secrets:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.set_page_config(page_title="AI株価アナリスト PRO+四季報", layout="wide")
st.title("🚀 Gemini AI 2.5 プロ仕様 (四季報コピペ対応版)")

# 入力エリア
col_in1, col_in2 = st.columns([1, 2])
with col_in1:
    ticker = st.text_input("銘柄名を入力", placeholder="安川電機")
with col_in2:
    shikiho_text = st.text_area("四季報オンラインの業績表などをコピペ（任意）", placeholder="ここを空欄にしてもAIが自動推測しますが、貼り付けると精度が劇的に上がります", height=100)

def clean_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    cleaned = re.sub(r'[^\d.-]', '', str(value))
    try:
        return float(cleaned)
    except:
        return 0.0

def fetch_analysis(ticker_name, context_text=""):
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    あなたはプロの証券アナリストです。{ticker_name}のDCF分析を行います。
    もし以下の【補足データ】に数値がある場合は、そのテキスト内の数値を最優先で採用してください。
    
    【補足データ】
    {context_text}

    【極めて重要な規定】
    1. 製造業（自動車・機械・化学等）のfcf_marginは「2%〜6%」が標準です。補足データに根拠がない限り、過大なマージンは避けてください。
    2. 永久成長率は「0%〜1.0%」の範囲で保守的に設定してください。
    3. yahoo_ticker は、分析対象の銘柄の正しい証券コードを出力してください（例：6506.T）。
    4. 金額・株数は必ず「1の位」までのフル桁数（整数）で出力してください。
    
    必ず以下のJSON形式のみを出力。
    {{
        "company_name": "{ticker_name}",
        "yahoo_ticker": "証券コード.T",
        "current_price_fallback": 最新株価,
        "shares_outstanding_fallback": 発行済株式総数,
        "net_debt": 実質純負債(フル桁),
        "sales": 直近売上高(フル桁),
        "fcf_margin": FCFマージン(%),
        "growth_rate_bull": 強気成長率(%),
        "growth_rate_base": 基本成長率(%),
        "growth_rate_bear": 弱気成長率(%),
        "terminal_growth": 永久成長率(%),
        "risk_free_rate": 無リスク金利(%),
        "beta": ベータ値,
        "market_premium": リスクプレミアム(%)
    }}
    """
    response = model.generate_content(prompt)
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("AIの回答からデータを抽出できませんでした。")

if st.button("AI本格分析を実行"):
    if not ticker:
        st.warning("銘柄名を入力してください")
    else:
        with st.spinner("財務データと貼り付けられたテキストを解析中..."):
            try:
                data = fetch_analysis(ticker, shikiho_text)
                
                cp = clean_float(data.get('current_price_fallback', 0))
                sh = clean_float(data.get('shares_outstanding_fallback', 0))
                data_source_msg = "⚠️ AIの予測値を使用中"
                
                try:
                    ticker_symbol = data.get('yahoo_ticker', '')
                    if ticker_symbol:
                        yf_ticker = yf.Ticker(ticker_symbol)
                        info = yf_ticker.info
                        cp = float(info.get('currentPrice', info.get('regularMarketPrice', cp)))
                        sh = float(info.get('sharesOutstanding', sh))
                        data_source_msg = f"✅ 市場データ（証券コード:{ticker_symbol} / 株式数:{sh:,.0f}株）を取得完了"
                except:
                    pass

                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                fcf_margin = clean_float(data.get('fcf_margin', 0))
                rf = clean_float(data.get('risk_free_rate', 0))
                beta = clean_float(data.get('beta', 0))
                mp = clean_float(data.get('market_premium', 0))
                wacc = (rf + beta * mp) / 100
                if wacc <= 0: wacc = 0.05 
                tg = (clean_float(data.get('terminal_growth', 0)) / 100)
                if wacc <= tg: tg = wacc - 0.01

                def calculate_scenario(growth_rate):
                    fcf_list = []
                    pv_sum = 0
                    curr_s = sales
                    for y in range(1, 6):
                        curr_s *= (1 + growth_rate/100)
                        fcf = curr_s * (fcf_margin/100)
                        fcf_list.append(fcf)
                        pv_sum += fcf / ((1 + wacc)**y)
                    tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                    pv_tv = tv / ((1 + wacc)**5)
                    price = (pv_sum + pv_tv - debt) / sh if sh > 0 else 0
                    return price, (price / cp - 1) * 100 if cp > 0 else 0, fcf_list

                res_bull = calculate_scenario(clean_float(data.get('growth_rate_bull', 0)))
                res_base = calculate_scenario(clean_float(data.get('growth_rate_base', 0)))
                res_bear = calculate_scenario(clean_float(data.get('growth_rate_bear', 0)))

                st.success(f"### 分析完了: {data.get('company_name', ticker)}")
                st.info(data_source_msg)

                t1, t2, t3 = st.tabs(["📊 基本", "🚀 強気", "📉 弱気"])
                for tab, res, label in zip([t1, t2, t3], [res_base, res_bull, res_bear], ["基本", "強気", "弱気"]):
                    with tab:
                        c1, c2, c3 = st.columns(3)
                        c1.metric(f"{label}理論株価", f"¥{res[0]:,.0f}")
                        c2.metric("現在株価", f"¥{cp:,.0f}")
                        c3.metric("上昇余地", f"{res[1]:+.1f}%", delta=f"{res[1]:+.1f}%")
                        st.bar_chart(pd.DataFrame([f/100000000 for f in res[2]], index=[f"{y}年目" for y in range(1, 6)], columns=["FCF (億円)"]))

                with st.expander("AIが読み取った分析詳細"):
                    st.write(data)

            except Exception as e:
                st.error(f"分析中にエラーが発生しました: {e}")
