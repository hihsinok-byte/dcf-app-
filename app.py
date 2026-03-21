import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="自動DCF分析ツール", layout="wide")
st.title("簡易DCF分析ツール（日本株対応プロトタイプ）")

st.markdown("""
**注意:** `yfinance`を使用して無料でデータを取得しているため、日本株の場合はキャッシュフロー計算書の項目（設備投資など）が欠損している場合があります。その場合、正確な理論株価は算出できません。
""")

# サイドバーで入力
st.sidebar.header("前提条件の入力")
ticker_symbol = st.sidebar.text_input("証券コード（例: トヨタなら 7203.T）", value="7203.T")

# 将来予測のパラメータ
wacc = st.sidebar.slider("割引率 (WACC) %", min_value=1.0, max_value=15.0, value=6.0, step=0.1) / 100
growth_rate = st.sidebar.slider("予測期間中のFCF成長率 %", min_value=-10.0, max_value=20.0, value=2.0, step=0.5) / 100
terminal_growth = st.sidebar.slider("永続成長率 %", min_value=0.0, max_value=5.0, value=1.0, step=0.1) / 100
projection_years = st.sidebar.slider("予測期間（年）", min_value=3, max_value=10, value=5, step=1)

if st.sidebar.button("分析を実行"):
    with st.spinner('データを取得・計算中...'):
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            
            shares_outstanding = info.get('sharesOutstanding')
            current_price = info.get('currentPrice', info.get('previousClose'))
            
            cf = ticker.cashflow
            fcf = None
            if 'Free Cash Flow' in cf.index:
                fcf = cf.loc['Free Cash Flow'].dropna().iloc[0]
            elif 'Operating Cash Flow' in cf.index and 'Capital Expenditure' in cf.index:
                fcf = cf.loc['Operating Cash Flow'].dropna().iloc[0] + cf.loc['Capital Expenditure'].dropna().iloc[0]
            
            if fcf is None or shares_outstanding is None:
                st.error("エラー: 必要な財務データ（FCFまたは発行済株式数）がyfinanceから取得できませんでした。別の銘柄を試すか、手動入力への切り替えが必要です。")
            else:
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
                
                net_debt = info.get('totalDebt', 0) - info.get('totalCash', 0)
                equity_value = enterprise_value - net_debt
                
                intrinsic_value_per_share = equity_value / shares_outstanding
                
                st.success(f"分析完了: {info.get('longName', ticker_symbol)}")
                
                col1, col2 = st.columns(2)
                col1.metric("算出された理論株価", f"¥{intrinsic_value_per_share:,.0f}")
                col2.metric("現在の株価", f"¥{current_price:,.0f}" if current_price else "取得不可")
                
                st.markdown("### 将来FCFの予測推移")
                df_fcf = pd.DataFrame({
                    "年": [f"{i}年目" for i in range(1, projection_years + 1)],
                    "予測FCF": future_fcfs
                })
                st.bar_chart(df_fcf.set_index("年"))

                st.markdown("### 価値の構成")
                st.write(f"- 予測期間のFCF現在価値合計: ¥{pv_of_fcfs:,.0f}")
                st.write(f"- ターミナルバリューの現在価値: ¥{pv_of_tv:,.0f}")
                st.write(f"- 企業価値 (Enterprise Value): ¥{enterprise_value:,.0f}")
                st.write(f"- 株式価値 (Equity Value): ¥{equity_value:,.0f}")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
