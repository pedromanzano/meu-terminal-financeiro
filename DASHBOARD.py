import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import numpy as np
import requests
import json
import urllib.request
import os  
from datetime import date
import openpyxl

# ==========================================
# 🛡️ BLINDAGEM CONTRA ERRO DE ESTATÍSTICA
# ==========================================
try:
    import statsmodels.api as sm
    TEM_STATSMODELS = True
except ImportError:
    TEM_STATSMODELS = False

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS (UI/UX PREMIUM)
# ==========================================
st.set_page_config(page_title="Central Financeira", layout="wide", initial_sidebar_state="expanded")

# Injeção de CSS Avançado (Modo Kiosk + Efeito Card)
st.markdown("""
<style>
    /* --- 1. EFEITO "CARD" NAS MÉTRICAS --- */
    div[data-testid="metric-container"] {
        background-color: rgba(40, 40, 40, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
    }
    
    /* Ajuste para o padding dos containers com borda não ficar gigante */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        padding: 1rem;
    }

    /* ========================================= */
    /* --- 2. MODO KIOSK (LIMPEZA VISUAL) ---    */
    /* ========================================= */
    
    /* Esconde apenas o botão superior direito "Deploy" */
    .stDeployButton {
        display: none !important;
    }
    
    /* Esconde o menu de opções (três pontinhos) e a marca de água no rodapé */
    #MainMenu {
        visibility: hidden !important;
    }
    footer {
        visibility: hidden !important;
    }
    
    /* Puxa o painel inteiro para cima, removendo o espaço vazio */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🎨 FUNÇÃO MESTRA DE ESTILO GRÁFICO
# ==========================================
def padronizar_grafico(fig):
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.95)", font_color="white", font_size=14, font_family="sans-serif", bordercolor="#444"),
        font=dict(color="#E0E0E0"),
        xaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)', zerolinecolor='rgba(128, 128, 128, 0.2)'),
        yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)', zerolinecolor='rgba(128, 128, 128, 0.2)'),
        margin=dict(t=50, l=10, r=10, b=10)
    )
    return fig

# ==========================================
# ⚡ MOTOR DE CACHE (DADOS SALVOS NA MEMÓRIA)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados_yfinance(tickers, start=None, end=None, period="1y"):
    if isinstance(tickers, str):
        tickers = [tickers]
    if start and end:
        dados = yf.download(tickers, start=start, end=end, progress=False)['Close']
    elif start:
        dados = yf.download(tickers, start=start, progress=False)['Close']
    else:
        dados = yf.download(tickers, period=period, progress=False)['Close']
    if isinstance(dados, pd.Series):
        dados = dados.to_frame(name=tickers[0])
    return dados.ffill()

@st.cache_data(ttl=86400, show_spinner=False)
def carregar_cdi_historico(data_inicio, data_fim):
    try:
        url_cdi = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={data_inicio}&dataFinal={data_fim}"
        df_cdi = pd.read_json(url_cdi)
        df_cdi['data'] = pd.to_datetime(df_cdi['data'], dayfirst=True)
        df_cdi.set_index('data', inplace=True)
        return df_cdi
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_atual(ticker):
    """Cotação instantânea com 3 camadas de segurança (Ações + Cripto + FIIs)"""
    ticker = str(ticker).strip().upper()
    if not ticker:
        return 0.0
        
    try:
        acao = yf.Ticker(ticker)
        
        # 1ª Camada: fast_info (Ultrarrápido, perfeito para ações da B3)
        try:
            return float(acao.fast_info['lastPrice'])
        except:
            pass
            
        # 2ª Camada: history (Excelente para BDRs e algumas Criptomoedas)
        try:
            hist = acao.history(period="1d")
            if not hist.empty and 'Close' in hist.columns:
                return float(hist['Close'].iloc[-1])
        except:
            pass
            
        # 3ª Camada: download bruto (Força bruta do Yahoo, não falha no Bitcoin)
        try:
            dados = yf.download(ticker, period="1d", progress=False)['Close']
            if not dados.empty:
                if isinstance(dados, pd.DataFrame):
                    return float(dados.iloc[-1, 0])
                else:
                    return float(dados.iloc[-1])
        except:
            pass
            
    except:
        pass
        
    return 0.0

@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_cripto(ticker):
    """Motor Supremo: Mercado Bitcoin + Binance (Ignora o Yahoo)"""
    ticker = str(ticker).upper().strip()
    if not ticker: 
        return 0.0
        
    # Extrai só o nome da moeda (ex: BTC-BRL ou BTC vira apenas BTC)
    moeda = ticker.split('-')[0] if '-' in ticker else ticker
        
    # 1ª Tentativa: Mercado Bitcoin (Perfeito para BRL e não bloqueia nuvem)
    try:
        url_mb = f"https://www.mercadobitcoin.net/api/{moeda}/ticker/"
        req = urllib.request.Request(url_mb, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            dados = json.loads(response.read().decode())
            return float(dados['ticker']['last'])
    except:
        pass
        
    # 2ª Tentativa: Binance (A maior corretora do mundo)
    try:
        url_binance = f"https://api.binance.com/api/v3/ticker/price?symbol={moeda}BRL"
        req = urllib.request.Request(url_binance, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            dados = json.loads(response.read().decode())
            return float(dados['price'])
    except:
        pass
        
    return 0.0

@st.cache_data(ttl=86400, show_spinner=False)
def obter_dividendos(ticker):
    try:
        return yf.Ticker(ticker).dividends
    except:
        return pd.Series()

def salvar_historico(total_global, b3, fixa, cripto):
    arquivo = "historico_patrimonio.csv"
    hoje = date.today().strftime("%Y-%m-%d")
    
    # Criar o DataFrame com os dados de hoje
    novo_dado = pd.DataFrame([[hoje, total_global, b3, fixa, cripto]], 
                             columns=['Data', 'Total', 'B3', 'Renda Fixa', 'Cripto'])
    
    if not os.path.exists(arquivo):
        # Se o arquivo não existe, cria um novo
        novo_dado.to_csv(arquivo, index=False)
    else:
        df_hist = pd.read_csv(arquivo)
        # Só adiciona se a data de hoje ainda não estiver lá
        if hoje not in df_hist['Data'].values:
            df_hist = pd.concat([df_hist, novo_dado], ignore_index=True)
            df_hist.to_csv(arquivo, index=False)
    
    return pd.read_csv(arquivo)

# ==========================================
# ==========================================
# 2. MENU LATERAL (SIDEBAR)
# ==========================================
with st.sidebar:
    st.title("💼 Central Financeira")
    st.markdown("Bem-vindo ao seu terminal de investimentos inteligente.")
    st.divider()
    st.subheader("📁 1. Carregar Dados")
    st.markdown("Faça o upload do seu ficheiro Excel com as abas **B3**, **Cripto** e **Renda Fixa**.")
    arquivo_usuario = st.file_uploader("Upload do Excel de Investimentos", type=['xlsx'])
    st.divider()
    st.caption("Terminal desenvolvido com Inteligência de Dados e Análise Quantitativa.")

# Área principal de título
if arquivo_usuario is None:
    st.title("O Seu Terminal de Investimentos")
    st.info("👈 Por favor, carregue o seu ficheiro Excel (com as abas B3, Cripto e Renda Fixa) no menu lateral para inicializar o sistema.")
    st.stop() # Para a execução aqui até que o arquivo seja carregado

# ==========================================
# ==========================================
# ==========================================
# 4. LÓGICA PRINCIPAL E CÁLCULOS GERAIS
# ==========================================
try:
    with st.spinner("A processar e cruzar os seus dados..."):
        # --- LER O EXCEL ---
        xls = pd.ExcelFile(arquivo_usuario)
        abas_disponiveis = [aba.strip().lower() for aba in xls.sheet_names]
        
        # INICIALIZAÇÃO DE VARIÁVEIS DE SEGURANÇA (Para evitar erros 'not defined')
        patrimonio_b3 = 0.0
        patrimonio_atual = 0.0 # <--- A VARIÁVEL QUE ESTAVA FALTANDO!
        investido_b3 = 0.0
        lucro_b3_reais = 0.0
        rentabilidade_b3_pct = 0.0
        variacao_percentual_dia = 0.0
        
        valor_criptos_total = 0.0
        investido_criptos_total = 0.0 
        df_cripto = pd.DataFrame()
        
        saldo_renda_fixa = 0.0
        df_rf = pd.DataFrame()
        
        carteira = pd.DataFrame() # Caso não haja B3

        # --- 1. PROCESSAR ABA B3 ---
        if 'b3' in abas_disponiveis:
            nome_real_b3 = xls.sheet_names[abas_disponiveis.index('b3')]
            df_b3 = pd.read_excel(xls, nome_real_b3)
            df_b3.columns = df_b3.columns.str.lower().str.strip()
            df_b3['ativo_limpo'] = df_b3['ativo'].astype(str).str.split(' -').str[0].str.strip() + '.SA'
            
            def ajustar_quantidade(linha):
                direcao = str(linha['entrada/saída']).strip().lower()
                if direcao in ['credito', 'entrada', 'c']:
                    return linha['quantidade']
                elif direcao in ['debito', 'saída', 'saida', 'd']:
                    return -linha['quantidade']
                return 0

            df_b3['qtd_ajustada'] = df_b3.apply(ajustar_quantidade, axis=1)
            compras = df_b3[df_b3['qtd_ajustada'] > 0].copy()
            compras['custo_transacao'] = compras['quantidade'] * compras['preço']
            custo_compras = compras.groupby('ativo_limpo').agg(qtd_comprada=('quantidade', 'sum'), valor_gasto=('custo_transacao', 'sum')).reset_index()
            custo_compras['preco_medio'] = custo_compras['valor_gasto'] / custo_compras['qtd_comprada']
            posicao_atual = df_b3.groupby('ativo_limpo')['qtd_ajustada'].sum().reset_index()
            posicao_atual = posicao_atual[posicao_atual['qtd_ajustada'] > 0]
            carteira = pd.merge(posicao_atual, custo_compras[['ativo_limpo', 'preco_medio']], on='ativo_limpo', how='left')
            carteira.rename(columns={'ativo_limpo': 'ativo', 'qtd_ajustada': 'quantidade_total'}, inplace=True)
            carteira['custo_total_investido'] = carteira['quantidade_total'] * carteira['preco_medio']

            precos_atuais, valores_atuais_totais, lucros, lucros_percentuais, mm200_lista, max_52w_lista, min_52w_lista, tendencia_lista = [], [], [], [], [], [], [], []

            for index, linha in carteira.iterrows():
                try:
                    acao = yf.Ticker(linha['ativo'])
                    p_info = acao.fast_info
                    preco_hoje = p_info['lastPrice']
                    mm200 = p_info['twoHundredDayAverage']
                    max_52w = p_info['yearHigh']
                    min_52w = p_info['yearLow']
                except:
                    preco_hoje, mm200, max_52w, min_52w = 0.0, 0.0, 0.0, 0.0
                
                v_total = preco_hoje * linha['quantidade_total']
                precos_atuais.append(preco_hoje)
                valores_atuais_totais.append(v_total)
                lucros.append(v_total - linha['custo_total_investido'])
                lucros_percentuais.append(((v_total / linha['custo_total_investido']) - 1) * 100 if linha['custo_total_investido'] > 0 else 0)
                mm200_lista.append(mm200); max_52w_lista.append(max_52w); min_52w_lista.append(min_52w)
                tendencia_lista.append("🟢 Alta" if preco_hoje > mm200 else "🔴 Baixa")

            carteira['preco_atual'] = precos_atuais
            carteira['valor_patrimonio_atual'] = valores_atuais_totais
            carteira['lucro_prejuizo'] = lucros
            carteira['rentabilidade_%'] = lucros_percentuais
            carteira['MM200'] = mm200_lista; carteira['Min_52S'] = min_52w_lista; carteira['Max_52S'] = max_52w_lista; carteira['Tendência'] = tendencia_lista
            
            patrimonio_b3 = carteira['valor_patrimonio_atual'].sum()
            investido_b3 = carteira['custo_total_investido'].sum()
            lucro_b3_reais = patrimonio_b3 - investido_b3
            rentabilidade_b3_pct = (lucro_b3_reais / investido_b3 * 100) if investido_b3 > 0 else 0

            # Variação do dia B3
            variacao_total_dia, patrimonio_ontem = 0.0, 0.0
            vars_pct = []
            for ativo in carteira['ativo']:
                try:
                    tick = yf.Ticker(ativo).fast_info
                    p_atual, p_ant = tick['lastPrice'], tick['previousClose']
                    q = carteira.loc[carteira['ativo'] == ativo, 'quantidade_total'].values[0]
                    variacao_total_dia += (p_atual - p_ant) * q
                    patrimonio_ontem += p_ant * q
                    vars_pct.append(((p_atual / p_ant) - 1) * 100)
                except: vars_pct.append(0.0)
            variacao_percentual_dia = (variacao_total_dia / patrimonio_ontem) * 100 if patrimonio_ontem > 0 else 0
            carteira['var_dia_pct'] = vars_pct
        else:
            st.error("A aba 'B3' não foi encontrada. Crie uma aba chamada 'B3'.")
            st.stop()

        # --- 2. PROCESSAR ABA CRIPTO ---
        if 'cripto' in abas_disponiveis:
            nome_real_c = xls.sheet_names[abas_disponiveis.index('cripto')]
            df_c_raw = pd.read_excel(xls, nome_real_c)
            df_c_raw.columns = df_c_raw.columns.str.lower().str.strip()
            
            if not df_c_raw.empty and 'quantidade' in df_c_raw.columns:
                # Cálculo de saldo e preço médio
                df_c_raw['qtd_adj'] = df_c_raw.apply(lambda r: r['quantidade'] if str(r.get('entrada/saída', 'C')).strip().lower() in ['c','compra','entrada'] else -r['quantidade'], axis=1)
                custo_c = df_c_raw[df_c_raw['qtd_adj'] > 0].copy()
                custo_c['total_pago'] = custo_c['quantidade'] * custo_c.get('preço', 0)
                grp_custo = custo_c.groupby('ativo cripto').agg(q=('quantidade','sum'), v=('total_pago','sum')).reset_index()
                grp_custo['pm'] = np.where(grp_custo['q'] > 0, grp_custo['v'] / grp_custo['q'], 0)
                
                df_cripto = df_c_raw.groupby('ativo cripto')['qtd_adj'].sum().reset_index()
                df_cripto = df_cripto[df_cripto['qtd_adj'] > 0]
                df_cripto = pd.merge(df_cripto, grp_custo[['ativo cripto', 'pm']], on='ativo cripto', how='left')
                df_cripto.columns = ['Ativo Cripto', 'Quantidade', 'Preço Médio']
                
                p_atuais, v_atuais = [], []
                for _, row in df_cripto.iterrows():
                    p = obter_preco_cripto(row['Ativo Cripto'])
                    p_atuais.append(p)
                    v_atual = p * row['Quantidade']
                    v_atuais.append(v_atual)
                    valor_criptos_total += v_atual
                    investido_criptos_total += (row['Preço Médio'] * row['Quantidade'])
                
                df_cripto['Preço Atual (R$)'] = p_atuais
                df_cripto['Valor Atual (R$)'] = v_atuais
                df_cripto['Lucro/Prejuízo (R$)'] = df_cripto['Valor Atual (R$)'] - (df_cripto['Quantidade'] * df_cripto['Preço Médio'])
                df_cripto['Rentabilidade (%)'] = np.where(
                    (df_cripto['Quantidade'] * df_cripto['Preço Médio']) > 0, 
                    (df_cripto['Lucro/Prejuízo (R$)'] / (df_cripto['Quantidade'] * df_cripto['Preço Médio'])) * 100, 
                    0
                )

        # --- 3. PROCESSAR ABA RENDA FIXA ---
        if 'renda fixa' in abas_disponiveis:
            nome_real_rf = xls.sheet_names[abas_disponiveis.index('renda fixa')]
            df_rf = pd.read_excel(xls, nome_real_rf)
            df_rf.columns = df_rf.columns.str.strip()
            if 'Valor Atual' in df_rf.columns:
                saldo_renda_fixa = df_rf['Valor Atual'].sum()

    # ==========================================
    # 🌟 PAINEL DE PERFORMANCE E PATRIMÔNIO
    # ==========================================
    st.title("Visão Global do Patrimônio")
    
    # Soma Tudo (O Bolo Total)
    patrimonio_global_total = patrimonio_b3 + saldo_renda_fixa + valor_criptos_total
    
    # Desenha os 4 cartões lado a lado
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("🌍 Patrimônio Total", f"R$ {patrimonio_global_total:,.2f}")
    
    col2.metric(
        "📈 Lucro/Prejuízo (B3)", 
        f"R$ {lucro_b3_reais:,.2f}", 
        f"{rentabilidade_b3_pct:.2f}%"
    )
    
    col3.metric("🏦 Renda Fixa", f"R$ {saldo_renda_fixa:,.2f}")
    
    # Adicionando rentabilidade total das criptos se houver investimento
    if investido_criptos_total > 0:
        lucro_cripto_total = valor_criptos_total - investido_criptos_total
        rentabilidade_cripto_pct = (lucro_cripto_total / investido_criptos_total) * 100
        col4.metric("₿ Criptomoedas", f"R$ {valor_criptos_total:,.2f}", f"{rentabilidade_cripto_pct:.2f}%")
    else:
        col4.metric("₿ Criptomoedas", f"R$ {valor_criptos_total:,.2f}")
    
    # --- BARRA DE DISTRIBUIÇÃO (Visual) ---
    if patrimonio_global_total > 0:
        pct_b3 = (patrimonio_b3 / patrimonio_global_total) * 100
        pct_rf = (saldo_renda_fixa / patrimonio_global_total) * 100
        pct_cripto = (valor_criptos_total / patrimonio_global_total) * 100
        
        st.markdown(f"""
        <div style='width: 100%; height: 12px; display: flex; border-radius: 6px; overflow: hidden; margin-top: 15px;'>
            <div style='width: {pct_b3}%; background-color: #00CC96;' title='B3 (Ações/FIIs)'></div>
            <div style='width: {pct_rf}%; background-color: #FFA500;' title='Renda Fixa'></div>
            <div style='width: {pct_cripto}%; background-color: #9B59B6;' title='Criptomoedas'></div>
        </div>
        <div style='display: flex; justify-content: space-between; font-size: 13px; color: #888; margin-top: 5px; margin-bottom: 20px;'>
            <span>🟢 B3: {pct_b3:.1f}%</span>
            <span>🟠 Renda Fixa: {pct_rf:.1f}%</span>
            <span>🟣 Cripto: {pct_cripto:.1f}%</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.write("") # Espaço em branco

    # CRIA AS ABAS
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Visão Geral", 
        "💸 Renda Passiva", 
        "🛡️ Risco & Defesa", 
        "🧠 Inteligência de Mercado", 
        "⚙️ Gestão & Exportação",
        "💎 Outros Ativos"  # Nova aba!
    ])

    # ==========================================
    # ABA 1: VISÃO GERAL
    # ==========================================
    with tab1:
        with st.container(border=True):
            st.subheader("📊 Posição Atual e Indicadores Técnicos (B3)")
            colunas_exibicao = ["ativo", "quantidade_total", "preco_medio", "preco_atual", "Tendência", "MM200", "Min_52S", "Max_52S", "lucro_prejuizo", "rentabilidade_%"]
            st.dataframe(
                carteira[colunas_exibicao], use_container_width=True, hide_index=True,
                column_config={
                    "ativo": st.column_config.TextColumn("Ativo"), "quantidade_total": st.column_config.NumberColumn("Qtd Total", format="%d"),
                    "preco_medio": st.column_config.NumberColumn("Preço Médio", format="R$ %.2f"), "preco_atual": st.column_config.NumberColumn("Cotação Atual", format="R$ %.2f"),
                    "MM200": st.column_config.NumberColumn("Média 200d", format="R$ %.2f"), "Min_52S": st.column_config.NumberColumn("Mín (52 sem)", format="R$ %.2f"),
                    "Max_52S": st.column_config.NumberColumn("Máx (52 sem)", format="R$ %.2f"), "lucro_prejuizo": st.column_config.NumberColumn("Lucro/Prejuízo", format="R$ %.2f"),
                    "rentabilidade_%": st.column_config.NumberColumn("Retorno (%)", format="%.2f%%")
                }
            )

        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            with st.container(border=True):
                st.subheader("🗺️ Mapa de Calor (Desempenho Diário B3)")
                carteira['var_dia_reais'] = (carteira['valor_patrimonio_atual'] * (carteira['var_dia_pct'] / 100))
                carteira['font_size'] = (14 + carteira['var_dia_pct'].abs() * 2).clip(upper=22)
                fig_tree = px.treemap(
                    carteira, path=['ativo'], values='valor_patrimonio_atual', color='var_dia_pct', color_continuous_scale='RdYlGn', color_continuous_midpoint=0,
                    custom_data=['var_dia_pct', 'font_size', 'var_dia_reais'], labels={'var_dia_pct': 'Desempenho Hoje (%)'} 
                )
                fig_tree.update_traces(
                    textposition="middle center", texttemplate="<span style='font-size:%{customdata[1]}px'><b>%{label}</b></span><br><span style='font-size:%{customdata[1]}px'>%{customdata[0]:.2f}%</span>",
                    hovertemplate="<b>%{label}</b><br><br>Patrimônio: R$ %{value:,.2f}<br>Variação (%): %{customdata[0]:.2f}%<br>Variação (R$): <b>R$ %{customdata[2]:.2f}</b><extra></extra>"
                )
                fig_tree.update_layout(margin=dict(t=30, l=10, r=10, b=10), coloraxis_colorbar=dict(title="Oscilação do Dia"))
                fig_tree = padronizar_grafico(fig_tree)
                st.plotly_chart(fig_tree, use_container_width=True, theme=None)

        with col_t2:
            with st.container(border=True):
                st.subheader("🍕 Distribuição Global")
                # Criando um DataFrame consolidado para o gráfico de pizza
                pizza_data = []
                for _, row in carteira.iterrows():
                    pizza_data.append({'Ativo': row['ativo'], 'Valor': row['valor_patrimonio_atual'], 'Categoria': 'B3'})
                if 'Cripto' in xls.sheet_names and not df_cripto.empty:
                    for _, row in df_cripto.iterrows():
                         pizza_data.append({'Ativo': row['Ativo Cripto'], 'Valor': row['Valor Atual (R$)'], 'Categoria': 'Cripto'})
                if 'Renda Fixa' in xls.sheet_names and not df_rf.empty:
                     for _, row in df_rf.iterrows():
                         pizza_data.append({'Ativo': row['Ativo RF'], 'Valor': row['Valor Atual'], 'Categoria': 'Renda Fixa'})
                
                df_pizza = pd.DataFrame(pizza_data)
                
                fig_pie = px.pie(df_pizza, values='Valor', names='Ativo', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="%{label}<br>R$ %{value:,.2f}<br>%{percent}")
                fig_pie.update_layout(showlegend=False) 
                fig_pie = padronizar_grafico(fig_pie)
                st.plotly_chart(fig_pie, use_container_width=True, theme=None)

        with st.container(border=True):
            st.subheader("📈 Desempenho Acumulado: Carteira vs. Benchmarks")
            try:
                # Usa a menor data de entrada do Excel como início do gráfico
                data_inicial = pd.to_datetime(df_b3['data']).min().strftime('%Y-%m-%d')
            except:
                # Se não houver data no Excel, puxa 1 ano para trás
                data_inicial = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime('%Y-%m-%d')
            
            # Puxar histórico de cotações
            tickers_list = carteira['ativo'].tolist()
            dados_h = carregar_dados_yfinance(tickers_list + ['^BVSP'], start=data_inicial)

            # Puxar histórico do CDI
            try:
                data_hoje_str = pd.Timestamp.now().strftime('%d/%m/%Y')
                data_ini_str = pd.to_datetime(data_inicial).strftime('%d/%m/%Y')
                df_cdi_raw = carregar_cdi_historico(data_ini_str, data_hoje_str)
                retorno_cdi_acum = ((1 + df_cdi_raw['valor'] / 100).cumprod() - 1) * 100
            except:
                retorno_cdi_acum = pd.Series(0, index=dados_h.index)

            # 1. Calcular retorno acumulado de CADA ativo ((Preço Atual / Preço Inicial) - 1)
            ret_ativos = (dados_h / dados_h.iloc[0]) - 1
            
            # 2. Calcular o peso de cada ativo na carteira (usando patrimonio_b3)
            # AQUI ESTAVA O ERRO ANTES. Precisamos garantir que não divide por zero.
            if patrimonio_b3 > 0:
                pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_b3
            else:
                pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] * 0

            # 3. Multiplicar o retorno de cada ativo pelo seu peso na carteira
            cols_carteira = [t for t in tickers_list if t in ret_ativos.columns]
            
            # Criar o DataFrame final para o gráfico
            df_comp = pd.DataFrame({
                # Soma os retornos ponderados para ter a rentabilidade da carteira inteira
                'Minha Carteira': (ret_ativos[cols_carteira] * pesos).sum(axis=1) * 100,
                'Ibovespa': ret_ativos['^BVSP'] * 100 if '^BVSP' in ret_ativos.columns else 0,
                'CDI': retorno_cdi_acum
            }).ffill().fillna(0) # Preenche espaços vazios para não quebrar a linha

            # Desenha o Gráfico
            fig_comp = px.line(
                df_comp, 
                color_discrete_map={'Minha Carteira': '#00CC96', 'Ibovespa': '#EF553B', 'CDI': '#FFA500'},
                labels={'index': '', 'value': ''}
            )

            fig_comp.update_traces(
                line=dict(width=3), 
                hovertemplate="<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
            )

            fig_comp = padronizar_grafico(fig_comp)
            fig_comp.update_layout(
                hovermode="x unified",
                xaxis_title="", 
                yaxis_title="", 
                yaxis_ticksuffix="%", 
                legend=dict(title="", orientation="h", y=1.1, x=0.5, xanchor="center"), 
                margin=dict(l=60, b=60, t=40, r=20) 
            )

            st.plotly_chart(fig_comp, use_container_width=True, theme=None)

        # 1. Salva os dados atuais no histórico e recupera a lista completa
        df_historico = salvar_historico(patrimonio_global_total, patrimonio_b3, saldo_renda_fixa, valor_criptos_total)

        # 2. Criar o Gráfico de Evolução
        st.subheader("📈 Evolução do Patrimônio")
        
        if len(df_historico) > 1:
            fig_evolucao = px.area(
                df_historico, 
                x='Data', 
                y=['B3', 'Renda Fixa', 'Cripto'],
                title="Crescimento Patrimonial por Categoria",
                color_discrete_map={'B3': '#00CC96', 'Renda Fixa': '#FFA500', 'Cripto': '#9B59B6'},
                labels={'value': 'Valor (R$)', 'Data': '', 'variable': 'Ativo'}
            )
            
            fig_evolucao = padronizar_grafico(fig_evolucao)
            fig_evolucao.update_layout(hovermode="x unified", margin=dict(b=40))
            
            st.plotly_chart(fig_evolucao, use_container_width=True)
        else:
            st.info("📊 O gráfico de evolução aparecerá aqui assim que tivermos dados de mais de um dia. Volte amanhã para ver o primeiro ponto de crescimento!")


    # ==========================================
    # ABA 2: RENDA PASSIVA
    # ==========================================
    with tab2:
        with st.container(border=True):
            st.subheader("💸 Máquina de Dividendos (Projeção 12 Meses)")
            dividendos_totais = []
            for ativo in carteira['ativo']:
                divs = obter_dividendos(ativo)
                if not divs.empty:
                    data_corte = pd.Timestamp.now(tz=divs.index.tz) - pd.DateOffset(years=1)
                    divs_12m = divs[divs.index >= data_corte]
                    total_pago_por_acao = divs_12m.sum()
                else:
                    total_pago_por_acao = 0.0
                dividendos_totais.append(total_pago_por_acao)

            carteira_divs = carteira.copy()
            carteira_divs['div_por_acao_12m'] = dividendos_totais
            carteira_divs['renda_passiva_anual'] = carteira_divs['quantidade_total'] * carteira_divs['div_por_acao_12m']

            renda_anual_total = carteira_divs['renda_passiva_anual'].sum()
            renda_mensal_media = renda_anual_total / 12

            col_rp1, col_rp2 = st.columns(2)
            col_rp1.metric("Projeção de Dividendos (1 Ano)", f"R$ {renda_anual_total:,.2f}")
            col_rp2.metric("Média Mensal Estimada", f"R$ {renda_mensal_media:,.2f}")

            df_grafico_divs = carteira_divs[carteira_divs['renda_passiva_anual'] > 0].sort_values(by='renda_passiva_anual', ascending=False)
            
            if not df_grafico_divs.empty:
                fig_divs = px.bar(
                    df_grafico_divs, x='ativo', y='renda_passiva_anual', title="Quais ações pagam as suas contas?",
                    labels={'renda_passiva_anual': 'Renda Anual (R$)', 'ativo': 'Ação'}, text_auto='.2s', 
                    color='renda_passiva_anual', color_continuous_scale=px.colors.sequential.Greens 
                )
                fig_divs.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
                fig_divs = padronizar_grafico(fig_divs)
                fig_divs.update_layout(margin=dict(b=80))
                fig_divs.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_divs, use_container_width=True, theme=None)
            else:
                st.info("Nenhuma ação pagou dividendos nos últimos 12 meses.")

        with st.container(border=True):
            st.subheader("📅 Próximos Dividendos e JCP (Agenda Oficial)")
            if st.button("🚀 Consultar Editais de Pagamento"):
                agenda_list = []
                for ativo in carteira['ativo']:
                    try:
                        cal = yf.Ticker(ativo).calendar
                        if 'Dividend Date' in cal and pd.notnull(cal['Dividend Date']):
                            agenda_list.append({
                                'Ativo': ativo, 'Previsão de Pagamento': cal['Dividend Date'].strftime('%d/%m/%Y'),
                                'Tipo': 'Dividendo/JCP', 'Status': 'Anunciado'
                            })
                    except: continue

                if agenda_list:
                    st.success("✅ Novos pagamentos identificados!")
                    st.dataframe(pd.DataFrame(agenda_list), use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum novo pagamento anunciado recentemente.")


    # ==========================================
    # ABA 3: RISCO & DEFESA
    # ==========================================
    with tab3:
        with st.container(border=True):
            st.subheader("🛡️ Teste de Stress: Cenários de Crise")
            cenarios = {"Joesley Day (Maio 2017)": "2017-05-15", "Greve dos Caminhoneiros (Maio 2018)": "2018-05-18", "Início da Pandemia (Março 2020)": "2020-03-02"}
            escolha_crise = st.selectbox("Escolha o cenário de crise para simular:", list(cenarios.keys()))
            data_inicio = cenarios[escolha_crise]
            data_fim = (pd.to_datetime(data_inicio) + pd.DateOffset(days=30)).strftime('%Y-%m-%d')

            if st.button("🚨 Iniciar Simulação de Crise"):
                tickers_stress = carteira['ativo'].tolist()
                dados_crise = carregar_dados_yfinance(tickers_stress + ['^BVSP'], start=data_inicio, end=data_fim)

                if len(dados_crise) < 5:
                    st.error("Dados insuficientes para este período.")
                else:
                    ativos_validos = [t for t in tickers_stress if t in dados_crise.columns and not dados_crise[t].isnull().all()]
                    valor_total_existente = carteira[carteira['ativo'].isin(ativos_validos)]['valor_patrimonio_atual'].sum()
                    pesos_stress = carteira[carteira['ativo'].isin(ativos_validos)].set_index('ativo')['valor_patrimonio_atual'] / valor_total_existente
                    retornos_crise = (dados_crise / dados_crise.iloc[0]) - 1
                    desempenho_carteira = (retornos_crise[ativos_validos] * pesos_stress).sum(axis=1) * 100
                    desempenho_ibov = retornos_crise['^BVSP'] * 100 if '^BVSP' in retornos_crise.columns else 0

                    df_stress = pd.DataFrame({'A Minha Carteira': desempenho_carteira, 'Ibovespa': desempenho_ibov})
                    fig_stress = px.line(df_stress, title=f"Impacto na Carteira: {escolha_crise}", color_discrete_map={'A Minha Carteira': '#00CC96', 'Ibovespa': '#EF553B'})
                    fig_stress.update_traces(line=dict(width=3), hovertemplate="<b>%{fullData.name}</b><br>Data: %{x|%d/%m/%Y}<br>Variação: <b>%{y:.2f}%</b><extra></extra>")
                    fig_stress.update_layout(hovermode="x unified", xaxis=dict(showgrid=False), yaxis=dict(ticksuffix="%"))
                    fig_stress = padronizar_grafico(fig_stress)
                    st.plotly_chart(fig_stress, use_container_width=True, theme=None)

                    queda_max = df_stress['A Minha Carteira'].min()
                    st.error(f"⚠️ No pior momento desta crise, a sua carteira teria caído **{queda_max:.2f}%**.")

        with st.container(border=True):
            st.subheader("🌊 Análise de Drawdown (Gráfico Underwater)")
            if st.button("📉 Analisar Profundidade de Queda (1 Ano)"):
                tickers_draw = carteira['ativo'].tolist()
                dados_draw = carregar_dados_yfinance(tickers_draw, period="1y")
                retornos_ativos = (dados_draw / dados_draw.iloc[0])
                pesos_draw = (carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_atual).values
                cols_validas = [t for t in tickers_draw if t in retornos_ativos.columns]
                patrimonio_historico = (retornos_ativos[cols_validas] * pesos_draw).sum(axis=1)

                picos_historicos = patrimonio_historico.cummax()
                drawdowns = (patrimonio_historico / picos_historicos - 1) * 100
                df_underwater = pd.DataFrame({'Drawdown (%)': drawdowns}, index=patrimonio_historico.index)

                fig_under = px.area(df_underwater, y='Drawdown (%)', color_discrete_sequence=['#EF553B'])
                fig_under.update_traces(hovertemplate="Data: %{x|%d/%m/%Y}<br>Queda: <b>%{y:.2f}%</b><extra></extra>")
                fig_under.update_layout(yaxis_ticksuffix="%", hovermode="x unified", yaxis_range=[-max(abs(drawdowns))*1.2, 0])
                fig_under = padronizar_grafico(fig_under)
                st.plotly_chart(fig_under, use_container_width=True, theme=None)

                c1, c2 = st.columns(2)
                max_d = drawdowns.min()
                c1.metric("Pior Queda do Ano", f"{max_d:.2f}%")
                c2.metric("Esforço de Subida Necessário", f"{(1 / (1 + max_d/100) - 1) * 100:.2f}%")

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            with st.container(border=True):
                st.subheader("📊 Matriz de Correlação")
                if st.button("🧬 Gerar Matriz de Risco"):
                    tickers_corr = carteira['ativo'].tolist()
                    dados_corr = carregar_dados_yfinance(tickers_corr, period="1y")
                    matriz_corr = dados_corr.pct_change().dropna().corr()

                    fig_corr = px.imshow(matriz_corr, text_auto=".2f", aspect="auto", color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
                    
                    fig_corr = padronizar_grafico(fig_corr)
                    
                    altura_dinamica = max(500, len(tickers_corr) * 45)
                    
                    fig_corr.update_layout(
                        height=altura_dinamica, 
                        margin=dict(l=100, b=100) 
                    )
                    
                    fig_corr.update_xaxes(tickangle=-45, tickfont=dict(size=10), dtick=1)
                    fig_corr.update_yaxes(tickfont=dict(size=10), dtick=1)
                    
                    st.plotly_chart(fig_corr, use_container_width=True, theme=None)

        with col_r2:
            with st.container(border=True):
                st.subheader("🌎 Sensibilidade Cambial")
                if st.button("💵 Analisar Exposição ao Dólar"):
                    tickers_macro = carteira['ativo'].tolist()
                    dados_macro = carregar_dados_yfinance(tickers_macro + ['USDBRL=X'], period="1y")
                    retornos_macro = dados_macro.pct_change().dropna()
                    pesos_macro = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_atual
                    cols_validas = [t for t in tickers_macro if t in retornos_macro.columns]
                    retornos_macro['Minha Carteira'] = (retornos_macro[cols_validas] * pesos_macro).sum(axis=1)

                    if 'USDBRL=X' in retornos_macro.columns:
                        correl_dolar = retornos_macro['Minha Carteira'].corr(retornos_macro['USDBRL=X'])
                        st.metric("Correlação com USD", f"{correl_dolar:.2f}")
                        
                        tipo_tendencia = "ols" if TEM_STATSMODELS else None
                        fig_macro = px.scatter(
                            retornos_macro, x='USDBRL=X', y='Minha Carteira', trendline=tipo_tendencia,
                            labels={'USDBRL=X': 'Var. Dólar (%)', 'Minha Carteira': 'Var. Carteira (%)'}
                        )
                        fig_macro.update_traces(marker=dict(size=10, color='#00CC96', opacity=0.6))
                        fig_macro = padronizar_grafico(fig_macro)
                        st.plotly_chart(fig_macro, use_container_width=True, theme=None)

    # ==========================================
    # ABA 4: INTELIGÊNCIA DE MERCADO
    # ==========================================
    with tab4:
        with st.container(border=True):
            st.subheader("💎 Valuation Real (Graham & Bazin)")
            yield_desejado = st.slider("Yield Mínimo Desejado (Bazin) %:", 4.0, 12.0, 6.0) / 100
            if st.button("🔍 Calcular Valuation"):
                valuation_list = []
                for ativo in carteira['ativo']:
                    try:
                        preco_atual = obter_preco_atual(ativo)
                        historico_divs = obter_dividendos(ativo)
                        div_anual_real = historico_divs[historico_divs.index >= (pd.Timestamp.now(tz=historico_divs.index.tz) - pd.DateOffset(years=1))].sum() if not historico_divs.empty else 0
                        info = yf.Ticker(ativo).info
                        lpa, vpa = info.get('trailingEps'), info.get('bookValue')
                        preco_bazin = div_anual_real / yield_desejado if div_anual_real > 0 else np.nan
                        preco_graham = np.sqrt(22.5 * lpa * vpa) if (lpa and vpa and lpa > 0 and vpa > 0) else np.nan
                        margem_graham = ((preco_graham / preco_atual) - 1) * 100 if pd.notnull(preco_graham) else np.nan

                        valuation_list.append({
                            'Ativo': ativo, 'Preço': preco_atual, 'P. Teto (Bazin)': preco_bazin, 'P. Justo (Graham)': preco_graham,
                            'Margem Graham (%)': margem_graham, 'Status Bazin': "✅ Comprar" if preco_atual < preco_bazin else "❌ Caro"
                        })
                    except: continue

                df_val = pd.DataFrame(valuation_list)
                st.dataframe(df_val.style.format({'Preço': 'R$ {:.2f}', 'P. Teto (Bazin)': 'R$ {:.2f}', 'P. Justo (Graham)': 'R$ {:.2f}', 'Margem Graham (%)': '{:.2f}%'}, na_rep="N/A"), use_container_width=True, hide_index=True)

        with st.container(border=True):
            st.subheader("🎯 Otimização de Portfólio (Markowitz)")
            if st.button("🧬 Calcular Carteira Ótima"):
                tickers_opt = carteira['ativo'].tolist()
                dados_opt = carregar_dados_yfinance(tickers_opt, period="1y").pct_change().dropna()
                retornos_anuais, cov_matriz = dados_opt.mean() * 252, dados_opt.cov() * 252
                
                resultados = np.zeros((3, 5000))
                pesos_recorde = []

                for i in range(5000):
                    weights = np.random.random(len(tickers_opt))
                    weights /= np.sum(weights)
                    pesos_recorde.append(weights)
                    resultados[0,i] = np.sum(retornos_anuais * weights)
                    resultados[1,i] = np.sqrt(np.dot(weights.T, np.dot(cov_matriz, weights)))
                    resultados[2,i] = resultados[0,i] / resultados[1,i]

                max_sharpe_idx = resultados[2].argmax()
                pesos_otimos = pesos_recorde[max_sharpe_idx]

                fig_mark = px.scatter(pd.DataFrame({'Retorno': resultados[0], 'Risco': resultados[1], 'Sharpe': resultados[2]}), x='Risco', y='Retorno', color='Sharpe', color_continuous_scale='Viridis')
                fig_mark.add_scatter(x=[resultados[1, max_sharpe_idx]], y=[resultados[0, max_sharpe_idx]], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='Ótimo')
                fig_mark = padronizar_grafico(fig_mark)
                st.plotly_chart(fig_mark, use_container_width=True, theme=None)

                df_pesos = pd.DataFrame({'Ativo': tickers_opt, 'Peso Atual (%)': (carteira['valor_patrimonio_atual'] / patrimonio_atual * 100).values, 'Sugerido (%)': pesos_otimos * 100})
                st.dataframe(df_pesos.style.format({'Peso Atual (%)': '{:.2f}%', 'Sugerido (%)': '{:.2f}%'}), use_container_width=True, hide_index=True)

        col_ia1, col_ia2 = st.columns(2)
        with col_ia1:
            with st.container(border=True):
                st.subheader("🎲 Monte Carlo")
                anos = st.slider("Anos de projeção:", 1, 30, 10)
                aporte_mensal = st.number_input("Aporte Mensal (R$):", value=1000.0)
                if st.button("🎲 Rodar Simulação"):
                    hist = carregar_dados_yfinance(carteira['ativo'].tolist(), period="1y").pct_change().dropna()
                    if isinstance(hist, pd.Series): hist = hist.to_frame()
                    pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / carteira['valor_patrimonio_atual'].sum()
                    mu, sigma = (hist.mean() * pesos).sum(), (hist * pesos).sum(axis=1).std()
                    
                    sims = np.zeros((anos * 252, 100))
                    for s in range(100):
                        p = [carteira['valor_patrimonio_atual'].sum()]
                        for d in range(1, anos * 252): p.append(p[-1] * (1 + np.random.normal(mu, sigma)) + (aporte_mensal/21))
                        sims[:, s] = p
                    
                    df_stats = pd.DataFrame(sims).quantile([0.1, 0.5, 0.9], axis=1).T
                    df_stats.columns = ['Pessimista', 'Mediana', 'Otimista']
                    fig_mc = px.line(df_stats)
                    fig_mc = padronizar_grafico(fig_mc)
                    st.plotly_chart(fig_mc, use_container_width=True, theme=None)

        with col_ia2:
            with st.container(border=True):
                st.subheader("🗓️ Sazonalidade (Heatmap Mensal)")
                ativo_escolhido = st.selectbox("Ativo para Raio-X:", carteira['ativo'].tolist())
                if st.button("🔍 Vasculhar Padrões"):
                    dados_saz = carregar_dados_yfinance([ativo_escolhido], start=(pd.Timestamp.now() - pd.DateOffset(years=10)).strftime('%Y-%m-%d'))
                    retornos_mensais = dados_saz.resample('ME').last().pct_change().dropna() * 100
                    df_saz = pd.DataFrame({'Retorno': retornos_mensais.values.flatten(), 'Ano': retornos_mensais.index.year, 'Mês': retornos_mensais.index.month})
                    matriz_saz = df_saz.pivot(index='Ano', columns='Mês', values='Retorno')
                    
                    fig_saz = px.imshow(matriz_saz, text_auto=".1f", color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
                    fig_saz = padronizar_grafico(fig_saz)
                    st.plotly_chart(fig_saz, use_container_width=True, theme=None)

        with st.container(border=True):
            st.subheader("📰 Radar de Notícias")
            ativo_noticia = st.selectbox("Selecione um ativo para ler as notícias recentes:", carteira['ativo'].tolist(), key="news_select")
            try:
                for n in yf.Ticker(ativo_noticia).news[:3]:  
                    titulo = n.get('title') or n.get('content', {}).get('title', 'Notícia')
                    link = n.get('link') or n.get('content', {}).get('clickThroughUrl', {}).get('url', '#')
                    st.markdown(f"**[{titulo}]({link})**")
            except: st.info("Sem notícias recentes.")

    # ==========================================
    # ABA 5: GESTÃO & EXPORTAÇÃO
    # ==========================================
    with tab5:
        with st.container(border=True):
            st.subheader("⚖️ Rebalanceamento Automático")
            novo_aporte = st.number_input("Valor do Novo Aporte (R$):", value=1000.0, step=100.0)
            df_alvos = pd.DataFrame({'Ativo': carteira['ativo'].tolist(), 'Alvo (%)': [100.0/len(carteira)] * len(carteira)})
            alvos_editados = st.data_editor(df_alvos, num_rows="dynamic", use_container_width=True)

            if abs(alvos_editados['Alvo (%)'].sum() - 100.0) < 0.01 and st.button("🚀 Calcular Ordens"):
                patrimonio_futuro_total = carteira['valor_patrimonio_atual'].sum() + novo_aporte
                ordens = []
                for _, row in alvos_editados.iterrows():
                    ativo, alvo_pct = str(row['Ativo']).upper().strip(), row['Alvo (%)'] / 100.0
                    valor_atual = carteira.loc[carteira['ativo'] == ativo, 'valor_patrimonio_atual'].values[0] if ativo in carteira['ativo'].values else 0.0
                    preco_ativo = obter_preco_atual(ativo)
                    qtd = int((patrimonio_futuro_total * alvo_pct - valor_atual) / preco_ativo) if preco_ativo > 0 else 0
                    if qtd != 0: ordens.append({'Operação': "COMPRAR" if qtd > 0 else "VENDER", 'Ativo': ativo, 'Qtd': abs(qtd), 'Total (R$)': abs(qtd * preco_ativo)})
                
                def colorir(val): return 'color: #2e7d32; font-weight: bold' if val == 'COMPRAR' else ('color: #c62828; font-weight: bold' if val == 'VENDER' else '')
                st.dataframe(pd.DataFrame(ordens).style.map(colorir, subset=['Operação']), use_container_width=True, hide_index=True)

        with st.container(border=True):
            st.subheader("📄 Relatório Executivo (Exportar PDF)")
            st.markdown("""<style>@media print { [data-testid="stSidebar"], header, footer { display: none !important; } .block-container { max-width: 100% !important; padding: 0 !important; } }</style>""", unsafe_allow_html=True)
            html_botao = """<div style="text-align: center;"><button onclick="window.parent.print()" style="background-color: #00CC96; color: #111; border: none; padding: 15px 30px; font-size: 18px; font-weight: bold; border-radius: 8px; cursor: pointer;">🖨️ Gerar Relatório em PDF</button></div>"""
            st.components.v1.html(html_botao, height=70)
            
    # ==========================================
    # ==========================================
    # ABA 6: OUTROS ATIVOS
    # ==========================================
    with tab6:
        st.header("💎 Visão Detalhada: Criptomoedas e Renda Fixa")
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            with st.container(border=True):
                st.subheader("₿ Criptomoedas")
                if 'Cripto' in xls.sheet_names and not df_cripto.empty:
                    st.dataframe(
                        df_cripto,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Ativo Cripto": st.column_config.TextColumn("Ativo"),
                            "Quantidade": st.column_config.NumberColumn("Qtd", format="%.4f"),
                            "Preço Médio": st.column_config.NumberColumn("Preço Médio", format="R$ %.2f"),
                            "Preço Atual (R$)": st.column_config.NumberColumn("Cotação Atual", format="R$ %.2f"),
                            "Valor Atual (R$)": st.column_config.NumberColumn("Total Atual", format="R$ %.2f"),
                            "Lucro/Prejuízo (R$)": st.column_config.NumberColumn("L/P", format="R$ %.2f"),
                            "Rentabilidade (%)": st.column_config.NumberColumn("Retorno", format="%.2f%%")
                        }
                    )
                else:
                    st.info("Nenhuma aba 'Cripto' encontrada ou a aba está vazia. Crie uma aba 'Cripto' no seu Excel com as colunas: 'Ativo Cripto', 'Entrada/Saída', 'Quantidade' e 'Preço'.")
                    
        with col_c2:
            with st.container(border=True):
                st.subheader("🏦 Renda Fixa")
                if 'Renda Fixa' in xls.sheet_names and not df_rf.empty:
                    st.dataframe(
                        df_rf,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Ativo RF": st.column_config.TextColumn("Ativo"),
                            "Valor Investido": st.column_config.NumberColumn("Investido", format="R$ %.2f"),
                            "Valor Atual": st.column_config.NumberColumn("Atual", format="R$ %.2f")
                        }
                    )
                else:
                    st.info("Nenhuma aba 'Renda Fixa' encontrada. Crie uma aba 'Renda Fixa' no seu Excel com as colunas: 'Ativo RF', 'Valor Investido' e 'Valor Atual'.")


except Exception as e:
    st.error(f"Erro ao processar ficheiro: {e}")