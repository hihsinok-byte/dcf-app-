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
st.title("🚀 Gemini AI 2.5 プロ投資家仕様 (株式分割・自動補正版)")

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
    あなたはプロの証券アナリストです。{ticker_name}の直近の財務データを基に、DCF分析に必要な数値を算出して出力してください。
    
    【重要】
    ・金額や株数などは省略単位を使わず、必ず「1の位」までのフル桁数で出力してください。
    ・日本の銘柄の場合、yahoo_ticker は必ず「証券コード4桁.T」の形式にしてください（例：トヨタ自動車なら 7203.T）。
    ・金融子会社を持つ企業の場合、net_debt（純有利子負債）から「金融事業の負債」は除外して見積もってください。
    
    必ず以下のJSON形式のみを出力してください。
    {{
        "company_name": "{ticker_name}",
        "yahoo_ticker": "7203.T",
        "current_price_fallback": 最新の株価(円),
        "shares_outstanding_fallback": 発行済株式総数(株),
        "net_debt": 有利子負債 - 現金同等物(フル桁数),
        "sales": 直近の年間売上高(フル桁数),
        "fcf_margin": 売上高に対するフリーキャッシュフロー・マージン(%),
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
        with st.spinner("AIが財務データを解析し、市場の最新株式数（分割反映済）を取得中..."):
            try:
                data = fetch_analysis(ticker)
                
                # --- 1. リアルデータの取得 (yfinance) ---
                cp = clean_float(data.get('current_price_fallback', 0))
                sh = clean_float(data.get('shares_outstanding_fallback', 0))
                data_source_msg = "⚠️ リアルタイムデータの取得に失敗したため、AIの予測値を使用しています。"
                
                try:
                    ticker_symbol = data.get('yahoo_ticker', '')
                    # 証券コードだけの入力だった場合、自動で .T を補完する
                    if ticker_symbol and not ticker_symbol.endswith('.T') and ticker_symbol.isdigit():
                        ticker_symbol += '.T'
                        
                    if ticker_symbol:
                        yf_ticker = yf.Ticker(ticker_symbol)
                        info = yf_ticker.info
                        
                        # 株価の取得
                        if 'currentPrice' in info and info['currentPrice'] is not None:
                            cp = float(info['currentPrice'])
                        elif 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                            cp = float(info['regularMarketPrice'])
                            
                        # 【重要】分割反映済みの最新株式数を取得
                        if 'sharesOutstanding' in info and info['sharesOutstanding'] is not None:
                            sh = float(info['sharesOutstanding'])
                            data_source_msg = f"✅ 市場から最新の株価と株式数（分割反映済み: {sh:,.0f}株）を取得し、計算に適用しました。"
                except Exception as e:
                    pass

                # --- 2. 共通パラメータ ---
                sales = clean_float(data.get('sales', 0))
                debt = clean_float(data.get('net_debt', 0))
                fcf_margin = clean_float(data.get('fcf_margin', 0))
                
                rf = clean_float(data.get('risk_free_rate', 0))
                beta = clean_float(data.get('beta', 0))
                mp = clean_float(data.get('market_premium', 0))
                wacc = (rf + beta * mp) / 100
                if wacc <= 0: wacc = 0.05 
                
                tg_val = clean_float(data.get('terminal_growth', 0))
                tg = tg_val / 100
                if wacc <= tg: tg = wacc - 0.01

                # --- 3. 安定DCF計算関数 ---
                def calculate_scenario(growth_rate):
                    fcf_list = []
                    pv_sum = 0
                    curr_s = sales
                    for y in range(1, 6):
                        curr_s *= (1 + growth_rate/100)
                        fcf = curr_s * (fcf_margin/100)
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
                
                # データ取得が成功したかどうかを画面に表示
                if "✅" in data_source_msg:
                    st.info(data_source_msg)
                else:
                    st.warning(data_source_msg)

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

                with st.expander("AI調査データ内訳 (フル桁数)"):
                    st.write("WACC (加重平均資本コスト):", f"{wacc*100:.2f}%")
                    st.write(data)

            except Exception as e:
                st.error("分析エラーが発生しました。")
                st.caption(f"エラー詳細: {e}")
