import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import re

# --- 1. 接続設定 ---
if "GEMINI_API_KEY" not in st.secrets:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.set_page_config(page_title="AI株価アナリスト", layout="wide")
st.title("🚀 Gemini AI 2.0 専門家仕様 (完全エラー対策版)")

ticker = st.text_input("銘柄名を入力", placeholder="トヨタ自動車")

# 【改良1】マイナスの数値や、カンマ混じりの文字を安全な数字に変換する機能
def clean_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    # マイナス記号と数字と小数点だけを残す
    cleaned = re.sub(r'[^\d.-]', '', str(value))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def fetch_analysis(ticker_name):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    株式アナリストとして、{ticker_name}の最新財務データ（2024-2025年）を調査し、DCF分析用数値を出力してください。
    必ず以下のJSON形式のみを出力してください。単位（円など）やカンマは含めず、純粋な数値のみにしてください。
    
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
    
    # 【改良2】AIに「絶対にJSON形式以外喋らない」よう強制する設定
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
        )
    )
    return json.loads(response.text)

if st.button("AI分析を実行"):
    if not ticker:
        st.warning("銘柄名を入力してください")
    else:
        with st.spinner("AIが財務データを安全に計算中..."):
            try:
                data = fetch_analysis(ticker)
                
                # 【改良3】データが欠けていてもエラーにならないよう安全に取り出す
                cp = clean_float(data.get('current_price', 0))
                sh = clean_float(data.get('shares_outstanding', 0))
                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                
                rf = clean_float(data.get('risk_free_rate', 0))
                beta = clean_float(data.get('beta', 0))
                mp = clean_float(data.get('market_premium', 0))
                
                # WACCの計算とエラー防止（WACCが0以下になるのを防ぐ）
                wacc = (rf + beta * mp) / 100
                if wacc <= 0:
                    wacc = 0.05 
                
                fcf_margin = clean_float(data.get('fcf_margin', 0))
                g_high = clean_float(data.get('growth_rate_high', 0))
                g_stable = clean_float(data.get('growth_rate_stable', 0))
                tg_val = clean_float(data.get('terminal_growth', 0))
                
                # DCF計算
                fcf_list = []
                pv_sum = 0
                curr_s = sales
                for y in range(1, 6):
                    g = g_high if y <= 3 else g_stable
                    curr_s *= (1 + g/100)
                    fcf = curr_s * (fcf_margin/100)
                    fcf_list.append(fcf)
                    pv_sum += fcf / ((1 + wacc)**y)
                
                # 【改良4】永久成長率がWACCを超えて計算不能になるエラーを防ぐ
                tg = tg_val / 100
                if wacc <= tg:
                    tg = wacc - 0.01

                tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                pv_tv = tv / ((1 + wacc)**5)
                
                total_value = (pv_sum + pv_tv) - debt
                
                # 理論株価の計算（株式数が0の場合は計算しない）
                theoretical_price = total_value / sh if sh > 0 else 0
                
                # 上昇余地の計算（現在株価が0の場合は計算しない）
                upside = 0
                if cp > 0:
                    upside = (theoretical_price / cp - 1) * 100

                # --- 画面表示 ---
                st.success(f"### 分析完了: {data.get('company_name', ticker)}")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("理論株価", f"¥{theoretical_price:,.0f}")
                c2.metric("現在株価", f"¥{cp:,.0f}")
                c3.metric("上昇余地", f"{upside:+.1f}%", delta=f"{upside:+.1f}%")

                st.write("#### 将来予測キャッシュフロー (グラフ)")
                st.bar_chart(pd.DataFrame(fcf_list, index=[f"{y}年目" for y in range(1, 6)], columns=["FCF"]))
                
                with st.expander("AIの調査データ内訳（これに基づき計算しました）"):
                    st.write(data)

            except Exception as e:
                st.error("分析を完了できませんでした。AIが取得したデータに一時的な異常があります。")
                st.caption(f"エラー詳細: {e}")
