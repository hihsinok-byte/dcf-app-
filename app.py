import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

# 秘密鍵の読み込み
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")

st.set_page_config(page_title="Gemini AI DCFアナリスト", layout="wide")
st.title("Gemini AI 自動調査・精緻DCF分析ツール")

ticker = st.text_input("銘柄名を入力（例：トヨタ、積水化学）", placeholder="積水化学")

def fetch_financial_data(ticker_name):
    # 【修正ポイント】モデル名を最新の正式名称「gemini-1.5-flash-latest」に変更
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データを調査し、DCF分析用数値を推論してください。
    回答は必ず以下のJSON形式のデータのみを出力してください。
    {{
        "company_name": "会社名",
        "current_price": 数値,
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
    """
    
    response = model.generate_content(prompt)
    res_text = response.text
    
    json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    else:
        raise ValueError("データの解析に失敗しました。")

if st.button("AI分析を実行"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("Geminiが最新データを分析中..."):
            try:
                data = fetch_financial_data(ticker)
                
                # 数値の計算
                sales = float(data['sales'])
                shares = float(data['shares_outstanding'])
                current_price = float(data['current_price'])
                wacc = (float(data['risk_free_rate']) + float(data['beta']) * float(data['market_premium'])) / 100 
                
                future_fcf = []
                pv_fcf_sum = 0
                curr_s = sales
                for y in range(1, 6):
                    g = float(data['growth_rate_high']) if y <= 3 else float(data['growth_rate_stable'])
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (float(data['fcf_margin'])/100)
                    future_fcf.append(fcf)
                    pv_fcf_sum += fcf / ((1 + wacc)**y)
                
                tg = float(data['terminal_growth']) / 100
                tv = (future_fcf[-1] * (1 + tg)) / (wacc - tg)
                pv_tv = tv / ((1 + wacc)**5)
                
                equity_value = (pv_fcf_sum + pv_tv) - float(data['net_debt'])
                theoretical_price = equity_value / shares
                
                # 表示
                st.success(f"分析完了: {data['company_name']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{current_price:,.0f}")
                upside = (theoretical_price / current_price - 1) * 100
                c3.metric("上昇余地", f"{upside:+.1f}%")
                
                with st.expander("AIが調査した財務数値の詳細"):
                    st.table(pd.Series(data).to_frame(name="調査値"))
                
            except Exception as e:
                st.error("エラーが発生しました。時間を置いて再度お試しください。")
                st.caption(f"エラー詳細: {e}")
