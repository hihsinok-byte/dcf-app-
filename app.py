import streamlit as st
import google.generativeai as genai
import json
import pandas as pd

# 秘密鍵の読み込み
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")

st.set_page_config(page_title="Gemini AI DCFアナリスト", layout="wide")
st.title("Gemini AI 自動調査・精緻DCF分析ツール")

st.info("銘柄名を入れるだけで、Geminiが最新の決算データを検索して分析します。")

ticker = st.text_input("銘柄名または証券コードを入力（例：トヨタ、積水化学）", placeholder="積水化学")

def fetch_financial_data(ticker_name):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    あなたはプロの株式アナリストです。{ticker_name}について最新の財務データを調査し、DCF分析に必要な数値をJSON形式で出力してください。
    必ず最新の決算短信や公式ニュースから数値を拾ってください。

    {{
        "company_name": "会社名",
        "current_price": 数値(円),
        "shares_outstanding": 数値(百万株),
        "net_debt": 数値(百万円),
        "sales": 数値(百万円),
        "fcf_margin": 数値(%),
        "growth_rate_high": 数値(%),
        "growth_rate_stable": 数値(%),
        "terminal_growth": 数値(%),
        "risk_free_rate": 数値(%),
        "beta": 数値,
        "market_premium": 数値(%)
    }}
    JSONのみを出力。
    """
    response = model.generate_content(prompt)
    text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(text)

if st.button("AIによる自動調査と分析を実行"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("Geminiが最新データを検索中..."):
            try:
                data = fetch_financial_data(ticker)
                sales = data['sales']
                shares = data['shares_outstanding']
                current_price = data['current_price']
                wacc_pct = (data['risk_free_rate'] + data['beta'] * data['market_premium']) / 100 
                
                years = [1, 2, 3, 4, 5]
                future_fcf = []
                pv_fcf = 0
                curr_s = sales
                for y in years:
                    g = data['growth_rate_high'] if y <= 3 else data['growth_rate_stable']
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (data['fcf_margin']/100)
                    future_fcf.append(fcf)
                    pv_fcf += fcf / ((1 + wacc_pct)**y)
                
                tg = data['terminal_growth'] / 100
                tv = (future_fcf[-1] * (1 + tg)) / (wacc_pct - tg)
                pv_tv = tv / ((1 + wacc_pct)**5)
                equity_value = (pv_fcf + pv_tv) - data['net_debt']
                theoretical_price = equity_value / shares
                
                st.header(f"分析結果: {data['company_name']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{current_price:,.0f}")
                upside = (theoretical_price / current_price - 1) * 100
                c3.metric("上昇余地", f"{upside:+.1f}%")
                
                with st.expander("Geminiの調査データ詳細"):
                    st.json(data)
                st.bar_chart(pd.DataFrame({"予測FCF": future_fcf}, index=[f"{y}年目" for y in years]))
            except Exception as e:
                st.error(f"エラーが発生しました。もう一度お試しください。")
