import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="自動DCF分析ツール", layout="wide")
st.title("簡易DCF分析ツール（ハイブリッド版）")

st.markdown("""
**【使い方】**
日本株は無料データ（yfinance）だと欠損が多いため、エラーが出る場合やより精緻に分析したい場合は、左側のメニューから「手動入力」に切り替えてIR BANKなどの数値を入力してください。
""")

# サイドバーで入力
st.sidebar.header("前提条件の入力")

input_method = st.sidebar.radio("データ取得方法を選択", ["自動取得 (yfinance)", "手動入力"])

if input_method == "自動取得 (yfinance)":
    ticker_symbol = st.sidebar.text_input("証券コード（例: トヨタなら 7203.T）", value="7203.T")
else:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 手動入力エリア")
    st.sidebar.caption("※入力しやすいよう「百万単位」にしています")
    ticker_symbol = st.sidebar.text_input("銘柄名（表示用）", value="テスト銘柄")
    current_price = st.sidebar.number_input("現在の株価 (円)", value=2000.0, step=100.0)
    shares_outstanding_mil = st.sidebar.number_input("発行済株式数 (百万株)", value=100.0, step=10.0)
    operating_cf_mil = st.sidebar.number_input("営業キャッシュフロー (百万円)", value=10000.0, step=1000.0)
    capex_mil = st.sidebar.number_input("設備投資 (百万円・マイナス値)", value=-3000.0, step=1000.0)
    net_debt_mil = st.sidebar.number_input("純有利子負債 (百万円)", value=5000.0, step=1000.0)
    st.sidebar.markdown("---")

st.sidebar.header("将来予測のパラメータ")
wacc = st.sidebar.slider("割引率 (WACC) %", min_value=1.0, max_value=15.0, value=6.0, step=0.1) / 100
growth_rate = st.sidebar.slider("予測期間中のFCF成長率 %", min_value=-10.0, max_value=20.0, value=2.0, step=0.5) / 100
terminal_growth = st.sidebar.slider("永続成長率 %", min_value=0.0, max_value=5.0, value=1.0, step=0.1) / 100
projection_years = st.sidebar.slider("予測期間（年）", min_value=3, max_value=10, value=5, step=1)

if st.sidebar.button("分析を実行"):
    with st.spinner('計算中...'):
        try:
            # データの準備
            if input_method == "自動取得 (yfinance)":
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.info
                
                shares_outstanding = info.get('sharesOutstanding')
                current_price_val = info.get('currentPrice', info.get('previousClose'))
                
                cf = ticker.cashflow
                fcf = None
                if 'Free Cash Flow' in cf.index:
                    fcf = cf.loc['Free Cash Flow'].dropna().iloc[0]
                elif 'Operating Cash Flow' in cf.index and 'Capital Expenditure' in cf.index:
                    fcf = cf.loc['Operating Cash Flow'].dropna().iloc[0] + cf.loc['Capital Expenditure'].dropna().iloc[0]
                
                net_debt_val = info.get('totalDebt', 0) - info.get('totalCash', 0)
                company_name = info.get('longName', ticker_symbol)
                
            else:
                # 手動入力の値を計算用（円単位）に変換
                shares_outstanding = shares_outstanding_mil * 1000000
                current_price_val = current_price
                fcf = (operating_cf_mil + capex_mil) * 1000000
                net_debt_val = net_debt_mil * 1000000
                company_name = ticker_symbol

            # データが揃っているかチェック
            if fcf is None or shares_outstanding is None:
                st.error("エラー: yfinanceから必要なデータが取得できませんでした。「手動入力」に切り替えて実行してください。")
            else:
                # DCFの計算ロジック
                future_fcfs = []
                pv_of_fcfs = 0
                current_fcf = fcf
                
                for year in range(1, projection_years + 1):
                    projected_fcf = current_fcf * ((1 + growth_rate) ** year)
                    discounted_fcf = projected_fcf / ((1 + wacc) ** year)
                    future_fcfs.append(projected_fcf)
                    pv_of_fcfs += discounted_fcf
                
                final_year_fcf = future_fcfs[-1]
                terminal_value = (final_year_fcf * (1 + terminal_growth)) / (wacc - terminal_growth)
                pv_of_tv = terminal_value / ((1 + wacc) ** projection_years)
                
                enterprise_value = pv_of_fcfs + pv_of_tv
                
                equity_value = enterprise_value - net_debt_val
                
                intrinsic_value_per_share = equity_value / shares_outstanding
                
                # 結果の表示
                st.success(f"分析完了: {company_name}")
                
                col1, col2 = st.columns(2)
                col1.metric("算出された理論株価", f"¥{intrinsic_value_per_share:,.0f}")
                col2.metric("現在の株価", f"¥{current_price_val:,.0f}" if current_price_val else "取得不可")
                
                st.markdown("### 将来FCFの予測推移")
                df_fcf = pd.DataFrame({
                    "年": [f"{i}年目" for i in range(1, projection_years + 1)],
                    "予測FCF": future_fcfs
                })
                st.bar_chart(df_fcf.set_index("年"))

                st.markdown("### 価値の構成")
                st.write(f"- 基準となるFCF（直近）: ¥{fcf:,.0f}")
                st.write(f"- 予測期間のFCF現在価値合計: ¥{pv_of_fcfs:,.0f}")
                st.write(f"- ターミナルバリューの現在価値: ¥{pv_of_tv:,.0f}")
                st.write(f"- 企業価値 (Enterprise Value): ¥{enterprise_value:,.0f}")
                st.write(f"- 株式価値 (Equity Value): ¥{equity_value:,.0f}")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
