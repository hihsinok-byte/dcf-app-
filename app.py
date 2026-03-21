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
    # 【重要】検索機能(google_search)を有効にしてモデルを呼び出す
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        tools=[{"google_search": {}}] 
    )
    
    prompt = f"""
    あなたはプロの株式アナリストです。Google検索を駆使して、{ticker_name}の最新の財務データ（2024年度または2025年最新）を調査してください。
    
    以下の項目を必ず調べ、JSON形式のみで回答してください。
    - company_name: 会社名
    - current_price: 現在株価(円)
    - shares_outstanding: 発行済株式数(百万株単位)
    - net_debt: ネット有利子負債(百万円単位)
    - sales: 直近売上高(百万円単位)
    - fcf_margin: 売上高に対するフリーキャッシュフローの比率(%)
    - growth_rate_high: 今後3年の予測成長率(%)
    - growth_rate_stable: 4-5年目の予測成長率(%)
    - terminal_growth: 永続成長率(%)
    - risk_free_rate: リスクフリーレート(%)
    - beta: ベータ値
    - market_premium: 株式リスクプレミアム(%)
    
    JSONデータ以外の説明文は一切含めないでください。
    """
    
    response = model.generate_content(prompt)
    # AIの回答からJSON部分を抽出して解析
    res_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(res_text)

if st.button("AIによる自動調査と分析を実行"):
    if not ticker:
        st.warning("銘柄を入力してください")
    else:
        with st.spinner("Geminiが最新データを検索・分析中..."):
            try:
                data = fetch_financial_data(ticker)
                
                # 数値の取り出し
                sales = data['sales']
                shares = data['shares_outstanding']
                current_price = data['current_price']
                wacc_pct = (data['risk_free_rate'] + data['beta'] * data['market_premium']) / 100 
                
                # DCF計算
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
                
                # 表示
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
                # 具体的なエラー内容を表示して原因を突き止めやすくします
                st.error(f"分析中にエラーが発生しました。時間を置いて再度お試しください。")
                st.caption(f"詳細エラー: {e}")
