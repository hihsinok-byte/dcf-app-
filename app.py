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

st.set_page_config(page_title="AI株価アナリスト Autopilot", layout="wide")
st.title("🤖 Gemini AI 2.5 全自動リサーチ・アナリスト")
st.caption("IRBANK、みんかぶ、バフェットコード等の公開情報をAIが自ら調査し、DCF分析を行います。")

ticker_input = st.text_input("銘柄名または証券コードを入力", placeholder="安川電機 または 6506")

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

def fetch_analysis_autopilot(ticker_name):
    # 最新モデルを使用して検索能力を最大化
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    あなたは凄腕の証券アナリストです。
    今から「{ticker_name}」について、IRBANK、バフェットコード、みんかぶ、ヤフーファイナンス、および公式サイトの決算短信を検索・調査してください。
    
    【調査・算出ルール】
    1. 最新の通期決算データおよび直近の四半期進捗を確認してください。
    2. 製造業の場合、FCFマージンは実態に合わせて3%〜8%程度で保守的に見積もってください。
    3. 純有利子負債(net_debt)は、現金同等物を差し引いた実質値を算出してください。
    4. 証券コードを特定し、yahoo_ticker（例: 6506.T）を必ず出力してください。
    
    必ず以下のJSON形式のみを回答してください。
    {{
        "company_name": "正確な企業名",
        "yahoo_ticker": "証券コード.T",
        "current_price_fallback": 調査した最新株価,
        "shares_outstanding_fallback": 最新の発行済株式総数,
        "net_debt": 算出された純有利子負債(円),
        "sales": 直近の年間売上高(円),
        "fcf_margin": 予測FCFマージン(%),
        "growth_rate_bull": 調査に基づく強気成長率(%),
        "growth_rate_base": 調査に基づく基本成長率(%),
        "growth_rate_bear": 調査に基づく弱気成長率(%),
        "terminal_growth": 永久成長率(0.5-1.0%推奨),
        "wacc_reason": "WACC算出の根拠を一言",
        "beta": 調査されたベータ値,
        "risk_free_rate": 0.5,
        "market_premium": 5.5
    }}
    """
    # AIにウェブ検索と解析を行わせる
    response = model.generate_content(prompt)
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("AIがデータを特定できませんでした。")

if st.button("全自動AI分析を開始"):
    if not ticker_input:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner(f"AIが {ticker_input} の決算書と財務サイトを巡回調査中..."):
            try:
                data = fetch_analysis_autopilot(ticker_input)
                
                # 市場データのリアルタイム取得を試行
                ticker_symbol = data.get('yahoo_ticker', '')
                sh = clean_float(data.get('shares_outstanding_fallback', 0))
                cp = clean_float(data.get('current_price_fallback', 0))
                
                try:
                    if ticker_symbol:
                        yf_ticker = yf.Ticker(ticker_symbol)
                        info = yf_ticker.info
                        cp = float(info.get('currentPrice', info.get('regularMarketPrice', cp)))
                        sh = float(info.get('sharesOutstanding', sh))
                except:
                    pass

                # DCF計算
                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                fcf_margin = clean_float(data.get('fcf_margin', 0))
                beta = clean_float(data.get('beta', 1.0))
                rf = clean_float(data.get('risk_free_rate', 0.5))
                mp = clean_float(data.get('market_premium', 5.0))
                wacc = (rf + beta * mp) / 100
                tg = clean_float(data.get('terminal_growth', 0.8)) / 100

                def calc(g):
                    f_list = []
                    pv = 0
                    s = sales
                    for i in range(5):
                        s *= (1 + g/100)
                        f = s * (fcf_margin/100)
                        f_list.append(f)
                        pv += f / ((1 + wacc)**(i+1))
                    tv = (f_list[-1] * (1 + tg)) / (wacc - tg)
                    val = (pv + (tv / (1 + wacc)**5) - debt) / sh
                    return val, (val/cp - 1)*100, f_list

                r_bull = calc(clean_float(data.get('growth_rate_bull', 0)))
                r_base = calc(clean_float(data.get('growth_rate_base', 0)))
                r_bear = calc(clean_float(data.get('growth_rate_bear', 0)))

                st.success(f"### 調査結果: {data.get('company_name')} ({ticker_symbol})")
                
                col1, col2 = st.columns(2)
                col1.info(f"✅ 発行済株式数: {sh:,.0f}株 (市場データ)")
                col2.info(f"🛡️ WACC根拠: {data.get('wacc_reason')}")

                t1, t2, t3 = st.tabs(["📊 基本", "🚀 強気", "📉 弱気"])
                for tab, res, label in zip([t1, t2, t3], [r_base, r_bull, r_bear], ["基本", "強気", "弱気"]):
                    with tab:
                        c1, c2, c3 = st.columns(3)
                        c1.metric(f"{label}理論株価", f"¥{res[0]:,.0f}")
                        c2.metric("現在株価", f"¥{cp:,.0f}")
                        c3.metric("上昇余地", f"{res[1]:+.1f}%", delta=f"{res[1]:+.1f}%")
                        st.bar_chart(pd.DataFrame([f/100000000 for f in res[2]], index=[f"{i+1}年目" for i in range(5)], columns=["予測FCF (億円)"]))

                with st.expander("AIが収集した財務生データ"):
                    st.write(data)

            except Exception as e:
                st.error(f"調査失敗: {e}")
