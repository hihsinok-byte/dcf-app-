import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="AI診断ツール", layout="wide")
st.title("🛠️ システム診断ツール")
st.write("現在のAPIキーで、実際に利用可能なAIモデルを直接調査しています...")

if "GEMINI_API_KEY" not in st.secrets:
    st.error("SecretsにGEMINI_API_KEYが設定されていません。")
else:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    try:
        # 使えるモデルをすべて取得してリスト化する
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if available_models:
            st.success("✅ 以下のモデルが利用可能です！この中から一番上の名前を教えてください。")
            for name in available_models:
                st.code(name)
        else:
            st.error("❌ 利用可能なモデルが一つもありません。APIキーの設定自体や、Googleアカウントの制限が原因です。")
            
    except Exception as e:
        st.error("❌ 調査中にエラーが発生しました。APIキーが無効である可能性があります。")
        st.caption(f"エラー詳細: {e}")
