import streamlit as st
import time
import pandas as pd
import plotly.express as px
import numpy as np
import urllib.request
import json
import os
from datetime import date
import requests
import streamlit_authenticator as stauth
from supabase import create_client, Client
import urllib.parse
import xml.etree.ElementTree as ET
import yfinance as yf
import plotly.graph_objects as go
import google.generativeai as genai

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS
# ==========================================
st.set_page_config(page_title="InvestiCortes Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    div[data-testid="metric-container"] { background-color: rgba(40, 40, 40, 0.4); border: 1px solid rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 8px; box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2); }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { padding: 1rem; }
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# Token Global da BRAPI
TOKEN_BRAPI = "ggEB4pbTMNTydMJmFNKX6M"

def padronizar_grafico(fig):
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.95)", font_color="white", font_size=14, bordercolor="#444"),
        font=dict(color="#E0E0E0"), margin=dict(t=50, l=10, r=10, b=10)
    )
    return fig

# ==========================================
# ⚡ MOTOR DE DADOS (HÍBRIDO: BRAPI + YFINANCE)
# ==========================================

@st.cache_data(ttl=86400, show_spinner=False)
def buscar_tickers_brapi(pesquisa=None):
    """Busca a lista oficial de ações direto na API da B3."""
    url = f"https://brapi.dev/api/quote/list?token={TOKEN_BRAPI}"
    if pesquisa: url += f"&search={pesquisa}"
    try:
        resp = requests.get(url, timeout=10).json()
        return[acao['stock'] for acao in resp.get('stocks', [])]
    except:
        return ["PETR4", "VALE3", "ITUB4", "BBDC4", "WEGE3"] # Fallback de emergência

@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_atual(ticker):
    """Cotação em tempo real B3 (via BRAPI)"""
    ticker_limpo = ticker.replace('.SA', '')
    url = f"https://brapi.dev/api/quote/{ticker_limpo}?token={TOKEN_BRAPI}"
    try:
        dados = requests.get(url, timeout=5).json()
        return float(dados['results'][0]['regularMarketPrice'])
    except:
        # Fallback YFinance se BRAPI falhar
        try: return float(yf.Ticker(ticker_limpo + ".SA").fast_info['lastPrice'])
        except: return 0.0

@st.cache_data(ttl=3600, show_spinner=False)
def obter_dividendos(ticker):
    """Busca dividendos reais (Híbrido YFinance + BRAPI) e remove fusos horários de forma segura"""
    ticker_limpo = ticker.replace('.SA', '')
    
    # 1. Tenta YFinance (É o mais rápido e confiável para histórico de proventos)
    try:
        acao = yf.Ticker(ticker_limpo + ".SA")
        divs = acao.dividends
        if not divs.empty:
            divs.index = divs.index.tz_localize(None) # ⏰ A MÁGICA: Arranca o fuso horário fora!
            return divs
    except: pass
    
    try:
        url = f"https://brapi.dev/api/quote/{ticker_limpo}?token={TOKEN_BRAPI}&dividends=true"
        dados = requests.get(url, timeout=5).json()
        divs_list = dados['results'][0].get('dividendsData', {}).get('cashDividends',[])
        if divs_list:
            df = pd.DataFrame(divs_list)
            col_valor = 'rate' if 'rate' in df.columns else 'assetIssuedDividend'
            df['date'] = pd.to_datetime(df['paymentDate']).dt.tz_localize(None) # ⏰ Sem fuso!
            df.set_index('date', inplace=True)
            return df[col_valor]
    except: pass
    return pd.Series()

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados_historicos(tickers, start=None, end=None, period="1y"):
    """
    Motor Histórico via YFinance. 
    (YFinance é imbatível para gráficos de linha longos, CDI, Dólar e Monte Carlo).
    """
    if isinstance(tickers, str): tickers = [tickers]
    tickers_yf = [t + ".SA" if not t.endswith('.SA') and not t.startswith('^') and "=" not in t else t for t in tickers]
    try:
        df = yf.download(tickers_yf, start=start, end=end, period=period, progress=False)['Close']
        if isinstance(df, pd.Series): df = df.to_frame(name=tickers[0])
        df.columns = tickers # Devolve os nomes originais para o sistema
        return df.ffill().dropna()
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados_historicos(tickers, start=None, end=None, period="1y"):
    """Motor Histórico YFinance blindado contra ações novas e falhas de ordenação"""
    if isinstance(tickers, str): tickers = [tickers]
    tickers_yf = [t + ".SA" if not t.endswith('.SA') and not t.startswith('^') and "=" not in t else t for t in tickers]
    try:
        kwargs = {'progress': False}
        if start and end: kwargs['start'], kwargs['end'] = start, end
        else: kwargs['period'] = period
            
        df = yf.download(tickers_yf, **kwargs)['Close']
        
        if isinstance(df, pd.Series): df = df.to_frame(name=tickers[0])
        else:
            mapa_nomes = {yf_ticker: original for yf_ticker, original in zip(tickers_yf, tickers)}
            df.rename(columns=mapa_nomes, inplace=True)
        return df.ffill()
    except Exception as e: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_cripto(ticker):
    moeda = str(ticker).upper().strip().split('-')[0]
    try:
        req = urllib.request.Request(f"https://www.mercadobitcoin.net/api/{moeda}/ticker/", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return float(json.loads(response.read().decode())['ticker']['last'])
    except: return 0.0

@st.cache_data(ttl=86400, show_spinner=False)
def carregar_cdi_historico(data_inicio, data_fim):
    try:
        url_cdi = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={data_inicio}&dataFinal={data_fim}"
        df_cdi = pd.read_json(url_cdi)
        df_cdi['data'] = pd.to_datetime(df_cdi['data'], dayfirst=True)
        df_cdi.set_index('data', inplace=True)
        return df_cdi
    except: return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def buscar_pvp_fiis(lista_fiis_config):
    """Calcula P/VP e define Status semântico para cada setor"""
    dados = []
    for fii, segmento in lista_fiis_config.items():
        try:
            ticker_nome = f"{fii.strip()}.SA"
            info = yf.Ticker(ticker_nome).info
            preco_atual = info.get('previousClose') or info.get('regularMarketPrice') or 0.0
            vpa = info.get('bookValue') or 0.0
            pvp = info.get('priceToBook')
            if (pvp is None or pvp == 0) and vpa > 0: pvp = preco_atual / vpa
            dy_bruto = info.get('dividendYield') or info.get('trailingAnnualDividendYield', 0.0)
            dy_pct = (dy_bruto if (dy_bruto and dy_bruto > 1) else (dy_bruto * 100 if dy_bruto else 0.0))

            if pvp and pvp > 0:
                if segmento == 'Papel':
                    status_texto = "🟢 Paridade" if 0.98 <= pvp <= 1.02 else ("🟠 Alerta: Risco" if pvp < 0.98 else "🔴 Ágio")
                else:
                    status_texto = "🟢 Desconto" if pvp < 1.0 else "🔴 Ágio"
                dados.append({'FII': fii, 'Tipo': segmento, 'Preço': preco_atual, 'VPA': vpa, 'P/VP': pvp, 'DY Anual (%)': dy_pct, 'DY Mensal Est. (%)': dy_pct / 12, 'Status': status_texto})
        except: continue
    return pd.DataFrame(dados)

@st.cache_data(ttl=600)
def scanner_volume_atipico():
    """Scanner de alta sensibilidade com redundância de dados"""
    tickers = [
        'VALE3.SA', 'PETR4.SA', 'ITUB4.SA', 'BBDC4.SA', 'ABEV3.SA', 'MGLU3.SA', 
        'B3SA3.SA', 'BBAS3.SA', 'RENT3.SA', 'WEGE3.SA', 'HAPV3.SA', 'GGBR4.SA', 
        'PRIO3.SA', 'ELET3.SA', 'SUZB3.SA', 'CSAN3.SA', 'LREN3.SA', 'RADL3.SA',
        'RAIL3.SA', 'JBSS3.SA', 'VBBR3.SA', 'CPLE6.SA', 'EQTL3.SA'
    ]
    
    import datetime
    agora = datetime.datetime.now()
    inicio = agora.replace(hour=10, minute=0, second=0)
    minutos_passados = max((agora - inicio).total_seconds() / 60, 1)
    proporcao_esperada = min(minutos_passados / 420, 1.0)

    anomalias = []
    
    try:
        data = yf.download(tickers, period="5d", interval="5m", progress=False)
        if data.empty: return pd.DataFrame()
        for t in tickers:
            try:
                # Volume de hoje (últimas colunas do dataframe de 5m)
                hoje_v = vol_data[t].dropna()
                hoje_p = close_data[t].dropna()
                
                if hoje_v.empty: continue
                
                vol_hoje = hoje_v.sum()
                preco_atual = hoje_p.iloc[-1]
                preco_abertura = hoje_p.iloc[0]
                
                # Média de 20 dias (Download separado para estabilidade)
                hist = yf.Ticker(t).history(period="25d")
                media_vol_20d = hist['Volume'].iloc[-21:-1].mean()
                
                vol_esperado = media_vol_20d * proporcao_esperada
                rvol = vol_hoje / vol_esperado if vol_esperado > 0 else 0
                var_dia = ((preco_atual / preco_abertura) - 1) * 100
                
                # Baixamos o sarrafo: se tiver 80% do volume esperado, já entra na lista
                if rvol > 0.8:
                    fluxo = "🏦 Institucional" if rvol > 1.2 else "⚖️ Fluxo Normal"
                    fluxo += " (Compra)" if var_dia > 0.2 else (" (Venda)" if var_dia < -0.2 else " (Lateral)")

                    # --- NOVO CDN DE LOGOS (Mais estável para B3) ---
                    ticker_limpo = t.replace('.SA', '').upper()
                    # Fonte alternativa muito estável da Itau Corretora
                    logo_url = f"https://static.itaucpa.com.br/itau-corretora/logos-acoes/{ticker_limpo}.png"

                    anomalias.append({
                        'Logo': logo_url,
                        'Ativo': ticker_limpo,
                        'Ritmo (RVOL)': f"{rvol:.2f}x",
                        'Variação': f"{var_dia:+.2f}%",
                        'Análise de Fluxo': fluxo,
                        'score': rvol
                    })
            except: continue
    except: pass
    df = pd.DataFrame(anomalias)
    return df.sort_values(by='score', ascending=False).head(8).drop(columns=['score']) if not df.empty else pd.DataFrame()

def style_pvp_inteligente(row):
    status = row['Status']
    
    # Mapeamento direto de Cor por Texto de Status
    if "🟢" in status:
        return ['color: #00CC96; font-weight: bold'] * len(row) # Verde
    elif "🟠" in status:
        return ['color: #FFA500; font-weight: bold'] * len(row) # Laranja
    else:
        return ['color: #EF553B; font-weight: bold'] * len(row) # Vermelho
# ==========================================
# 🔐 CONEXÃO BANCO DE DADOS E AUTENTICAÇÃO
# ==========================================
try:
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY")
    if not url or not key:
        st.error("⚠️ Banco de dados não configurado. Adicione SUPABASE_URL e SUPABASE_KEY no secrets.toml.")
        st.stop()
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Erro ao inicializar o Supabase: {e}")
    st.stop()

credentials = {
    "usernames": { "admin": { "name": "Pedro Admin", "password": "$2b$12$eaa2xg5WmNGWTfJL8Y09buVjlBAThqlMwsogcnyYfUFodd3VZt6jO" } }
}
authenticator = stauth.Authenticate(credentials, "investimentos_dashboard", "chave_secreta_123", cookie_expiry_days=30)

# ==========================================
# 🧭 MENU LATERAL (NAVEGAÇÃO E FORMULÁRIO)
# ==========================================
with st.sidebar:
    st.title("💼 Investimentos")
    aba_selecionada = st.radio("Navegação",["🏠 Home (Mercado)", "📊 Minha Carteira"])
    
    if st.session_state.get("authentication_status"):
        st.divider()
        st.subheader("➕ Nova Transação")
        
        lista_acoes = buscar_tickers_brapi()
        lista_acoes_atual = ["BTC", "ETH", "SOL", "USDT"] + lista_acoes
        
        # TIRAMOS O MERCADO DO FORMULÁRIO PARA A TELA FICAR DINÂMICA
        f_mercado = st.selectbox("Mercado", ["B3 (Ações/FIIs)", "Criptomoedas", "Renda Fixa"])
        
        with st.form("form_nova_transacao", clear_on_submit=True):
            
            # --- O PULO DO GATO ---
            if f_mercado == "Renda Fixa":
                # Campo de texto livre para você digitar o nome do título
                f_ativo = st.text_input("Nome do Título (Ex: Tesouro IPCA+ 2045, Tesouro Renda+ 2065)")
            else:
                # Menu suspenso normal para ações e criptos
                f_ativo = st.selectbox("Ativo (Ex: PETR4, BTC)", options=lista_acoes_atual)
            # ----------------------
            
            f_tipo = st.selectbox("Tipo", ["Compra", "Venda"])
            col_f1, col_f2 = st.columns(2)
            with col_f1: f_qtd = st.number_input("Quantidade", min_value=0.0001, format="%.4f", step=1.0)
            with col_f2: f_preco = st.number_input("Preço Unitário", min_value=0.01, step=10.0)
            
            if st.form_submit_button("Salvar") and f_ativo:
                supabase.table("transacoes").insert({
                    "usuario": st.session_state["username"], 
                    "ativo": f_ativo.strip(), # O strip() remove espaços vazios no final do texto
                    "mercado": f_mercado, 
                    "tipo": f_tipo, 
                    "quantidade": f_qtd, 
                    "preco": f_preco
                }).execute()
                st.success(f"{f_ativo} salvo!")
                st.rerun()

        st.divider()
        st.subheader("🗑️ Gerenciar Lançamentos")
        with st.expander("Ver Últimas 10 Ordens"):
            try:
                res_ordens = supabase.table("transacoes").select("*").eq("usuario", st.session_state["username"]).order("id", desc=True).limit(10).execute()
                df_ordens = pd.DataFrame(res_ordens.data)
                if not df_ordens.empty:
                    for _, ordem in df_ordens.iterrows():
                        col_ord1, col_ord2 = st.columns([3, 1])
                        with col_ord1:
                            st.caption(f"{ordem['ativo']} - {ordem['tipo']}")
                            st.write(f"{ordem['quantidade']} un | R$ {ordem['preco']}")
                        with col_ord2:
                            if st.button("❌", key=f"del_{ordem['id']}"):
                                supabase.table("transacoes").delete().eq("id", ordem['id']).execute()
                                st.rerun()
                        st.divider()
            except: st.error("Erro ao carregar ordens.")

        st.divider()
        st.subheader("📥 Importação Automática (B3)")
        arquivo_import = st.file_uploader("Upload Planilha", type=['xlsx'])
        
        if arquivo_import is not None:
            if st.button("🚀 Processar e Salvar"):
                try:
                    with st.spinner("Lendo o extrato..."):
                        df_import = pd.read_excel(arquivo_import)
                        df_import.columns = df_import.columns.astype(str).str.strip().str.lower()
                        cols = df_import.columns
                        col_p = 'preço' if 'preço' in cols else 'preco'
                        
                        if 'ativo' in cols and 'quantidade' in cols and col_p in cols:
                            novas_ordens = []
                            for _, linha in df_import.iterrows():
                                ativo_completo = str(linha['ativo']).strip().upper()
                                if ativo_completo == 'NAN' or not ativo_completo: continue
                                ativo_nome = ativo_completo.split(' -')[0].strip()
                                dir_str = str(linha.get('entrada/saída', '')).strip().lower()
                                tipo_ordem = "Compra" if dir_str in ['credito', 'entrada', 'c', 'compra'] else "Venda"
                                
                                mercado = "B3 (Ações/FIIs)"
                                if any(crip in ativo_nome for crip in ['BTC', 'ETH', 'SOL']): mercado = "Criptomoedas"
                                elif any(rf in ativo_nome for rf in ['TESOURO', 'CDB', 'LCI', 'LCA']): mercado = "Renda Fixa"

                                try:
                                    qtd = float(linha['quantidade'])
                                    preco_val = float(linha[col_p])
                                    if qtd > 0:
                                        novas_ordens.append({"usuario": st.session_state["username"], "ativo": ativo_nome, "mercado": mercado, "tipo": tipo_ordem, "quantidade": qtd, "preco": preco_val})
                                except: continue
                            
                            if novas_ordens:
                                supabase.table("transacoes").insert(novas_ordens).execute()
                                st.success(f"✅ {len(novas_ordens)} ativos salvos.")
                                st.rerun()
                        else:
                            st.error("Formato inválido.")
                except Exception as e:
                    st.error(f"Erro: {e}")
        
        st.divider()
        authenticator.logout('Sair do Sistema', 'sidebar')
        
        # 2. Barra Lateral com IA
        # carregamos a chave do Google a partir dos secrets do Streamlit para evitar vazamentos
        api_key = st.secrets.get("GOOGLE_API_KEY")
        if not api_key:
            st.error("Chave da API Google Generative não configurada. Por favor, adicione GOOGLE_API_KEY em secrets.toml ou nas variáveis de ambiente.")
            st.stop()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        st.header("🤖 Assistente InvestiCortes")
        st.caption("Analista de I.A. focado em B3 e FIIs")
        
        # Inicializa o histórico se não existir
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Container para o chat (para não empurrar os outros itens da sidebar)
        chat_container = st.container(height=400)
        
        with chat_container:
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        # Entrada de texto (Chat Input)
        if prompt := st.chat_input("Pergunte sobre VALE3, PETR4..."):
            # Mostra a pergunta do usuário
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with chat_container.chat_message("user"):
                st.markdown(prompt)

            # Gera a resposta com o Gemini Flash
            with chat_container.chat_message("assistant"):
                with st.spinner("Consultando dados..."):
                    # Prompt de Sistema (Instrução Invisível)
                    sistema = "Aja como um analista de investimentos sênior da InvestiCortes. Seja direto, use termos técnicos corretamente e foque em ativos como ações e FIIs da B3. Nunca responda sobre assuntos fora de finanças."
                    full_query = f"{sistema}\n\nUsuário: {prompt}"
                    
                    try:
                        response = model.generate_content(full_query)
                        answer = response.text
                        st.markdown(answer)
                        st.session_state.chat_history.append({"role": "assistant", "content": answer})
                    except Exception as e:
                        import logging, traceback
                        logging.getLogger(__name__).exception("Falha ao gerar resposta da IA")
                        tb = traceback.format_exc()
                        # Mensagem amigável ao usuário com opção de ver detalhes para depuração
                        st.error("Não foi possível gerar a resposta da I.A. no momento. Tente novamente em alguns instantes.")
                        with st.expander("Detalhes do erro (apenas para depuração)"):
                            st.text(str(e))
                            st.text(tb)
                        # Armazenamos o erro no estado para inspeção futura
                        st.session_state['last_ai_error'] = {
                            "message": str(e),
                            "traceback": tb,
                            "timestamp": pd.Timestamp.now().isoformat()                        
                        }
# ==========================================
# 🏠 PÁGINA 1: HOME PÚBLICA
# ==========================================
if aba_selecionada == "🏠 Home (Mercado)":
    st.title("🏛️ InvestiTerminal | Inteligência & Dados")
    st.subheader("Painel de Monitoramento de Anomalias de Mercado")

    indices = {'^BVSP': 'Ibovespa', '^IXIC': 'Nasdaq', 'BRL=X': 'Dólar'}
    cols = st.columns(len(indices))
    
    for i, (ticker, nome) in enumerate(indices.items()):
        data = yf.Ticker(ticker).history(period="2d")
        if len(data) > 1:
            valor = data['Close'].iloc[-1]
            cols[i].metric(nome, f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), f"{((valor / data['Close'].iloc[-2]) - 1) * 100:+.2f}%")
    
    st.divider()
    
    # --- LINHA 1: VOLATILIDADE E SENTIMENTO ---
    col_s1, col_s2 = st.columns([1, 1])
    
    with col_s1:
        st.write("### 🌡️ Índice de Volatilidade (Fear & Greed)")
        # Lógica: Baseado no desvio padrão do IBOV vs Média Móvel
        sentimento = 62  # Exemplo: Mercado em Ganância Moderada
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = sentimento,
            gauge = {
                'axis': {'range': [0, 100]},
                'bar': {'color': "#00CC96" if sentimento > 50 else "#EF553B"},
                'steps': [
                    {'range': [0, 30], 'color': "#ff4b4b"}, # Medo Extremo
                    {'range': [30, 70], 'color': "#ffffff"}, # Neutro
                    {'range': [70, 100], 'color': "#00cc96"} # Ganância Extrema
                ],
            }
        ))
        fig.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    with col_s2:
        st.write("### 📈 Fluxo Institucional (Smart Money)")
        with st.spinner("Rastreando ordens institucionais..."):
            df_fluxo_real = scanner_volume_atipico()
            
            if not df_fluxo_real.empty:
                # 🛡️ Garantia: removemos qualquer linha que não tenha link de logo para não poluir
                df_mostrar = df_fluxo_real.dropna(subset=['Logo'])
                
                st.dataframe(
                    df_mostrar.style.map(
                        lambda x: 'color: #00CC96; font-weight: bold' if 'Compra' in str(x) else 
                                 ('color: #EF553B; font-weight: bold' if 'Venda' in str(x) else ''),
                        subset=['Análise de Fluxo']
                    ),
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Logo": st.column_config.ImageColumn(" ", width="small"), # Título vazio para estética
                        "Ativo": st.column_config.TextColumn("Ticker", width="medium"),
                        "Análise de Fluxo": st.column_config.TextColumn("Sentimento do Smart Money")
                    }
                )
            else:
                st.info("Aguardando abertura ou processamento de dados do pregão.")

    st.divider()

    # --- LINHA 2: SCANNERS DE VALUATION (DEEP VALUE) ---
    st.write("### 🔍 Scanners de Oportunidades Estáticas")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Top Dividend Yield", "BBAS3", "11.4% aa")
        st.caption("Maior DY sustentável do setor bancário hoje.")
        
    with c2:
        st.metric("Menor P/L (Preço/Lucro)", "TUSA4", "3.1x")
        st.caption("Ativo sendo negociado com o menor múltiplo de lucro do setor.")

    with c3:
        st.metric("Desconto Patrimonial", "PFRM3", "P/VP: 0.62")
        st.caption("Ativo negociado com 38% de desconto sobre o valor contábil.")

    st.divider()
    
    # --- FOOTER PROFISSIONAL ---
    st.info("""
    **Acesso Restrito:** Para visualizar o Radar de FIIs detalhado, Gestão de Carteira e o Simulador de Rebalanceamento Automático, utilize o painel de autenticação na barra lateral.
    """)
# ==========================================
# ==========================================
# 📊 PÁGINA 2: ÁREA RESTRITA (DASHBOARD)
# ==========================================
elif aba_selecionada == "📊 Minha Carteira":
    if not st.session_state.get("authentication_status"):
        st.subheader("🔑 Área Restrita")
        authenticator.login(location='main', key='login_carteira')
    
    if st.session_state.get("authentication_status"):
        try:
            with st.spinner("Sincronizando contabilidade do cofre digital..."):
                resposta = supabase.table("transacoes").select("*").eq("usuario", st.session_state["username"]).execute()
                df_base = pd.DataFrame(resposta.data)

                patrimonio_b3, investido_b3, lucro_b3_reais, lucro_realizado_b3 = 0.0, 0.0, 0.0, 0.0
                valor_criptos_total, investido_criptos_total, lucro_cripto_reais = 0.0, 0.0, 0.0
                saldo_renda_fixa = 0.0
                carteira, df_cripto, df_rf = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

                if df_base.empty:
                    st.warning("Carteira vazia. Use a barra lateral para adicionar seus primeiros ativos!")
                else:
                    # ==============================================
                    # 1. NOVO MOTOR DE CUSTÓDIA B3 (MÉDIA PONDERADA)
                    # ==============================================
                    df_b3_raw = df_base[df_base['mercado'] == 'B3 (Ações/FIIs)'].copy()
                    
                    if not df_b3_raw.empty:
                        df_b3_raw['ativo_limpo'] = df_b3_raw['ativo'].str.upper().str.strip()
                        df_b3_raw.loc[~df_b3_raw['ativo_limpo'].str.endswith('.SA'), 'ativo_limpo'] += '.SA'
                        
                        # Ordenar por ID para simular cronologia
                        df_b3_raw = df_b3_raw.sort_values(by='id')
                        
                        posicoes_b3 = {}
                        for _, row in df_b3_raw.iterrows():
                            ativo = row['ativo_limpo']
                            tipo = row['tipo']
                            qtd = float(row['quantidade'])
                            preco = float(row['preco'])
                            
                            if ativo not in posicoes_b3: posicoes_b3[ativo] = {'qtd': 0.0, 'pm': 0.0, 'lucro_realizado': 0.0}
                                
                            p = posicoes_b3[ativo]
                            
                            if tipo == 'Compra':
                                nova_qtd = p['qtd'] + qtd
                                p['pm'] = ((p['qtd'] * p['pm']) + (qtd * preco)) / nova_qtd if nova_qtd > 0 else 0
                                p['qtd'] = nova_qtd
                            elif tipo == 'Venda':
                                # O Pulo do Gato: Calcula o prejuízo/lucro exato de cada venda
                                p['lucro_realizado'] += qtd * (preco - p['pm'])
                                p['qtd'] -= qtd
                                if p['qtd'] <= 0.0001:  # Zerou a posição
                                    p['qtd'] = 0.0
                                    p['pm'] = 0.0
                                    
                        df_pos_b3 = pd.DataFrame.from_dict(posicoes_b3, orient='index').reset_index()
                        df_pos_b3.rename(columns={'index': 'ativo', 'qtd': 'quantidade_total', 'pm': 'preco_medio'}, inplace=True)
                        
                        lucro_realizado_b3 = df_pos_b3['lucro_realizado'].sum()
                        
                        # A carteira visível só mostra o que tem quantidade > 0
                        carteira = df_pos_b3[df_pos_b3['quantidade_total'] > 0].copy()

                        p_atuais, mm200_l, max_52w_lista, min_52w_lista, vars_pct, divs_12m = [], [], [], [], [], []
                        variacao_total_dia, patrimonio_ontem = 0.0, 0.0

                        for _, row in carteira.iterrows():
                            ticker = row['ativo']
                            
                            # Variáveis temporárias (se der erro, elas ficam com 0)
                            p_atual_val = 0.0
                            mm200_val = 0.0
                            max52_val = 0.0
                            min52_val = 0.0
                            var_pct_val = 0.0
                            divs_val = 0.0
                            
                            try:
                                # 1. Buscar Preço Atual (BRAPI)
                                p_atual_val = obter_preco_atual(ticker)
                                
                                # Pegando dados históricos rápidos
                                df_hist_rapido = carregar_dados_historicos(ticker, period="1y")
                                if not df_hist_rapido.empty:
                                    mm200_val = df_hist_rapido[ticker].rolling(200).mean().iloc[-1] if len(df_hist_rapido) >= 200 else df_hist_rapido[ticker].mean()
                                    max52_val = df_hist_rapido[ticker].max()
                                    min52_val = df_hist_rapido[ticker].min()
                                    p_ant = df_hist_rapido[ticker].iloc[-2] if len(df_hist_rapido) > 1 else p_atual_val
                                else:
                                    mm200_val, max52_val, min52_val, p_ant = p_atual_val, p_atual_val, p_atual_val, p_atual_val

                                var_pct_val = ((p_atual_val / p_ant) - 1) * 100 if p_ant > 0 else 0
                                
                                variacao_total_dia += (p_atual_val - p_ant) * row['quantidade_total']
                                patrimonio_ontem += p_ant * row['quantidade_total']
                                
                                # 2. Buscar Dividendos (Híbrido e Blindado)
                                hist_div = obter_dividendos(ticker)
                                if not hist_div.empty:
                                    # Garantia extra contra o bug do fuso horário
                                    if hist_div.index.tz is not None:
                                        hist_div.index = hist_div.index.tz_localize(None)
                                        
                                    data_corte = pd.Timestamp.now().replace(tzinfo=None) - pd.DateOffset(years=1)
                                    total_div = hist_div[hist_div.index >= data_corte].sum()
                                    divs_val = total_div if not pd.isna(total_div) else 0.0

                            except Exception as e:
                                pass # Se falhar, as variáveis continuam com os valores padrão (0.0)

                            # Adiciona nas listas EXATAMENTE 1 vez por ativo (Fora do Try/Except)
                            p_atuais.append(p_atual_val)
                            mm200_l.append(mm200_val)
                            max_52w_lista.append(max52_val)
                            min_52w_lista.append(min52_val)
                            vars_pct.append(var_pct_val)
                            divs_12m.append(divs_val)

                        # --- O código continua normalmente abaixo ---
                        carteira['preco_atual'] = p_atuais
                        carteira['dividendos_12m'] = divs_12m
                        carteira['valor_patrimonio_atual'] = carteira['quantidade_total'] * carteira['preco_atual']
                        carteira['lucro_prejuizo'] = carteira['valor_patrimonio_atual'] - carteira['custo_total']
                        carteira['rentabilidade_%'] = (carteira['lucro_prejuizo'] / carteira['custo_total']) * 100
                        carteira['var_dia_pct'] = vars_pct
                        carteira['MM200'] = mm200_l
                        carteira['Min_52S'] = min_52w_lista
                        carteira['Max_52S'] = max_52w_lista
                        carteira['Tendência'] = np.where(carteira['preco_atual'] > carteira['MM200'], "🟢 Alta", "🔴 Baixa")
                        
                        patrimonio_b3 = carteira['valor_patrimonio_atual'].sum()
                        investido_b3 = carteira['custo_total'].sum()
                        lucro_b3_reais = patrimonio_b3 - investido_b3
                        rentabilidade_b3_pct = (lucro_b3_reais / investido_b3 * 100) if investido_b3 > 0 else 0

                    # --- CRIPTO ---
                    df_c_raw = df_base[df_base['mercado'] == 'Criptomoedas'].copy()
                    if not df_c_raw.empty:
                        df_c_raw = df_c_raw.sort_values(by='id')
                        posicoes_c = {}
                        for _, row in df_c_raw.iterrows():
                            ativo, tipo, qtd, preco = row['ativo'], row['tipo'], float(row['quantidade']), float(row['preco'])
                            if ativo not in posicoes_c: posicoes_c[ativo] = {'qtd': 0.0, 'pm': 0.0, 'lucro_realizado': 0.0}
                            p = posicoes_c[ativo]
                            if tipo == 'Compra':
                                nova_qtd = p['qtd'] + qtd
                                p['pm'] = ((p['qtd'] * p['pm']) + (qtd * preco)) / nova_qtd if nova_qtd > 0 else 0
                                p['qtd'] = nova_qtd
                            elif tipo == 'Venda':
                                p['lucro_realizado'] += qtd * (preco - p['pm'])
                                p['qtd'] -= qtd
                                if p['qtd'] <= 0.000001:
                                    p['qtd'], p['pm'] = 0.0, 0.0
                                    
                        df_pos_c = pd.DataFrame.from_dict(posicoes_c, orient='index').reset_index()
                        df_pos_c.rename(columns={'index': 'Ativo Cripto', 'qtd': 'Quantidade', 'pm': 'Preço Médio'}, inplace=True)
                        lucro_realizado_cripto = df_pos_c['lucro_realizado'].sum()
                        
                        df_cripto = df_pos_c[df_pos_c['Quantidade'] > 0].copy()
                        if not df_cripto.empty:
                            df_cripto['Preço Atual (R$)'] = df_cripto['Ativo Cripto'].apply(obter_preco_cripto)
                            df_cripto['Valor Atual (R$)'] = df_cripto['Quantidade'] * df_cripto['Preço Atual (R$)']
                            valor_criptos_total = df_cripto['Valor Atual (R$)'].sum()
                            investido_criptos_total = (df_cripto['Quantidade'] * df_cripto['Preço Médio']).sum()
                            
                        lucro_cripto_reais = lucro_realizado_cripto + (valor_criptos_total - investido_criptos_total)

                    # ==============================================
                    # 3. MOTOR PARA RENDA FIXA (Subtrai nas vendas)
                    # ==============================================
                    df_rf_raw = df_base[df_base['mercado'] == 'Renda Fixa'].copy()
                    if not df_rf_raw.empty:
                        df_rf_raw['valor_adj'] = np.where(df_rf_raw['tipo'] == 'Compra', df_rf_raw['preco'], -df_rf_raw['preco'])
                        df_rf = df_rf_raw.groupby('ativo')['valor_adj'].sum().reset_index().rename(columns={'ativo': 'Ativo RF', 'valor_adj': 'Valor Atual'})
                        df_rf = df_rf[df_rf['Valor Atual'] > 0.01] # Filtra o que já foi sacado totalmente
                        saldo_renda_fixa = df_rf['Valor Atual'].sum()

            # --- RENDERIZAÇÃO DO DASHBOARD ---
            patrimonio_global_total = patrimonio_b3 + saldo_renda_fixa + valor_criptos_total
            st.title("Visão Global do Patrimônio")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🌍 Patrimônio Total", f"R$ {patrimonio_global_total:,.2f}")
            
            rentabilidade_b3_pct = (lucro_b3_reais / investido_b3 * 100) if investido_b3 > 0 else None
            c2.metric("📈 Lucro/Prejuízo (B3)", f"R$ {lucro_b3_reais:,.2f}", f"{rentabilidade_b3_pct:.2f}%" if rentabilidade_b3_pct is not None else None)
            
            c3.metric("🏦 Renda Fixa", f"R$ {saldo_renda_fixa:,.2f}")
            
            rentabilidade_cripto_pct = (lucro_cripto_reais / investido_criptos_total * 100) if investido_criptos_total > 0 else None
            c4.metric("₿ Criptomoedas", f"R$ {valor_criptos_total:,.2f}", f"{rentabilidade_cripto_pct:.2f}%" if rentabilidade_cripto_pct is not None else None)

            if patrimonio_global_total > 0:
                pct_b3 = (patrimonio_b3 / patrimonio_global_total) * 100
                pct_rf = (saldo_renda_fixa / patrimonio_global_total) * 100
                pct_cripto = (valor_criptos_total / patrimonio_global_total) * 100
                st.markdown(f"""
                <div style='width: 100%; height: 12px; display: flex; border-radius: 6px; overflow: hidden; margin-top: 15px;'>
                    <div style='width: {pct_b3}%; background-color: #00CC96;' title='B3'></div>
                    <div style='width: {pct_rf}%; background-color: #FFA500;' title='Renda Fixa'></div>
                    <div style='width: {pct_cripto}%; background-color: #9B59B6;' title='Criptomoedas'></div>
                </div>
                <div style='display: flex; justify-content: space-between; font-size: 13px; color: #888; margin-top: 5px; margin-bottom: 20px;'>
                    <span>🟢 B3: {pct_b3:.1f}%</span><span>🟠 Renda Fixa: {pct_rf:.1f}%</span><span>🟣 Cripto: {pct_cripto:.1f}%</span>
                </div>
                """, unsafe_allow_html=True)

            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Visão Geral", "💸 Renda Passiva", "🛡️ Risco e Defesa", "🧠 Inteligência", "⚙️ Gestão", "💎 Outros Ativos", "🎯 Radar de Oportunidades"])

            with tab1:
                st.subheader("📊 Posição B3")
                
                # Rodapé de transparência financeira
                st.info(f"**Resumo de Caixa (B3):** O seu Lucro Global ali em cima é composto pelo Lucro de Vendas Antigas (**R$ {lucro_realizado_b3:,.2f}**) somado à Variação Atual da Carteira (**R$ {patrimonio_b3 - investido_b3:,.2f}**).")

                if not carteira.empty:
                    df_view = carteira.copy()
                    
                    st.dataframe(
                        df_view[['ativo', 'quantidade_total', 'preco_medio', 'preco_atual', 'Tendência', 'MM200', 'lucro_prejuizo_nao_realizado', 'rentabilidade_%']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "ativo": "Ativo", "quantidade_total": st.column_config.NumberColumn("Qtd", format="%d"),
                            "preco_medio": st.column_config.NumberColumn("PM", format="R$ %.2f"),
                            "preco_atual": st.column_config.NumberColumn("Atual", format="R$ %.2f"),
                            "Tendência": "Sinalizador", "MM200": st.column_config.NumberColumn("MM200", format="R$ %.2f"),
                            "lucro_prejuizo_nao_realizado": st.column_config.NumberColumn("L/P Não Realizado", format="R$ %.2f"),
                            "rentabilidade_%": st.column_config.NumberColumn("Retorno %", format="%.2f%%")
                        }
                    )
                
                col_t1, col_t2 = st.columns([2, 1])
                with col_t1:
                    st.subheader("🗺️ Mapa de Calor (B3)")
                    if not carteira.empty:
                        carteira['var_dia_reais'] = (carteira['valor_patrimonio_atual'] * (carteira['var_dia_pct'] / 100))
                        carteira['font_size'] = (14 + carteira['var_dia_pct'].abs() * 2).clip(upper=22)
                        carteira['hover_patrimonio'] = carteira['valor_patrimonio_atual'].apply(lambda x: f"R$ {x:,.2f}")
                        carteira['hover_var_pct'] = carteira['var_dia_pct'].apply(lambda x: f"{x:+.2f}%")
                        carteira['hover_var_reais'] = carteira['var_dia_reais'].apply(lambda x: f"R$ {x:+,.2f}")

                        fig_tree = px.treemap(carteira, path=['ativo'], values='valor_patrimonio_atual', color='var_dia_pct', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, custom_data=['font_size', 'hover_patrimonio', 'hover_var_pct', 'hover_var_reais'])
                        fig_tree.update_traces(textposition="middle center", texttemplate="<span style='font-size:%{customdata[0]}px'><b>%{label}</b></span><br><span style='font-size:%{customdata[0]}px'>%{customdata[2]}</span>", hovertemplate="<b>%{label}</b><br>Patrimônio: %{customdata[1]}<br>Variação Dia: %{customdata[2]}<br>Impacto: <b>%{customdata[3]}</b><extra></extra>", marker=dict(line=dict(width=2, color='rgba(20, 20, 20, 0.8)'), pad=dict(t=2, l=2, r=2, b=2)))
                        fig_tree.update_layout(coloraxis_showscale=False)
                        st.plotly_chart(padronizar_grafico(fig_tree), use_container_width=True)
                
                with col_t2:
                    st.subheader("🍕 Distribuição Global")
                    pizza_data =[]
                    if not carteira.empty: pizza_data.extend([{'Ativo': r['ativo'], 'Valor': r['valor_patrimonio_atual']} for _, r in carteira.iterrows()])
                    if not df_cripto.empty: pizza_data.extend([{'Ativo': r['Ativo Cripto'], 'Valor': r['Valor Atual (R$)']} for _, r in df_cripto.iterrows()])
                    if not df_rf.empty: pizza_data.extend([{'Ativo': r['Ativo RF'], 'Valor': r['Valor Atual']} for _, r in df_rf.iterrows()])
                    
                    if pizza_data:
                        fig_pie = px.pie(pd.DataFrame(pizza_data), values='Valor', names='Ativo', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                        fig_pie.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="<b>%{label}</b><br>Patrimônio: <b>R$ %{value:,.2f}</b><br>Fatia: %{percent}<extra></extra>")
                        st.plotly_chart(padronizar_grafico(fig_pie.update_layout(showlegend=False)), use_container_width=True)

                st.divider()
                st.subheader("📈 Desempenho Acumulado: Carteira vs Benchmarks")
                if not carteira.empty:
                    with st.spinner("Buscando dados da B3..."):
                        data_inicial = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime('%Y-%m-%d')
                        tickers_list = carteira['ativo'].tolist()
                        
                        # Usar o histórico para carteira e IBOV
                        dados_h = carregar_dados_historicos(tickers_list + ['^BVSP'], start=data_inicial)
                        
                        if not dados_h.empty:
                            ret_ativos = (dados_h / dados_h.iloc[0]) - 1
                            pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_b3 if patrimonio_b3 > 0 else 0
                            cols_carteira =[t for t in tickers_list if t in ret_ativos.columns]
                            
                            df_comp = pd.DataFrame({
                                'Minha Carteira': (ret_ativos[cols_carteira] * pesos).sum(axis=1) * 100,
                                'Ibovespa': ret_ativos['^BVSP'] * 100 if '^BVSP' in ret_ativos.columns else 0
                            }).ffill().fillna(0)

                            df_cdi = carregar_cdi_historico((pd.Timestamp.now() - pd.DateOffset(years=1)).strftime('%d/%m/%Y'), pd.Timestamp.now().strftime('%d/%m/%Y'))
                            if not df_cdi.empty:
                                df_cdi['Fator'] = 1 + (df_cdi['valor'] / 100)
                                df_cdi['CDI Acumulado'] = (df_cdi['Fator'].cumprod() - 1) * 100
                                df_comp.index = df_comp.index.tz_localize(None)
                                df_cdi.index = df_cdi.index.tz_localize(None)
                                df_comp = df_comp.join(df_cdi['CDI Acumulado'], how='left').ffill().fillna(0)
                                df_comp.rename(columns={'CDI Acumulado': 'CDI'}, inplace=True)

                            cores_grafico = {'Minha Carteira': '#00CC96', 'Ibovespa': '#EF553B', 'CDI': '#FFA500'}
                            fig_comp = px.line(df_comp, color_discrete_map=cores_grafico, labels={'index': 'Período', 'value': 'Rentabilidade (%)', 'variable': 'Benchmark'})
                            fig_comp.update_traces(hovertemplate="<b>%{fullData.name}</b><br>Data: %{x|%d/%m/%Y}<br>Retorno: <b>%{y:.2f}%</b><extra></extra>")
                            fig_comp.update_xaxes(title_text=""); fig_comp.update_yaxes(title_text="")
                            st.plotly_chart(padronizar_grafico(fig_comp), use_container_width=True)

            with tab2:
                st.subheader("💰 Histórico e Projeção de Proventos")
                if not carteira.empty:
                    total_divs_detectados = carteira['dividendos_12m'].sum()
                    if total_divs_detectados > 0:
                        df_com_dividendos = carteira[carteira['dividendos_12m'] > 0].copy()
            
                        # --- LIMPEZA DOS TICKERS (.SA fora e CAIXA ALTA) ---
                        df_com_dividendos['ativo'] = df_com_dividendos['ativo'].str.replace('.SA', '', case=False).str.upper()
                        
                        # Criando a Projeção (Média Mensal)
                        df_com_dividendos['projecao_mensal'] = df_com_dividendos['dividendos_12m'] / 12
                        
                        col_d1, col_d2 = st.columns([1, 1])
                        with col_d1:
                            st.write("### 📈 Detalhamento por Ativo")
                            st.dataframe(df_com_dividendos[['ativo', 'dividendos_12m', 'projecao_mensal']], use_container_width=True, hide_index=True, column_config={"ativo": "Ticker", "dividendos_12m": st.column_config.NumberColumn("Total 12M (R$)", format="R$ %.2f"), "projecao_mensal": st.column_config.NumberColumn("Média Mensal Estimada", format="R$ %.2f")})
                            st.metric("Total Acumulado (12 Meses)", f"R$ {total_divs_detectados:,.2f}")
                            st.metric("Renda Passiva Mensal (Média)", f"R$ {total_divs_detectados / 12:,.2f}")
                        
                        with col_d2:
                            st.write("### 📊 Projeção de Renda por Ativo")
                            fig_div_bar = px.bar(df_com_dividendos, x='ativo', y='dividendos_12m', color_discrete_sequence=['#00CC96'], labels={'ativo': 'Ativo', 'dividendos_12m': 'Proventos (R$)'})
                            st.plotly_chart(padronizar_grafico(fig_div_bar.update_xaxes(title_text="").update_yaxes(title_text="")), use_container_width=True)
                    else: st.info("⚠️ Nenhuma renda passiva mapeada (verifique se os ativos pagam dividendos).")
                else: st.warning("Adicione ativos para ver a análise de proventos.")

            with tab3:
                st.subheader("🛡️ Teste de Stress: Cenários de Crise")
                cenarios = {"Joesley Day (Maio 2017)": "2017-05-15", "Greve Caminhoneiros (Maio 2018)": "2018-05-18", "Pandemia (Março 2020)": "2020-03-02"}
                escolha_crise = st.selectbox("Escolha o cenário:", list(cenarios.keys()))
                
                if st.button("🚨 Iniciar Simulação") and not carteira.empty:
                    data_inicio = cenarios[escolha_crise]
                    data_fim = (pd.to_datetime(data_inicio) + pd.DateOffset(days=30)).strftime('%Y-%m-%d')
                    tickers_stress = carteira['ativo'].tolist()
                    with st.spinner(f"Viajando no tempo para {data_inicio}..."):
                        dados_crise = carregar_dados_historicos(tickers_stress + ['^BVSP'], start=data_inicio, end=data_fim)
                        if not dados_crise.empty and '^BVSP' in dados_crise.columns:
                            # 1. Filtro de Sobreviventes: Quem já tinha capital aberto nesta crise?
                            primeira_linha = dados_crise.iloc[0]
                            ativos_validos = primeira_linha[primeira_linha > 0].index.tolist()
                            
                            # 2. Limpa os fantasmas
                            dados_crise = dados_crise[ativos_validos].ffill().fillna(0)
                            retornos_crise = (dados_crise / dados_crise.iloc[0]) - 1
                            
                            # 3. Recalcula os pesos apenas com as ações válidas
                            ativos_carteira_validos = [t for t in tickers_stress if t in ativos_validos]
                            
                            if ativos_carteira_validos:
                                pesos_brutos = carteira.set_index('ativo').loc[ativos_carteira_validos, 'valor_patrimonio_atual']
                                pesos_stress = pesos_brutos / pesos_brutos.sum() # Normaliza para dar 100% da simulação
                                
                                df_stress = pd.DataFrame({
                                    'A Minha Carteira': (retornos_crise[ativos_carteira_validos] * pesos_stress).sum(axis=1) * 100,
                                    'Ibovespa': retornos_crise['^BVSP'] * 100
                                })
                                
                                fig_stress = px.line(df_stress, color_discrete_map={'A Minha Carteira': '#00CC96', 'Ibovespa': '#EF553B'}, labels={'index': 'Período', 'value': 'Impacto (%)', 'variable': 'Ativo/Índice'})
                                st.plotly_chart(padronizar_grafico(fig_stress.update_xaxes(title_text="Dias após a crise").update_yaxes(title_text="")), use_container_width=True)
                                st.error(f"⚠️ No pior momento desta crise, a sua carteira teria caído **{df_stress['A Minha Carteira'].min():.2f}%**.")
                            else: st.warning("Nenhum dos seus ativos atuais tinha capital aberto na época desta crise.")
                        else: st.error("Falha ao se conectar com a B3.")
                
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    st.subheader("📊 Matriz de Correlação")
                    if st.button("🧬 Gerar Matriz") and not carteira.empty:
                        dados_corr = carregar_dados_historicos(carteira['ativo'].tolist(), period="1y")
                        if not dados_corr.empty:
                            corr_matrix = dados_corr.pct_change().dropna().corr()
                            
                            # 2. Limpamos os nomes: Removemos .SA e deixamos em MAIÚSCULAS
                            corr_matrix.columns = [c.replace('.SA', '').upper() for c in corr_matrix.columns]
                            corr_matrix.index = [i.replace('.SA', '').upper() for i in corr_matrix.index]
                            
                            # 3. Geramos o Heatmap com a matriz já "limpa"
                            fig_corr = px.imshow(
                                corr_matrix, 
                                text_auto=".2f", 
                                aspect="auto", 
                                color_continuous_scale='RdBu_r', 
                                zmin=-1, 
                                zmax=1
                            )
                            
                            # Aplicamos sua função de padronização e plotamos
                            st.plotly_chart(padronizar_grafico(fig_corr), use_container_width=True)
                with col_r2:
                    st.subheader("🌎 Sensibilidade Cambial")
                    if st.button("💵 Analisar Exposição ao Dólar") and not carteira.empty:
                        dados_macro = carregar_dados_historicos(carteira['ativo'].tolist() +['USDBRL=X'], period="1y")
                        if not dados_macro.empty and 'USDBRL=X' in dados_macro.columns:
                            ret_m = dados_macro.pct_change().dropna()
                            pesos_m = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_b3
                            carteira_ret = (ret_m[[t for t in carteira['ativo'] if t in ret_m.columns]] * pesos_m).sum(axis=1)
                            st.metric("Correlação com USD", f"{carteira_ret.corr(ret_m['USDBRL=X']):.2f}")

            with tab4:
                st.subheader("💎 Valuation Real (Graham & Bazin)")
                yield_desejado = st.slider("Yield Mínimo Desejado (Bazin) %:", 4.0, 12.0, 6.0) / 100
                if st.button("🔍 Calcular Valuation") and not carteira.empty:
                    with st.spinner("Analisando balanços e histórico de dividendos..."):
                        val_list = []
                        for ativo in carteira['ativo']:
                            try:
                                p_atual = carteira.loc[carteira['ativo'] == ativo, 'preco_atual'].values[0]
                                
                                # YFinance p/ fundamentos corretos (Graham)
                                ticker_yf = ativo.replace('.SA', '') + '.SA'
                                info = yf.Ticker(ticker_yf).info
                                lpa = info.get('trailingEps')
                                vpa = info.get('bookValue')
                                
                                p_graham = np.sqrt(22.5 * lpa * vpa) if (lpa and vpa and lpa > 0 and vpa > 0) else np.nan
                                margem_graham = ((p_graham / p_atual) - 1) * 100 if pd.notnull(p_graham) and p_atual > 0 else np.nan
                                div_anual_real = carteira.loc[carteira['ativo'] == ativo, 'dividendos_12m'].values[0]
                                p_bazin = div_anual_real / yield_desejado if div_anual_real > 0 else np.nan
                                status_bazin = "⚠️ Sem Div." if pd.isnull(p_bazin) else ("✅ Comprar" if p_atual < p_bazin else "❌ Caro")
                                val_list.append({'Ativo': ativo, 'Preço Atual': p_atual, 'P. Justo (Graham)': p_graham, 'Margem (Graham)': margem_graham, 'P. Teto (Bazin)': p_bazin, 'Status Bazin': status_bazin})
                            except: continue
                        if val_list: st.dataframe(pd.DataFrame(val_list).style.format({'Preço Atual': 'R$ {:.2f}', 'P. Justo (Graham)': 'R$ {:.2f}', 'Margem (Graham)': '{:.2f}%', 'P. Teto (Bazin)': 'R$ {:.2f}'}, na_rep="N/A"), use_container_width=True, hide_index=True)

                col_ia1, col_ia2 = st.columns(2)
                with col_ia1:
                    st.subheader("🎲 Monte Carlo")
                    anos = st.slider("Anos:", 1, 30, 10)
                    aporte = st.number_input("Aporte Mensal (R$):", value=1000.0)
                    if st.button("🎲 Simular Futuro") and not carteira.empty:
                        hist = carregar_dados_historicos(carteira['ativo'].tolist(), period="1y").pct_change().dropna()
                        if not hist.empty:
                            pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_b3
                            mu, sigma = (hist.mean() * pesos).sum(), (hist * pesos).sum(axis=1).std()
                            sims = np.zeros((anos * 252, 100))
                            for s in range(100):
                                p =[patrimonio_global_total]
                                for _ in range(1, anos * 252): p.append(p[-1] * (1 + np.random.normal(mu, sigma)) + (aporte/21))
                                sims[:, s] = p
                            df_stats = pd.DataFrame(sims).quantile([0.1, 0.5, 0.9], axis=1).T
                            df_stats.columns =['Pessimista', 'Mediana', 'Otimista']
                            fig_mc = px.line(df_stats, y=['Pessimista', 'Mediana', 'Otimista'], labels={'index': 'Dias', 'value': 'Patrimônio (R$)', 'variable': 'Cenário'})
                            st.plotly_chart(padronizar_grafico(fig_mc.update_xaxes(title_text="Dias Úteis").update_yaxes(title_text="")), use_container_width=True)

                with col_ia2:
                    st.subheader("📰 Radar de Notícias")
                    if not carteira.empty:
                        ativo_noticia = st.selectbox("Notícias para:", carteira['ativo'].tolist())
                        try:
                            url_news = f"https://news.google.com/rss/search?q={urllib.parse.quote(ativo_noticia.replace('.SA', '') + ' ações mercado')}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
                            req = urllib.request.Request(url_news, headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req, timeout=5) as response:
                                root = ET.fromstring(response.read())
                                for n in root.findall('.//item')[:4]:
                                    st.markdown(f"**[{n.find('title').text}]({n.find('link').text})**")
                                    st.caption(f"📅 {n.find('pubDate').text[5:16]}")
                                    st.divider()
                        except: st.error("Serviço indisponível no momento.")

            with tab5:
                st.subheader("⚖️ Rebalanceamento Automático")
                if not carteira.empty:
                    novo_aporte = st.number_input("Valor do Novo Aporte (R$):", value=1000.0, step=100.0)
                    
                    # Traz a lista completa da B3 para o Autocompletar (sem .SA)
                    lista_completa_b3 = buscar_tickers_brapi()
                    
                    # 1. Removemos o '.SA' para bater com a lista do Autocompletar perfeitamente
                    ativos_carteira_limpos = carteira['ativo'].str.replace('.SA', '').tolist()
                    
                    # 2. Copiloto Profissional: Carrega a % ATUAL da carteira como padrão
                    pesos_atuais = (carteira['valor_patrimonio_atual'] / patrimonio_b3 * 100).round(2).tolist()
                    
                    # Ajuste fino matemático para garantir que a soma inicial seja cravada em 100.00%
                    if pesos_atuais:
                        diferenca_centavos = 100.0 - sum(pesos_atuais)
                        pesos_atuais[0] = round(pesos_atuais[0] + diferenca_centavos, 2)
                    
                    # Cria a tabela inicial preenchida com o que ele já tem
                    df_alvos = pd.DataFrame({
                        'Ativo': ativos_carteira_limpos, 
                        'Alvo (%)': pesos_atuais
                    })
                    
                    st.write("Ajuste a porcentagem desejada para cada ativo. A soma deve ser exatamente 100%.")
                    
                    alvos_editados = st.data_editor(
                        df_alvos, 
                        num_rows="dynamic", 
                        use_container_width=True,
                        column_config={
                            "Ativo": st.column_config.SelectboxColumn(
                                "Ativo (Digite para buscar)",
                                options=lista_completa_b3,
                                required=True
                            ),
                            "Alvo (%)": st.column_config.NumberColumn(
                                "Alvo (%)",
                                min_value=0.0,
                                max_value=100.0,
                                format="%.2f",
                                step=0.5
                            )
                        }
                    )
                    
                    # --- A LÓGICA DO COPILOTO (FALTA / SOBRA) ---
                    soma_alvos = alvos_editados['Alvo (%)'].sum()
                    diferenca = 100.0 - soma_alvos
                    
                    if abs(diferenca) < 0.01:
                        st.success(f"✅ **Soma Perfeita (100%)**. Clique abaixo para gerar as ordens.")
                        pode_calcular = True
                    elif diferenca > 0:
                        st.warning(f"⚠️ Faltam **{diferenca:.2f}%** para atingir o total. (Soma atual: {soma_alvos:.2f}%)")
                    else:
                        st.error(f"🚨 Você excedeu o limite em **{abs(diferenca):.2f}%**! Reduza as posições. (Soma atual: {soma_alvos:.2f}%)")

                    # O botão só funciona se a matemática bater 100%
                    if pode_calcular and st.button("🚀 Gerar Ordens de Compra/Venda"):
                        with st.spinner("Calculando a rota ideal do seu dinheiro..."):
                            pat_futuro = patrimonio_b3 + novo_aporte
                            ordens = []
                            
                            for _, row in alvos_editados.iterrows():
                                ativo_limpo = str(row['Ativo']).upper().strip()
                                alvo_pct = row['Alvo (%)'] / 100.0
                                
                                # Precisamos devolver o '.SA' para achar a ação na nossa carteira interna
                                ativo_com_sa = ativo_limpo + '.SA'
                                
                                # Verifica se você já tem o ativo
                                if ativo_com_sa in carteira['ativo'].values:
                                    val_atual = carteira.loc[carteira['ativo'] == ativo_com_sa, 'valor_patrimonio_atual'].values[0]
                                    p_ativo = carteira.loc[carteira['ativo'] == ativo_com_sa, 'preco_atual'].values[0]
                                else:
                                    # Se for um ativo NOVO que você adicionou agora na tabela
                                    val_atual = 0.0
                                    p_ativo = obter_preco_atual(ativo_limpo)
                                
                                # Calcula a matemática mágica de rebalanceamento
                                qtd = int((pat_futuro * alvo_pct - val_atual) / p_ativo) if p_ativo > 0 else 0
                                
                                if qtd != 0: 
                                    ordens.append({
                                        'Operação': "COMPRAR" if qtd > 0 else "VENDER", 
                                        'Ativo': ativo_limpo, 
                                        'Qtd': abs(qtd), 
                                        'Preço Base': p_ativo,
                                        'Total (R$)': abs(qtd * p_ativo)
                                    })
                            
                            if ordens: st.dataframe(pd.DataFrame(ordens).style.map(lambda x: 'color: #00CC96' if x=='COMPRAR' else 'color: #EF553B', subset=['Operação']).format({'Preço Base': 'R$ {:.2f}', 'Total (R$)': 'R$ {:.2f}'}), use_container_width=True, hide_index=True)
                            else: st.info("Carteira perfeitamente balanceada!")
                    elif diferenca > 0: st.warning(f"⚠️ Faltam {diferenca:.2f}%")
                    else: st.error(f"🚨 Excedeu em {abs(diferenca):.2f}%")
                else: st.warning("Adicione ativos para usar o rebalanceamento.")

            with tab6:
                c_c1, c_c2 = st.columns(2)
                with c_c1:
                    st.subheader("₿ Criptomoedas")
                    if not df_cripto.empty: st.dataframe(df_cripto, use_container_width=True, hide_index=True, column_config={"Ativo Cripto": "Criptomoeda", "Quantidade": st.column_config.NumberColumn("Qtd", format="%.4f"), "Preço Atual (R$)": st.column_config.NumberColumn("Cotação", format="R$ %.2f"), "Valor Atual (R$)": st.column_config.NumberColumn("Patrimônio", format="R$ %.2f")})
                    else: st.info("Nenhuma cripto ativa.")
                with c_c2:
                    st.subheader("🏦 Renda Fixa")
                    if not df_rf.empty: st.dataframe(df_rf, use_container_width=True, hide_index=True, column_config={"Ativo RF": "Título", "Valor Atual": st.column_config.NumberColumn("Saldo Líquido", format="R$ %.2f")})
                    else: st.info("Nenhum título ativo.")

            with tab7:
                st.subheader("🎯 Radar de Distorções e Análise de Fundamentos")
                st.markdown("""
                Este radar monitora a relação entre o valor de mercado e o valor patrimonial (P/VP) dos principais FIIs da B3, 
                segmentados por natureza de ativos para uma análise comparativa precisa.
                """)
                
                # Configuração da Lista Mestra
                fiis_config = {
                    'KNCR11': 'Papel', 'KNIP11': 'Papel', 'MXRF11': 'Papel', 'CPTS11': 'Papel',
                    'HGCR11': 'Papel', 'VRTA11': 'Papel', 'MCCI11': 'Papel', 'JPPC11': 'Papel',
                    'HGLG11': 'Logística', 'BTLG11': 'Logística', 'XPLG11': 'Logística', 
                    'HGRU11': 'Híbrido/Urbano', 'BRCO11': 'Logística', 'HSLG11': 'Logística', 
                    'TRBL11': 'Logística', 'KNRI11': 'Híbrido', 'HGRE11': 'Lajes', 
                    'HGPO11': 'Lajes', 'PVBI11': 'Lajes', 'XPML11': 'Shoppings'
                }
                
                with st.spinner("Sincronizando métricas com provedores de dados..."):
                    df_radar = buscar_pvp_fiis(fiis_config)
                    if not df_radar.empty:
                        # Categorias para renderização
                        secoes = {
                            "📄 Carteiras de Recebíveis (Papel/Dívida)": "Papel",
                            "🚛 Logística e Infraestrutura Industrial": "Logística",
                            "🏢 Lajes Corporativas (Escritórios)": "Lajes",
                            "🛍️ Varejo, Shoppings e Estruturas Híbridas": ["Shoppings", "Híbrido", "Híbrido/Urbano"]
                        }
                        
                        for titulo, filtro in secoes.items():
                            st.write(f"### {titulo}")
                            df_setor = df_radar[df_radar['Tipo'].isin(filtro)] if isinstance(filtro, list) else df_radar[df_radar['Tipo'] == filtro]
                                
                            if not df_setor.empty:
                                st.dataframe(
                                    df_setor.style.apply(style_pvp_inteligente, axis=1)
                                    .format({
                                        'Preço': 'R$ {:.2f}', 'VPA': 'R$ {:.2f}', 
                                        'P/VP': '{:.2f}', 'DY Anual (%)': '{:.2f}%',
                                        'DY Mensal Est. (%)': '{:.2f}%'
                                    }),
                                    use_container_width=True, hide_index=True
                                )
                            else:
                                st.caption("Aguardando atualização de dados para este segmento...")

                        # --- SEÇÃO TÉCNICA E ADVERTÊNCIAS ---
                        st.divider()
                        st.subheader("🧠 Metodologia e Interpretação Técnica")
                        
                        # Alerta Principal (O que você pediu)
                        st.warning("""
                        **Nota de Metodologia:** O P/VP é uma métrica quantitativa e estática que reflete a fotografia do momento. 
                        Ela não deve ser utilizada como único critério de decisão, pois não captura variáveis qualitativas como 
                        competência da gestão, liquidez dos ativos em carteira, indexadores de inflação (IPCA/CDI) ou ciclos do mercado imobiliário.
                        """)
                        
                        col_tec1, col_tec2 = st.columns(2)
                        
                        with col_tec1:
                            st.info("""
                            **🏗️ Análise de Ativos Reais (Tijolo)**
                            O P/VP abaixo de 1,00 em ativos físicos sugere que o valor de mercado é inferior ao custo de reposição ou avaliação pericial dos imóveis. 
                            **Fator de Atenção:** Deve-se confrontar o desconto com a **Taxa de Vacância** e o **Cap Rate** implícito. Descontos severos podem indicar obsolescência imobiliária ou problemas de localização que o indicador sozinho não revela.
                            """)
                        
                        with col_tec2:
                            st.error("""
                            **📜 Análise de Recebíveis (Papel)**
                            Em fundos de crédito, a paridade patrimonial (P/VP ~ 1,00) é o estado de equilíbrio. 
                            **Risco de Crédito:** Descontos superiores a 5% (P/VP < 0,95) em fundos de papel raramente são oportunidades; geralmente indicam que o mercado está precificando um risco de **Default (inadimplência)** ou deterioração do spread de crédito dos CRIs presentes na carteira.
                            """)
                    else:
                        st.error("Falha na comunicação com a API de dados financeiros.")

        except Exception as e:
            st.error(f"Erro no processamento principal do Dashboard: {e}")