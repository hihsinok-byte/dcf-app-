import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

# 秘密鍵の読み込み
if "GEMINI_API_KEY" not in st.secrets:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.set_page_config(page_title="Gemini AI DCF分析", layout="wide")
st.title("🚀 Gemini AI 精緻DCF分析ツール")

ticker = st.text_input("銘柄名を入力してください（例：トヨタ、積水化学）", placeholder="トヨタ自動車")

def fetch_financial_data(ticker_name):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データ（2024-2025年）を調査し、DCF分析用数値を出力してください。
    回答は必ず以下のJSON形式のみを出力してください。
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
    json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    else:
        raise ValueError("データの解析に失敗しました。")

if st.button("分析を実行する"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("AIが財務データを精査中..."):
            try:
                data = fetch_financial_data(ticker)
                
                # 数値計算
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
                upside = (theoretical_price / current_price - 1) * 100

                # --- 【ここから表示の強化】 ---
                st.success(f"### 分析完了: {data['company_name']}")
                
                # 大きなカード形式で数値を表示
                st.markdown(f"""
                <div style="background-color: #1e2130; padding: 20px; border-radius: 10px; border: 1px solid #3b82f6; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-around; text-align: center;">
                        <div>
                            <p style="color: #7a9ab8; font-size: 14px; margin-bottom: 5px;">理論株価</p>
                            <p style="color: #22d3ee; font-size: 32px; font-weight: bold; margin: 0;">¥{theoretical_price:,.0f}</p>
                        </div>
                        <div>
                            <p style="color: #7a9ab8; font-size: 14px; margin-bottom: 5px;">現在株価</p>
                            <p style="color: #e2eaf4; font-size: 32px; font-weight: bold; margin: 0;">¥{current_price:,.0f}</p>
                        </div>
                        <div>
                            <p style="color: #7a9ab8; font-size: 14px; margin-bottom: 5px;">上昇余地</p>
                            <p style="color: {'#34d399' if upside > 0 else '#f87171'}; font-size: 32px; font-weight: bold; margin: 0;">{upside:+.1f}%</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # グラフも表示
                st.write("### 5年間の予測フリーキャッシュフロー (百万円)")
                chart_data = pd.DataFrame({"予測FCF": future_fcf}, index=[f"{y}年目" for y in range(1, 6)])
                st.bar_chart(chart_data)

                with st.expander("AIが算出した前提条件を確認"):
                    st.table(pd.Series(data).to_frame(name="調査数値"))
                
            except Exception as e:
                st.error(f"エラー: {e}")
