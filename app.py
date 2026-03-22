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

st.set_page_config(page_title="AI株価アナリスト PRO", layout="wide")
st.title("🚀 Gemini AI 2.5 プロ投資家仕様 (全部入り完成版)")

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
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"""
    あなたはプロの証券アナリストです。{ticker_name}の直近の財務データを基に、本格的なDCF分析に必要な数値を算出して出力してください。
    
    【重要】金額や株数などは省略単位を使わず、必ず「1の位」までのフル桁数で出力してください。
    
    必ず以下のJSON形式のみを出力してください。
    {{
        "company_name": "{ticker_name}",
        "yahoo_ticker": "日本の銘柄は 7203.T のように.Tをつける。米国株はAAPLなど。",
        "current_price_fallback": 最新の株価(円またはドル),
        "shares_outstanding_fallback": 発行済株式総数(株),
        "net_debt": 有利子負債 - 現金同等物(フル桁数),
        "sales": 直近の年間売上高(フル桁数),
        "ebit_margin": 営業利益率(%),
        "tax_rate": 実効税率(%),
        "da_margin": 売上高に対する減価償却費の割合(%),
        "capex_margin": 売上高に対する設備投資の割合(%),
        "nwc_margin": 売上高に対する運転資本増減の割合(%),
        "growth_rate_bull": 楽観的（強気）な今後3年間の売上高成長率(%),
        "growth_rate_base": 基本的な今後3年間の売上高成長率(%),
        "growth_rate_bear": 悲観的（弱気）な今後3年間の売上高成長率(%),
        "terminal_growth": 永久成長率(%),
        "risk_free_rate": 無リスク利子率(%),
        "beta": ベータ値,
        "market_premium": マーケットリスクプレミアム(%)
    }}
    """
    response = model.generate_content(prompt)
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("AIの回答からデータを抽出できませんでした。")

if st.button("AI本格分析を実行"):
    if not ticker:
        st.warning("銘柄名を入力してください")
    else:
        with st.spinner("AIが財務データを解析し、市場のリアルタイムデータを取得中..."):
            try:
                data = fetch_analysis(ticker)
                
                # --- 1. リアルデータの取得 (yfinance) ---
                cp = clean_float(data.get('current_price_fallback', 0))
                sh = clean_float(data.get('shares_outstanding_fallback', 0))
                
                try:
                    # AIが出したティッカーコードで市場から正確な株価と株数を取得
                    if 'yahoo_ticker' in data and data['yahoo_ticker']:
                        yf_ticker = yf.Ticker(data['yahoo_ticker'])
                        info = yf_ticker.info
                        if 'currentPrice' in info and info['currentPrice'] is not None:
                            cp = float(info['currentPrice'])
                        if 'sharesOutstanding' in info and info['sharesOutstanding'] is not None:
                            sh = float(info['sharesOutstanding'])
                except:
                    pass # 取得失敗時はAIの予測値（フォールバック）を使用

                # --- 2. 共通パラメータの準備 ---
                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                ebit_margin = clean_float(data.get('ebit_margin', 0))
                tax_rate = clean_float(data.get('tax_rate', 0))
                da_margin = clean_float(data.get('da_margin', 0))
                capex_margin = clean_float(data.get('capex_margin', 0))
                nwc_margin = clean_float(data.get('nwc_margin', 0))
                
                rf = clean_float(data.get('risk_free_rate', 0))
                beta = clean_float(data.get('beta', 0))
                mp = clean_float(data.get('market_premium', 0))
                wacc = (rf + beta * mp) / 100
                if wacc <= 0: wacc = 0.05 
                
                tg_val = clean_float(data.get('terminal_growth', 0))
                tg = tg_val / 100
                if wacc <= tg: tg = wacc - 0.01

                # --- 3. 本格DCF計算関数 (営業利益・税金・設備投資を考慮) ---
                def calculate_scenario(growth_rate):
                    fcf_list = []
                    pv_sum = 0
                    curr_s = sales
                    for y in range(1, 6):
                        curr_s *= (1 + growth_rate/100)
                        ebit = curr_s * (ebit_margin/100)
                        nopat = ebit * (1 - tax_rate/100)
                        da = curr_s * (da_margin/100)
                        capex = curr_s * (capex_margin/100)
                        nwc = curr_s * (nwc_margin/100)
                        
                        fcf = nopat + da - capex - nwc
                        fcf_list.append(fcf)
                        pv_sum += fcf / ((1 + wacc)**y)
                        
                    tv = (fcf_list[-1] * (1 + tg)) / (wacc - tg)
                    pv_tv = tv / ((1 + wacc)**5)
                    total_value = (pv_sum + pv_tv) - debt
                    price = total_value / sh if sh > 0 else 0
                    upside = (price / cp - 1) * 100 if cp > 0 else 0
                    return price, upside, fcf_list

                # 3つのシナリオを計算
                bull_price, bull_up, bull_fcf = calculate_scenario(clean_float(data.get('growth_rate_bull', 0)))
                base_price, base_up, base_fcf = calculate_scenario(clean_float(data.get('growth_rate_base', 0)))
                bear_price, bear_up, bear_fcf = calculate_scenario(clean_float(data.get('growth_rate_bear', 0)))

                # --- 画面表示 ---
                st.success(f"### 分析完了: {data.get('company_name', ticker)} ({data.get('yahoo_ticker', '')})")
                st.caption("※現在の株価と発行済株式数は市場からリアルタイム取得しています（取得失敗時はAI予測値を使用）")

                # シナリオをタブで切り替え表示
                tab1, tab2, tab3 = st.tabs(["📊 基本シナリオ (Base)", "🚀 強気シナリオ (Bull)", "📉 弱気シナリオ (Bear)"])
                
                with tab1:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("基本理論株価", f"¥{base_price:,.0f}")
                    c2.metric("現在株価", f"¥{cp:,.0f}")
                    c3.metric("上昇余地", f"{base_up:+.1f}%", delta=f"{base_up:+.1f}%")
                    st.bar_chart(pd.DataFrame([f / 100000000 for f in base_fcf], index=[f"{y}年目" for y in range(1, 6)], columns=["FCF (億円)"]))

                with tab2:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("強気理論株価", f"¥{bull_price:,.0f}")
                    c2.metric("現在株価", f"¥{cp:,.0f}")
                    c3.metric("上昇余地", f"{bull_up:+.1f}%", delta=f"{bull_up:+.1f}%")
                    st.bar_chart(pd.DataFrame([f / 100000000 for f in bull_fcf], index=[f"{y}年目" for y in range(1, 6)], columns=["FCF (億円)"]))

                with tab3:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("弱気理論株価", f"¥{bear_price:,.0f}")
                    c2.metric("現在株価", f"¥{cp:,.0f}")
                    c3.metric("上昇余地", f"{bear_up:+.1f}%", delta=f"{bear_up:+.1f}%")
                    st.bar_chart(pd.DataFrame([f / 100000000 for f in bear_fcf], index=[f"{y}年目" for y in range(1, 6)], columns=["FCF (億円)"]))

                with st.expander("プロフェッショナル財務パラメータ詳細"):
                    st.write("WACC (加重平均資本コスト):", f"{wacc*100:.2f}%")
                    st.write(data)

            except Exception as e:
                st.error("分析エラーが発生しました。")
                st.caption(f"エラー詳細: {e}")
