import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

# --- 1. 秘密鍵の設定 ---
try:
    # 以前設定いただいた Secrets からキーを取得
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except Exception:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")

# --- 2. 画面構成の設定 ---
st.set_page_config(page_title="AI株価アナリスト", layout="wide")
st.title("🚀 Gemini AI 2.0 精緻DCF分析ツール")
st.markdown("---")

# 銘柄入力
ticker = st.text_input("銘柄名を入力（例：トヨタ自動車、積水化学）", placeholder="積水化学")

# --- 3. AIによるデータ取得関数 ---
def get_ai_analysis(ticker_name):
    # 最新の 2.0 Flash モデルを使用
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データを調査し、DCF分析用数値を出力してください。
    回答は必ず以下のJSON形式のみを出力してください。説明は一切不要です。
    
    {{
        "company_name": "{ticker_name}",
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
    """
    
    response = model.generate_content(prompt)
    # AIの返答からJSONだけを抜き出す
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if not match:
        raise ValueError("AIからの回答が読み取れませんでした。")
    return json.loads(match.group())

# --- 4. メイン処理 ---
if st.button("AI分析を実行する"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("Gemini 2.0 が最新データを分析中..."):
            try:
                res = get_ai_analysis(ticker)
                
                # 数値の整理
                cp = float(res['current_price'])
                sh = float(res['shares_outstanding'])
                debt = float(res['net_debt'])
                sales = float(res['sales'])
                wacc = (float(res['risk_free_rate']) + float(res['beta']) * float(res['market_premium'])) / 100
                
                # DCF計算（5年分）
                fcf_list = []
                pv_sum = 0
                curr_s = sales
                for y in range(1, 6):
                    g = float(res['growth_rate_high']) if y <= 3 else float(res['growth_rate_stable'])
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (float(res['fcf_margin'])/100)
                    fcf_list.append(fcf)
                    pv_sum += fcf / ((1 + wacc)**y)
                
                tg = float(res['terminal_growth']) / 100
                tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                pv_tv = tv / ((1 + wacc)**5)
                
                value = (pv_sum + pv_tv) - debt
                theoretical_price = value / sh
                upside = (theoretical_price / cp - 1) * 100

                # --- 画面表示（デザインを強化） ---
                st.success(f"### 分析完了: {res['company_name']}")
                
                # 指標をタイル表示
                col1, col2, col3 = st.columns(3)
                col1.metric("算出された理論株価", f"¥{theoretical_price:,.0f}")
                col2.metric("現在の株価", f"¥{cp:,.0f}")
                col3.metric("上昇余地", f"{upside:+.1f}%", delta=f"{upside:+.1f}%")

                # グラフ
                st.write("#### 将来フリーキャッシュフロー予測（百万円）")
                df_fcf = pd.DataFrame({"FCF": fcf_list}, index=[f"{y}年目" for y in range(1, 6)])
                st.bar_chart(df_fcf)

                with st.expander("AIが調査した財務パラメータの詳細"):
                    st.write(res)

            except Exception as e:
                st.error(f"分析中にエラーが発生しました。")
                st.caption(f"技術的なエラー詳細: {e}")
