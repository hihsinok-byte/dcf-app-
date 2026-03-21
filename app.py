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

st.info("銘柄名を入れるだけで、Geminiが最新の決算データを検索して分析します。")

ticker = st.text_input("銘柄名または証券コードを入力（例：トヨタ、積水化学）", placeholder="積水化学")

def fetch_financial_data(ticker_name):
    # Google検索ツールを有効化
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        tools=[{"google_search": {}}] 
    )
    
    prompt = f"""
    株式アナリストとしてGoogle検索を行い、{ticker_name}の最新財務データを調査してください。
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
    JSON以外の説明文は一切含めないでください。
    """
    
    response = model.generate_content(prompt)
    res_text = response.text
    
    # AIが余計な説明文を付けてしまった場合のためにJSON部分だけを抜き出す
    json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    else:
        return json.loads(res_text.replace('```json', '').replace('```', '').strip())

if st.button("AIによる自動調査と分析を実行"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("Geminiが最新データを検索・分析中... (10〜20秒ほどかかります)"):
            try:
                data = fetch_financial_data(ticker)
                
                # 計算用変数のセット
                sales = float(data['sales'])
                shares = float(data['shares_outstanding'])
                current_price = float(data['current_price'])
                wacc_pct = (float(data['risk_free_rate']) + float(data['beta']) * float(data['market_premium'])) / 100 
                
                years = [1, 2, 3, 4, 5]
                future_fcf = []
                pv_fcf = 0
                curr_s = sales
                for y in years:
                    g = float(data['growth_rate_high']) if y <= 3 else float(data['growth_rate_stable'])
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (float(data['fcf_margin'])/100)
                    future_fcf.append(fcf)
                    pv_fcf += fcf / ((1 + wacc_pct)**y)
                
                tg = float(data['terminal_growth']) / 100
                tv = (future_fcf[-1] * (1 + tg)) / (wacc_pct - tg)
                pv_tv = tv / ((1 + wacc_pct)**5)
                
                equity_value = (pv_fcf + pv_tv) - float(data['net_debt'])
                theoretical_price = equity_value / shares
                
                # 結果表示
                st.header(f"分析結果: {data['company_name']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{current_price:,.0f}")
                upside = (theoretical_price / current_price - 1) * 100
                c3.metric("上昇余地", f"{upside:+.1f}%")
                
                with st.expander("Geminiの調査データ詳細"):
                    st.table(pd.Series(data).to_frame(name="調査値"))
                
                st.bar_chart(pd.DataFrame({"予測FCF": future_fcf}, index=[f"{y}年目" for y in years]))
                
            except Exception as e:
                st.error("分析中にエラーが発生しました。もう一度実行してみてください。")
                st.caption(f"システム用エラー詳細: {e}")
