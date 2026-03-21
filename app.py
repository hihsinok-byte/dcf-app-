import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

# --- 1. 秘密鍵の設定 ---
if "GEMINI_API_KEY" not in st.secrets:
    st.error("StreamlitのSecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# --- 2. 画面構成 ---
st.set_page_config(page_title="AI株価アナリスト", layout="wide")
st.title("🚀 Gemini AI 2.0 専門家仕様・DCF分析")
st.markdown("---")

ticker = st.text_input("銘柄名を入力（例：トヨタ、積水化学）", placeholder="積水化学")

def fetch_analysis(ticker_name):
    # 【最重要修正】モデル名を最新の 2.0 Flash に固定し、世代指定を確実にします
    model = genai.GenerativeModel('models/gemini-2.0-flash')
    
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データ（2024-2025年）を調査し、DCF分析用数値を出力してください。
    回答は必ず以下のJSON形式のみを出力し、説明文は一切含めないでください。
    
    {{
        "company_name": "{ticker_name}",
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
    
    # JSON抽出の精度を上げます
    text = response.text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    else:
        raise ValueError("AIの回答からデータを抽出できませんでした。")

if st.button("AI分析を実行"):
    if not ticker:
        st.warning("銘柄名を入力してください")
    else:
        with st.spinner("最新のGemini 2.0が財務データを解析中..."):
            try:
                data = fetch_analysis(ticker)
                
                # 計算用数値の変換
                cp = float(data['current_price'])
                sh = float(data['shares_outstanding'])
                sales = float(data['sales'])
                wacc = (float(data['risk_free_rate']) + float(data['beta']) * float(data['market_premium'])) / 100
                
                # DCF計算
                fcf_list = []
                pv_sum = 0
                curr_s = sales
                for y in range(1, 6):
                    g = float(data['growth_rate_high']) if y <= 3 else float(data['growth_rate_stable'])
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (float(data['fcf_margin'])/100)
                    fcf_list.append(fcf)
                    pv_sum += fcf / ((1 + wacc)**y)
                
                tg = float(data['terminal_growth']) / 100
                tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                pv_tv = tv / ((1 + wacc)**5)
                
                total_value = (pv_sum + pv_tv) - float(data['net_debt'])
                theoretical_price = total_value / sh
                upside = (theoretical_price / cp - 1) * 100

                # --- 画面表示（ハッキリ見えるデザイン） ---
                st.success(f"### 分析完了: {data['company_name']}")
                
                # タイル形式で数値を表示
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{cp:,.0f}")
                c3.metric("上昇余地", f"{upside:+.1f}%", delta=f"{upside:+.1f}%")

                st.write("#### 将来5年間の予測キャッシュフロー")
                st.bar_chart(pd.DataFrame(fcf_list, index=[f"{y}年目" for y in range(1, 6)], columns=["FCF"]))

                with st.expander("AIの調査根拠データ（詳細）"):
                    st.write(data)

            except Exception as e:
                st.error("分析エラーが発生しました。時間を置いて再試行してください。")
                st.caption(f"エラー詳細: {e}")
