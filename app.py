import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

if "GEMINI_API_KEY" not in st.secrets:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.set_page_config(page_title="AI株価アナリスト", layout="wide")
st.title("🚀 Gemini AI 専門家仕様 (シンプル安定版)")

ticker = st.text_input("銘柄名を入力", placeholder="トヨタ自動車")

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

def fetch_analysis(ticker_name):
    # ここを 1.5-flash に変更しました
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データを出力してください。
    必ず以下のJSON形式のみを出力してください。
    {{
        "company_name": "{ticker_name}",
        "current_price": 1234,
        "shares_outstanding": 123,
        "net_debt": 12345,
        "sales": 12345,
        "fcf_margin": 10.5,
        "growth_rate_high": 5.0,
        "growth_rate_stable": 2.0,
        "terminal_growth": 1.0,
        "risk_free_rate": 0.5,
        "beta": 1.1,
        "market_premium": 5.0
    }}
    """
    response = model.generate_content(prompt)
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("AIの回答からデータを抽出できませんでした。")

if st.button("AI分析を実行"):
    if not ticker:
        st.warning("銘柄名を入力してください")
    else:
        with st.spinner("AIが分析中..."):
            try:
                data = fetch_analysis(ticker)
                
                cp = clean_float(data.get('current_price', 0))
                sh = clean_float(data.get('shares_outstanding', 0))
                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                
                rf = clean_float(data.get('risk_free_rate', 0))
                beta = clean_float(data.get('beta', 0))
                mp = clean_float(data.get('market_premium', 0))
                
                wacc = (rf + beta * mp) / 100
                if wacc <= 0: wacc = 0.05 
                
                fcf_margin = clean_float(data.get('fcf_margin', 0))
                g_high = clean_float(data.get('growth_rate_high', 0))
                g_stable = clean_float(data.get('growth_rate_stable', 0))
                tg_val = clean_float(data.get('terminal_growth', 0))
                
                fcf_list = []
                pv_sum = 0
                curr_s = sales
                for y in range(1, 6):
                    g = g_high if y <= 3 else g_stable
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (fcf_margin/100)
                    fcf_list.append(fcf)
                    pv_sum += fcf / ((1 + wacc)**y)
                
                tg = tg_val / 100
                if wacc <= tg: tg = wacc - 0.01

                tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                pv_tv = tv / ((1 + wacc)**5)
                
                total_value = (pv_sum + pv_tv) - debt
                theoretical_price = total_value / sh if sh > 0 else 0
                
                upside = 0
                if cp > 0: upside = (theoretical_price / cp - 1) * 100

                st.success(f"### 分析完了: {data.get('company_name', ticker)}")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{cp:,.0f}")
                c3.metric("上昇余地", f"{upside:+.1f}%", delta=f"{upside:+.1f}%")

                st.write("#### 将来予測キャッシュフロー")
                st.bar_chart(pd.DataFrame(fcf_list, index=[f"{y}年目" for y in range(1, 6)], columns=["FCF"]))
                
                with st.expander("AIの調査データ内訳"):
                    st.write(data)

            except Exception as e:
                st.error("分析エラーが発生しました。")
                st.caption(f"エラー詳細: {e}")
