import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import numpy as np  # <--- A importação que faltava!

# 1. Configuração inicial da página
st.set_page_config(page_title="Gestão de Carteira B3", layout="wide")
st.title("💼 O Meu Dashboard de Investimentos B3")

# 2. Área de Upload do ficheiro Excel
st.subheader("📁 Carregar o Relatório da B3")
st.write("Faça o upload do seu ficheiro Excel de movimentação descarregado da B3.")

arquivo_usuario = st.file_uploader("Escolha o ficheiro Excel", type=['xlsx'])

# 3. Função para buscar preços em tempo real (com cache para ser mais rápido)
@st.cache_data(ttl=300) # Atualiza a cada 5 minutos no máximo
def obter_preco_atual(ticker):
    try:
        acao = yf.Ticker(ticker)
        return acao.fast_info['lastPrice'] 
    except:
        return 0.0

# 4. Lógica principal (só corre se o ficheiro for inserido)
if arquivo_usuario is not None:
    try:
        # Ler o Excel
        df_b3 = pd.read_excel(arquivo_usuario)
        
        # Padronizar o nome das colunas para minúsculas para evitar erros de digitação
        df_b3.columns = df_b3.columns.str.lower().str.strip()
        
        # Extrair apenas o Ticker do Ativo e adicionar '.SA' para o Yahoo Finance
        # Ex: transforma "PETR4 - PETROLEO..." em "PETR4.SA"
        df_b3['ativo_limpo'] = df_b3['ativo'].astype(str).str.split(' -').str[0].str.strip() + '.SA'
        
        # Função para determinar se a quantidade soma (compra) ou subtrai (venda)
        def ajustar_quantidade(linha):
            direcao = str(linha['entrada/saída']).strip().lower()
            # Na B3, 'credito' significa que o ativo entrou na sua conta (compra)
            if direcao in ['credito', 'entrada', 'c']:
                return linha['quantidade']
            # 'debito' significa que o ativo saiu da sua conta (venda)
            elif direcao in ['debito', 'saída', 'saida', 'd']:
                return -linha['quantidade']
            return 0

        df_b3['qtd_ajustada'] = df_b3.apply(ajustar_quantidade, axis=1)
        
        # Separar apenas as compras para calcular o Preço Médio
        compras = df_b3[df_b3['qtd_ajustada'] > 0].copy()
        compras['custo_transacao'] = compras['quantidade'] * compras['preço']
        
        # Agrupar compras por ativo
        custo_compras = compras.groupby('ativo_limpo').agg(
            qtd_comprada=('quantidade', 'sum'),
            valor_gasto=('custo_transacao', 'sum')
        ).reset_index()
        
        # Calcular Preço Médio
        custo_compras['preco_medio'] = custo_compras['valor_gasto'] / custo_compras['qtd_comprada']
        
        # Calcular Posição Atual (Quantidade comprada menos quantidade vendida)
        posicao_atual = df_b3.groupby('ativo_limpo')['qtd_ajustada'].sum().reset_index()
        
        # Filtrar para manter apenas os ativos que ainda tem na carteira
        posicao_atual = posicao_atual[posicao_atual['qtd_ajustada'] > 0]
        
        # Unir a posição atual com o preço médio
        carteira = pd.merge(posicao_atual, custo_compras[['ativo_limpo', 'preco_medio']], on='ativo_limpo', how='left')
        carteira.rename(columns={'ativo_limpo': 'ativo', 'qtd_ajustada': 'quantidade_total'}, inplace=True)
        
        # Calcular o capital investido na posição atual
        carteira['custo_total_investido'] = carteira['quantidade_total'] * carteira['preco_medio']

        st.success("Ficheiro processado com sucesso! A carregar cotações de mercado...")

       # 5. Buscar preços de mercado, indicadores técnicos e calcular lucros
        precos_atuais = []
        valores_atuais_totais = []
        lucros = []
        lucros_percentuais = []
        mm200_lista = []
        max_52w_lista = []
        min_52w_lista = []
        tendencia_lista = []

        with st.spinner("A carregar cotações e indicadores técnicos..."):
            for index, linha in carteira.iterrows():
                try:
                    acao = yf.Ticker(linha['ativo'])
                    # O fast_info traz os indicadores instantaneamente
                    preco_hoje = acao.fast_info['lastPrice']
                    mm200 = acao.fast_info['twoHundredDayAverage']
                    max_52w = acao.fast_info['yearHigh']
                    min_52w = acao.fast_info['yearLow']
                except:
                    preco_hoje, mm200, max_52w, min_52w = 0.0, 0.0, 0.0, 0.0
                
                valor_hoje_total = preco_hoje * linha['quantidade_total']
                lucro_monetario = valor_hoje_total - linha['custo_total_investido']
                lucro_percentual = (lucro_monetario / linha['custo_total_investido']) * 100 if linha['custo_total_investido'] > 0 else 0
                
                precos_atuais.append(preco_hoje)
                valores_atuais_totais.append(valor_hoje_total)
                lucros.append(lucro_monetario)
                lucros_percentuais.append(lucro_percentual)
                mm200_lista.append(mm200)
                max_52w_lista.append(max_52w)
                min_52w_lista.append(min_52w)
                
                # Definir tendência (Acima ou Abaixo da MM200)
                if preco_hoje > mm200:
                    tendencia_lista.append("🟢 Alta (Acima MM200)")
                else:
                    tendencia_lista.append("🔴 Baixa (Abaixo MM200)")

        # Adicionar os novos dados ao DataFrame da carteira
        carteira['preco_atual'] = precos_atuais
        carteira['valor_patrimonio_atual'] = valores_atuais_totais
        carteira['lucro_prejuizo'] = lucros
        carteira['rentabilidade_%'] = lucros_percentuais
        carteira['MM200'] = mm200_lista
        carteira['Min_52S'] = min_52w_lista
        carteira['Max_52S'] = max_52w_lista
        carteira['Tendência'] = tendencia_lista

        # ====================================================================
        # 6. TABELA DE POSIÇÃO ATUAL (VISUAL PROFISSIONAL)
        # ====================================================================
        st.divider()
        st.subheader("📊 Posição Atual e Indicadores Técnicos")

        # Criamos um mapeamento de nomes "feios" para nomes "bonitos"
        nomes_colunas = {
            "ativo": "Ativo",
            "quantidade_total": "Quantidade",
            "preco_medio": "Preço Médio",
            "preco_atual": "Cotação Atual",
            "Tendência": "Tendência",
            "MM200": "Média 200 Dias",
            "Min_52S": "Mín (52 sem)",
            "Max_52S": "Máx (52 sem)",
            "lucro_prejuizo": "Lucro/Prejuízo (R$)",
            "rentabilidade_%": "Retorno (%)"
        }

        # Selecionamos as colunas que queremos exibir na ordem correta
        colunas_exibicao = list(nomes_colunas.keys())

        # Exibição com formatação de moeda e nomes limpos
        st.dataframe(
            carteira[colunas_exibicao],
            use_container_width=True,
            hide_index=True,
            column_config={
                "ativo": st.column_config.TextColumn("Ativo"),
                "quantidade_total": st.column_config.NumberColumn("Qtd Total", format="%d"),
                "preco_medio": st.column_config.NumberColumn("Preço Médio", format="R$ %.2f"),
                "preco_atual": st.column_config.NumberColumn("Cotação Atual", format="R$ %.2f"),
                "MM200": st.column_config.NumberColumn("Média 200d", format="R$ %.2f"),
                "Min_52S": st.column_config.NumberColumn("Mín (52 sem)", format="R$ %.2f"),
                "Max_52S": st.column_config.NumberColumn("Máx (52 sem)", format="R$ %.2f"),
                "lucro_prejuizo": st.column_config.NumberColumn("Lucro/Prejuízo", format="R$ %.2f"),
                "rentabilidade_%": st.column_config.NumberColumn("Retorno (%)", format="%.2f%%")
            }
        )

        # ====================================================================
        # 7 e 8. RESUMO GLOBAL, TERMÔMETRO E MAPA DE CALOR
        # ====================================================================
        st.divider()
        st.subheader("💰 Resumo Global & Termómetro Diário")
        
        with st.spinner("A calcular o desempenho de hoje frente ao fecho de ontem..."):
            patrimonio_investido = carteira['custo_total_investido'].sum()
            patrimonio_atual = carteira['valor_patrimonio_atual'].sum()
            lucro_global = patrimonio_atual - patrimonio_investido
            rentabilidade_global = (lucro_global / patrimonio_investido) * 100 if patrimonio_investido > 0 else 0
            
            # --- Lógica do Termómetro Diário e Mapa de Calor ---
            variacao_total_dia = 0.0
            patrimonio_ontem = 0.0
            variacoes_individuais_pct = [] # NOVA LISTA: Vai guardar o valor de cada ação para o gráfico

            for ativo in carteira['ativo']:
                try:
                    acao = yf.Ticker(ativo)
                    preco_atual = acao.fast_info['lastPrice']
                    preco_anterior = acao.fast_info['previousClose']
                    qtd = carteira.loc[carteira['ativo'] == ativo, 'quantidade_total'].values[0]
                    
                    # 1. Conta para o Termômetro (Dinheiro total)
                    variacao_total_dia += (preco_atual - preco_anterior) * qtd
                    patrimonio_ontem += preco_anterior * qtd
                    
                    # 2. Conta para o Mapa de Calor (Porcentagem individual da ação)
                    v_pct = ((preco_atual / preco_anterior) - 1) * 100
                    variacoes_individuais_pct.append(v_pct)
                except:
                    variacoes_individuais_pct.append(0.0) # Fallback em caso de erro na internet
            
            variacao_percentual_dia = (variacao_total_dia / patrimonio_ontem) * 100 if patrimonio_ontem > 0 else 0

            # A MÁGICA AQUI: Adiciona a coluna que faltava no DataFrame!
            carteira['var_dia_pct'] = variacoes_individuais_pct

            # --- Exibir as métricas ---
            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Total Investido", f"R$ {patrimonio_investido:,.2f}")
            col2.metric("Património Atual", f"R$ {patrimonio_atual:,.2f}", f"{rentabilidade_global:.2f}% (Histórico)")
            col3.metric("Lucro/Prejuízo Total", f"R$ {lucro_global:,.2f}")
            col4.metric(
                label="Desempenho APENAS Hoje", 
                value=f"R$ {variacao_total_dia:,.2f}", 
                delta=f"{variacao_percentual_dia:.2f}%"
            )

        # --- 2. MAPA DE CALOR (TREEMAP) ---
        st.divider()
        st.subheader("🗺️ Mapa de Calor da Carteira (Heatmap)")

        # Cálculo da variação em Reais para o hover
        # (Patrimônio Atual * Porcentagem de Variação) / 100
        carteira['var_dia_reais'] = (carteira['valor_patrimonio_atual'] * (carteira['var_dia_pct'] / 100))
        
        carteira['var_dia_pct'] = carteira['var_dia_pct'].fillna(0.0)
        
        # Tamanho dinâmico seguro (limite de 22px para não quebrar o layout)
        carteira['font_size'] = (14 + carteira['var_dia_pct'].abs() * 2).clip(upper=22)

        fig_tree = px.treemap(
            carteira, 
            path=['ativo'], 
            values='valor_patrimonio_atual',
            color='var_dia_pct', 
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0,
            # Passamos a Variação em %, Tamanho da Fonte e Variação em R$
            custom_data=['var_dia_pct', 'font_size', 'var_dia_reais'],
            # TROCA O NOME NO TERMÔMETRO:
            labels={'var_dia_pct': 'Desempenho Hoje (%)'} 
        )

        fig_tree.update_traces(
            textposition="middle center",
            # Texto exibido no quadrado (limpo)
            texttemplate=(
                "<span style='font-size:%{customdata[1]}px'><b>%{label}</b></span><br>"
                "<span style='font-size:%{customdata[1]}px'>%{customdata[0]:.2f}%</span>"
            ),
            # BALÃO DE INFORMAÇÕES (HOVER) PERSONALIZADO
            hovertemplate=(
                "<b>%{label}</b><br><br>"
                "Patrimônio: R$ %{value:,.2f}<br>"
                "Variação (%): %{customdata[0]:.2f}%<br>"
                "Variação (R$): <b>R$ %{customdata[2]:.2f}</b>"
                "<extra></extra>"
            )
        )
        
        fig_tree.update_layout(
            margin=dict(t=30, l=10, r=10, b=10),
            coloraxis_colorbar=dict(title="Oscilação do Dia") # Nome amigável no topo do termômetro
        )
        
        st.plotly_chart(fig_tree, use_container_width=True)
        # 8. Gráfico de Pizza (Distribuição)
        st.divider()
        st.subheader("🍕 Distribuição da Carteira")

        fig = px.pie(
            carteira, 
            values='valor_patrimonio_atual', 
            names='ativo',                   
            hole=0.4,                        
            color_discrete_sequence=px.colors.sequential.Teal,
            title="Peso de cada ativo no património atual"
        )
        # Atualiza a formatação do hover (caixa que aparece ao passar o rato)
        fig.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="%{label}<br>R$ %{value:,.2f}<br>%{percent}")

        st.plotly_chart(fig, use_container_width=True)

        # ====================================================================
        # ====================================================================
        # ====================================================================
        # 7. COMPARATIVO DE DESEMPENHO (FIX DE CONTRASTE E LEITURA)
        # ====================================================================
        st.divider()
        st.subheader("📈 Desempenho Acumulado: Carteira vs. Benchmarks")

        with st.spinner("Sincronizando dados e benchmarks..."):
            # Lógica de segurança para a data inicial
            try:
                # Tenta usar a data do seu dataframe (ajuste 'df' se o nome for outro)
                data_inicial = pd.to_datetime(df['data_pregao']).min().strftime('%Y-%m-%d')
            except:
                data_inicial = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime('%Y-%m-%d')
            
            tickers_list = carteira['ativo'].tolist()
            dados_h = yf.download(tickers_list + ['^BVSP'], start=data_inicial, progress=False)['Close']
            dados_h = dados_h.ffill()

            # Busca CDI
            try:
                url_cdi = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={pd.to_datetime(data_inicial).strftime('%d/%m/%Y')}&dataFinal={pd.Timestamp.now().strftime('%d/%m/%Y')}"
                df_cdi_raw = pd.read_json(url_cdi)
                df_cdi_raw['data'] = pd.to_datetime(df_cdi_raw['data'], dayfirst=True)
                df_cdi_raw.set_index('data', inplace=True)
                retorno_cdi_acum = ((1 + df_cdi_raw['valor'] / 100).cumprod() - 1) * 100
            except:
                retorno_cdi_acum = pd.Series(0, index=dados_h.index)

            # Cálculos de Retorno
            ret_ativos = (dados_h / dados_h.iloc[0]) - 1
            pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_atual
            
            df_comp = pd.DataFrame({
                'Minha Carteira': (ret_ativos[tickers_list] * pesos).sum(axis=1) * 100,
                'Ibovespa': ret_ativos['^BVSP'] * 100,
                'CDI': retorno_cdi_acum
            }).ffill().fillna(0)

            # --- CRIAÇÃO DO GRÁFICO COM FOCO EM CONTRASTE ---
            fig_comp = px.line(
                df_comp,
                color_discrete_map={
                    'Minha Carteira': '#00CC96', # Verde Vibrante
                    'Ibovespa': '#EF553B',       # Vermelho Intenso
                    'CDI': '#FFA500'            # Laranja Seguro
                }
            )

            # 1. REMOVE NOMES FEIOS E ARREDONDA
            fig_comp.update_traces(
                line=dict(width=3),
                hovertemplate="<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
            )

            # 2. CONFIGURAÇÃO DE CONTRASTE DO BALÃO (HOVER)
            fig_comp.update_layout(
                hovermode="x unified",
                xaxis_title="",
                yaxis_title="Retorno Acumulado (%)",
                yaxis_ticksuffix="%",
                legend=dict(title="", orientation="h", y=1.05, x=1, xanchor="right"),
                
                # A SOLUÇÃO DO CONTRASTE:
                hoverlabel=dict(
                    bgcolor="rgba(33, 33, 33, 1)", # Fundo Preto Sólido (Estilo Terminal)
                    font_size=14,
                    font_color="white",            # Texto sempre Branco
                    font_family="Arial",
                    bordercolor="#555"             # Borda discreta
                ),
                
                # Deixa o gráfico limpo e sem bordas desnecessárias
                margin=dict(l=10, r=10, t=40, b=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )

            st.plotly_chart(fig_comp, use_container_width=True)

            # ====================================================================
        # 10. REBALANCEAMENTO INTELIGENTE DA CARTEIRA
        # ====================================================================
        st.divider()
        st.subheader("⚖️ Rebalanceamento Automático")
        st.write("Defina o percentual ideal que quer para cada ativo. Adicione novos ativos na tabela se desejar. O sistema dirá o que comprar ou vender.")

        # Campo para inserir quanto dinheiro novo quer investir
        col_aporte, col_vazia = st.columns([1, 2])
        novo_aporte = col_aporte.number_input("Valor do Novo Aporte (R$):", min_value=0.0, value=1000.0, step=100.0)

        # 1. Preparar a tabela interativa (Data Editor)
        ativos_atuais = carteira['ativo'].tolist()
        n_ativos = len(ativos_atuais)

        # Sugestão inicial: dividir o alvo igualmente entre as ações que já tem
        peso_inicial = 100.0 / n_ativos if n_ativos > 0 else 0

        df_alvos = pd.DataFrame({
            'Ativo': ativos_atuais,
            'Alvo (%)': [peso_inicial] * n_ativos
        })

        st.write("✏️ **Edite a tabela abaixo:** Mude as porcentagens ou adicione novas ações na última linha vazia. (A soma deve ser exatamente 100%)")
        
        # Cria a tabela interativa onde o utilizador pode adicionar linhas (num_rows="dynamic")
        alvos_editados = st.data_editor(
            df_alvos,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Ativo": st.column_config.TextColumn("Ticker (Ex: WEGE3.SA)", required=True),
                "Alvo (%)": st.column_config.NumberColumn("Alvo (%)", min_value=0.0, max_value=100.0, step=1.0)
            }
        )

        # Verificar se a matemática das percentagens bate certo
        soma_alvos = alvos_editados['Alvo (%)'].sum()
        
        # O botão só funciona se a soma der 100%
        if abs(soma_alvos - 100.0) > 0.01:
            st.warning(f"⚠️ A soma dos seus alvos está em **{soma_alvos:.2f}%**. Ajuste os valores para dar exatamente 100% para poder calcular.")
        else:
            if st.button("🚀 Calcular Ordens de Compra/Venda"):
                with st.spinner("A analisar o mercado e a calcular ordens..."):
                    
                    # Limpar possíveis espaços em branco digitados pelo utilizador
                    ativos_alvo = alvos_editados['Ativo'].str.upper().str.strip().tolist()
                    
                    # Buscar cotação em tempo real, inclusive das ações novas adicionadas
                    precos_rebalanceamento = {}
                    for ativo in ativos_alvo:
                        precos_rebalanceamento[ativo] = obter_preco_atual(ativo)
                    
                    # Patrimônio alvo total (O que tem hoje + O aporte novo)
                    patrimonio_futuro_total = carteira['valor_patrimonio_atual'].sum() + novo_aporte
                    
                    ordens = []
                    
                    # Processar a matemática para cada linha da tabela interativa
                    for index, row in alvos_editados.iterrows():
                        ativo = str(row['Ativo']).upper().strip()
                        alvo_pct = row['Alvo (%)'] / 100.0
                        
                        # Quanto de dinheiro ESTE ativo deveria ter no mundo ideal?
                        valor_alvo_ideal = patrimonio_futuro_total * alvo_pct
                        
                        # Quanto dinheiro temos NESTE ativo atualmente?
                        if ativo in carteira['ativo'].values:
                            valor_atual_ativo = carteira.loc[carteira['ativo'] == ativo, 'valor_patrimonio_atual'].values[0]
                        else:
                            valor_atual_ativo = 0.0 # É um ativo novo!
                            
                        # Diferença entre o que quero e o que tenho
                        diferenca_financeira = valor_alvo_ideal - valor_atual_ativo
                        
                        preco_ativo = precos_rebalanceamento[ativo]
                        
                        # Quantas ações a diferença de dinheiro compra (ou vende)?
                        if preco_ativo > 0:
                            qtd_acoes = diferenca_financeira / preco_ativo
                        else:
                            qtd_acoes = 0
                            
                        # Arredondar para número inteiro, pois normalmente não negociamos frações de ações
                        qtd_acoes_arredondada = int(qtd_acoes)
                        valor_da_ordem = abs(qtd_acoes_arredondada * preco_ativo)
                        
                        # Decidir se a ordem é de Compra, Venda ou Manter
                        if qtd_acoes_arredondada > 0:
                            acao_texto = "COMPRAR"
                            cor = "🟢"
                        elif qtd_acoes_arredondada < 0:
                            acao_texto = "VENDER"
                            cor = "🔴"
                        else:
                            acao_texto = "MANTER"
                            cor = "⚪"
                            
                        ordens.append({
                            'Status': cor,
                            'Operação': acao_texto,
                            'Ativo': ativo,
                            'Qtd de Ações': abs(qtd_acoes_arredondada),
                            'Preço Cotação (R$)': f"R$ {preco_ativo:,.2f}",
                            'Valor Total (R$)': f"R$ {valor_da_ordem:,.2f}"
                        })
                        
                    df_ordens = pd.DataFrame(ordens)
                    
                    st.success("✅ Plano gerado com sucesso! Eis o seu 'Recibo' para executar na Corretora:")
                    
                    # Destacar as compras e vendas usando cores no Streamlit
                    def colorir_operacao(val):
                        if val == 'COMPRAR':
                            return 'color: #2e7d32; font-weight: bold'
                        elif val == 'VENDER':
                            return 'color: #c62828; font-weight: bold'
                        return 'color: gray'
                        
                    st.dataframe(df_ordens.style.map(colorir_operacao, subset=['Operação']), use_container_width=True, hide_index=True)

                    # ====================================================================
        # 11. MÁQUINA DE DIVIDENDOS (RENDA PASSIVA)
        # ====================================================================
        st.divider()
        st.subheader("💸 Máquina de Dividendos (Projeção 12 Meses)")
        st.write("Se as empresas mantiverem o mesmo pagamento dos últimos 12 meses, esta é a sua projeção de renda passiva com a carteira atual.")

        with st.spinner("A calcular os dividendos históricos. Isto pode levar alguns segundos..."):
            dividendos_totais = []

            for ativo in carteira['ativo']:
                try:
                    acao = yf.Ticker(ativo)
                    # Pegar todo o histórico de dividendos da ação
                    divs = acao.dividends
                    
                    if not divs.empty:
                        # Descobrir a data de 1 ano atrás (com fuso horário ajustado)
                        data_corte = pd.Timestamp.now(tz=divs.index.tz) - pd.DateOffset(years=1)
                        
                        # Filtrar apenas os dividendos pagos neste último ano
                        divs_12m = divs[divs.index >= data_corte]
                        total_pago_por_acao = divs_12m.sum()
                    else:
                        total_pago_por_acao = 0.0
                except:
                    total_pago_por_acao = 0.0

                dividendos_totais.append(total_pago_por_acao)

            # Fazer a matemática: Multiplicar o que a empresa paga pela quantidade de ações que você tem
            carteira_divs = carteira.copy()
            carteira_divs['div_por_acao_12m'] = dividendos_totais
            carteira_divs['renda_passiva_anual'] = carteira_divs['quantidade_total'] * carteira_divs['div_por_acao_12m']

            # Calcular os totais
            renda_anual_total = carteira_divs['renda_passiva_anual'].sum()
            renda_mensal_media = renda_anual_total / 12

            # Mostrar os números em destaque
            col1, col2 = st.columns(2)
            col1.metric("Projeção de Dividendos (1 Ano)", f"R$ {renda_anual_total:,.2f}")
            col2.metric("Média Mensal Estimada", f"R$ {renda_mensal_media:,.2f}")

            # Criar um gráfico de barras para ver quem são as melhores "pagadoras"
            # Filtramos apenas as ações que pagaram mais de 0
            df_grafico_divs = carteira_divs[carteira_divs['renda_passiva_anual'] > 0].sort_values(by='renda_passiva_anual', ascending=False)
            
            if not df_grafico_divs.empty:
                fig_divs = px.bar(
                    df_grafico_divs,
                    x='ativo',
                    y='renda_passiva_anual',
                    title="Quais ações estão a pagar as suas contas?",
                    labels={'renda_passiva_anual': 'Renda Anual (R$)', 'ativo': 'Ação'},
                    text_auto='.2s', # Mostra o valor em cima da barra
                    color='renda_passiva_anual',
                    color_continuous_scale=px.colors.sequential.Greens # Usa uma escala de cores verde-dinheiro
                )
                
                fig_divs.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
                st.plotly_chart(fig_divs, use_container_width=True)
            else:
                st.info("Nenhuma das ações da sua carteira pagou dividendos nos últimos 12 meses.")

                # ====================================================================
        # 12. RADAR DE NOTÍCIAS DA CARTEIRA
        # ====================================================================
        st.divider()
        st.subheader("📰 Radar de Notícias")
        st.write("Fique por dentro do que está a acontecer com as empresas em que investe.")
        
        # Cria uma caixa de seleção com as ações que você tem na carteira
        ativo_noticia = st.selectbox("Selecione um ativo para ler as notícias recentes:", carteira['ativo'].tolist())
        
        with st.spinner(f"A buscar as últimas notícias para {ativo_noticia}..."):
            try:
                noticias = yf.Ticker(ativo_noticia).news
                
                if noticias:
                    # Mostrar apenas as 5 notícias mais recentes
                    for noticia in noticias[:5]:  
                        # 1. Tenta pegar no formato antigo (direto no dicionário)
                        titulo = noticia.get('title')
                        link = noticia.get('link')
                        editora = noticia.get('publisher')
                        
                        # 2. Se não encontrou o título, tenta o formato novo do Yahoo (dentro de 'content')
                        if not titulo and 'content' in noticia:
                            conteudo = noticia['content']
                            titulo = conteudo.get('title', 'Notícia sem título')
                            
                            # O link novo fica escondido dentro de 'clickThroughUrl'
                            link_obj = conteudo.get('clickThroughUrl', {})
                            link = link_obj.get('url', '#')
                            
                            # A editora nova fica escondida dentro de 'provider'
                            provider_obj = conteudo.get('provider', {})
                            editora = provider_obj.get('displayName', 'Fonte Desconhecida')
                            
                        # 3. Fallback de segurança (se vier completamente vazio)
                        titulo = titulo or "Notícia sem título"
                        link = link or "#"
                        editora = editora or "Fonte Desconhecida"
                        
                        st.markdown(f"**[{titulo}]({link})**")
                        st.caption(f"Fonte: {editora}")
                        st.write("---")
                else:
                    st.info(f"Nenhuma notícia recente encontrada para {ativo_noticia} nos principais portais.")
            except Exception as e:
                st.error("Não foi possível carregar as notícias agora. O servidor do Yahoo pode estar sobrecarregado ou mudou a estrutura.")

                # ====================================================================
       # ====================================================================
        # 15. TESTE DE STRESS: CENÁRIOS DE CRISE HISTÓRICOS
        # ====================================================================
        st.divider()
        st.subheader("🛡️ Teste de Stress: Como a sua carteira reagiria a grandes crises?")
        st.write("Simulamos o desempenho dos seus ativos atuais durante os períodos mais negros da nossa bolsa.")

        cenarios = {
            "Joesley Day (Maio 2017)": "2017-05-15",
            "Greve dos Caminhoneiros (Maio 2018)": "2018-05-18",
            "Início da Pandemia (Março 2020)": "2020-03-02"
        }

        escolha_crise = st.selectbox("Escolha o cenário de crise para simular:", list(cenarios.keys()))
        data_inicio = cenarios[escolha_crise]
        data_fim = (pd.to_datetime(data_inicio) + pd.DateOffset(days=30)).strftime('%Y-%m-%d')

        if st.button("🚨 Iniciar Simulação de Crise"):
            with st.spinner(f"Viajando no tempo para {escolha_crise}..."):
                tickers_stress = carteira['ativo'].tolist()
                
                # Baixar dados do período da crise + Ibovespa
                dados_crise = yf.download(tickers_stress + ['^BVSP'], start=data_inicio, end=data_fim, progress=False)['Close']
                dados_crise.ffill(inplace=True)

                if len(dados_crise) < 5:
                    st.error("Dados insuficientes para este período. Alguns ativos podem ser muito recentes (IPOs).")
                else:
                    # 1. Identificar quais ativos já existiam na época
                    ativos_validos = [t for t in tickers_stress if t in dados_crise.columns and not dados_crise[t].isnull().all()]
                    
                    # 2. Recalcular pesos apenas para os ativos que existiam
                    valor_total_existente = carteira[carteira['ativo'].isin(ativos_validos)]['valor_patrimonio_atual'].sum()
                    pesos_stress = carteira[carteira['ativo'].isin(ativos_validos)].set_index('ativo')['valor_patrimonio_atual'] / valor_total_existente

                    # 3. Normalizar dados (Base 0%)
                    retornos_crise = (dados_crise / dados_crise.iloc[0]) - 1
                    
                    # 4. Calcular desempenho da carteira e do Ibovespa
                    desempenho_carteira = (retornos_crise[ativos_validos] * pesos_stress).sum(axis=1) * 100
                    desempenho_ibov = retornos_crise['^BVSP'] * 100

                    df_stress = pd.DataFrame({
                        'A Minha Carteira': desempenho_carteira,
                        'Ibovespa': desempenho_ibov
                    })

                    # 5. Gráfico de Stress com Contraste Garantido
                    fig_stress = px.line(
                        df_stress, 
                        title=f"Impacto na Carteira: {escolha_crise}",
                        labels={'value': 'Variação (%)', 'Date': 'Data', 'variable': 'Série'},
                        color_discrete_map={
                            'A Minha Carteira': '#00CC96', # Verde Esmeralda
                            'Ibovespa': '#EF553B'          # Vermelho Coral
                        }
                    )

                    fig_stress.update_traces(
                        line=dict(width=3), # Linhas um pouco mais grossas para facilitar a visão
                        hovertemplate="<b>%{fullData.name}</b><br>Data: %{x|%d/%m/%Y}<br>Variação: <b>%{y:.2f}%</b><extra></extra>"
                    )

                    fig_stress.update_layout(
                        hovermode="x unified",
                        # Melhorando o contraste da legenda e eixos
                        legend=dict(font=dict(size=12, color="gray")),
                        xaxis=dict(showgrid=False, title_font=dict(color="gray")),
                        yaxis=dict(ticksuffix="%", title_font=dict(color="gray")),
                        
                        # A MÁGICA DO CONTRASTE: 
                        # Forçamos um fundo semi-transparente escuro com letra branca no balão
                        hoverlabel=dict(
                            bgcolor="rgba(33, 33, 33, 0.9)", # Cinza escuro profissional
                            font_size=14,
                            font_color="white",             # Letra obrigatoriamente branca
                            font_family="sans-serif"
                        ),
                        plot_bgcolor="rgba(0,0,0,0)", # Fundo do gráfico transparente
                        paper_bgcolor="rgba(0,0,0,0)"
                    )

                    st.plotly_chart(fig_stress, use_container_width=True)

                    # --- RESUMO FINANCEIRO DO SUSTO ---
                    queda_max = df_stress['A Minha Carteira'].min()
                    perda_financeira = (queda_max / 100) * patrimonio_atual
                    
                    st.error(f"⚠️ **Ponto Crítico:** No pior momento desta crise, a sua carteira teria caído **{queda_max:.2f}%**.")
                    st.warning(f"💸 Em valores de hoje, isso representaria uma queda de aproximadamente **R$ {abs(perda_financeira):,.2f}** no seu património em poucos dias.")
                    
                    if len(ativos_validos) < len(tickers_stress):
                        ativos_novos = set(tickers_stress) - set(ativos_validos)
                        st.info(f"Nota: Ativos como {', '.join(ativos_novos)} não existiam nesta época e foram excluídos da simulação.")
       
       # 9. Monte Carlo (Versão Final com Aporte e Hover Corrigido)
        st.divider()
        st.subheader("🎲 Simulação de Monte Carlo")
        st.write("Projeção probabilística considerando a volatilidade da sua carteira e aportes mensais.")

        # Reintroduzindo os campos de entrada
        col_tempo, col_contri = st.columns(2)
        anos = col_tempo.slider("Anos de projeção:", 1, 30, 10)
        aporte_mensal = col_contri.number_input("Aporte Mensal Desejado (R$):", value=1000.0)
        
        if st.button("🎲 Rodar Simulação"):
            with st.spinner("A processar 1.000 cenários de futuro..."):
                # 1. Obter retornos e volatilidade
                hist = yf.download(carteira['ativo'].tolist(), period="1y", progress=False)['Close']
                rets = hist.pct_change().dropna()
                pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / carteira['valor_patrimonio_atual'].sum()
                
                mu = (rets.mean() * pesos).sum()
                sigma = (rets * pesos).sum(axis=1).std()
                
                # 2. Configurar a simulação
                dias_proj = anos * 252
                aporte_diario = aporte_mensal / 21 # Média de dias úteis no mês
                n_simulacoes = 100
                
                sims = np.zeros((dias_proj, n_simulacoes))
                
                for s in range(n_simulacoes):
                    p = [carteira['valor_patrimonio_atual'].sum()]
                    for d in range(1, dias_proj):
                        # Preço anterior * (1 + variação aleatória) + aporte do dia
                        choque = np.random.normal(mu, sigma)
                        novo_valor = p[-1] * (1 + choque) + aporte_diario
                        p.append(novo_valor)
                    sims[:, s] = p
                
                # 3. Criar DataFrame com as estatísticas (Percentis)
                df_stats = pd.DataFrame(sims).quantile([0.1, 0.5, 0.9], axis=1).T
                df_stats.columns = ['Pessimista', 'Mediana', 'Otimista']
                df_stats.index.name = 'Dias úteis'
                
                # 4. Criar o Gráfico Plotly com Hover Personalizado
                fig_mc = px.line(
                    df_stats,
                    labels={'value': 'Património', 'Dias úteis': 'Dias úteis', 'variable': 'Cenário'},
                    title=f"Projeção de Património: {anos} Anos com Aportes de R$ {aporte_mensal:,.2f}/mês"
                )
                
                # Configuração exata do que aparece ao passar o rato (Hover)
                fig_mc.update_traces(
                    hovertemplate="<b>%{fullData.name}</b><br>Dias úteis: %{x}<br>Valor: R$ %{y:,.2f}<extra></extra>"
                )
                
                fig_mc.update_layout(
                    hovermode="x unified", 
                    yaxis_tickprefix="R$ ",
                    yaxis_tickformat=",.2f",
                    legend_title_text="Cenários"
                )
                
                st.plotly_chart(fig_mc, use_container_width=True)
                
                # Exibir resultado final esperado
                valor_final = df_stats['Mediana'].iloc[-1]
                st.success(f"📈 No cenário mais provável (Mediana), teria **R$ {valor_final:,.2f}** daqui a {anos} anos.")

                # ====================================================================
        # ====================================================================
        # ====================================================================
        # 13. VALUATION PRO: PREÇO JUSTO (BAZIN REAL & GRAHAM)
        # ====================================================================
        st.divider()
        st.subheader("💎 Valuation Real: Graham & Bazin (Últimos 12 Meses)")
        st.write("Calculando dividendos reais pagos nos últimos 12 meses para evitar erros de API.")

        yield_desejado = st.slider("Yield Mínimo Desejado (Bazin) %:", 4.0, 12.0, 6.0) / 100

        if st.button("🔍 Calcular Valuation com Dividendos Reais"):
            with st.spinner("Analisando histórico de proventos e lucros..."):
                valuation_list = []
                for ativo in carteira['ativo']:
                    try:
                        ticker = yf.Ticker(ativo)
                        
                        # 1. Puxar preço atual de forma segura
                        preco_atual = ticker.fast_info['lastPrice']
                        
                        # 2. CALCULAR DIVIDENDOS REAIS (BAZIN)
                        # Em vez de ler 'yield', vamos somar os dividendos pagos nos últimos 365 dias
                        historico_divs = ticker.dividends
                        if not historico_divs.empty:
                            data_corte = pd.Timestamp.now(tz=historico_divs.index.tz) - pd.DateOffset(years=1)
                            div_anual_real = historico_divs[historico_divs.index >= data_corte].sum()
                        else:
                            div_anual_real = 0

                        # 3. DADOS PARA GRAHAM
                        info = ticker.info
                        lpa = info.get('trailingEps') 
                        vpa = info.get('bookValue')

                        # --- CÁLCULOS MATEMÁTICOS ---
                        # Bazin: Preço Teto = Dividendo Real / Yield Desejado
                        preco_bazin = div_anual_real / yield_desejado if div_anual_real > 0 else np.nan
                        
                        # Graham: V = sqrt(22.5 * LPA * VPA)
                        preco_graham = np.nan
                        margem_graham = np.nan
                        if lpa and vpa and lpa > 0 and vpa > 0:
                            preco_graham = np.sqrt(22.5 * lpa * vpa)
                            margem_graham = ((preco_graham / preco_atual) - 1) * 100

                        valuation_list.append({
                            'Ativo': ativo,
                            'Preço Atual': preco_atual,
                            'Div. 12M (R$)': div_anual_real,
                            'P. Teto (Bazin)': preco_bazin,
                            'P. Justo (Graham)': preco_graham,
                            'Margem Graham (%)': margem_graham,
                            'Status Bazin': "✅ Comprar" if preco_atual < preco_bazin else "❌ Caro"
                        })
                    except Exception as e:
                        continue

                df_val = pd.DataFrame(valuation_list)
                
                # Exibição com formatação rigorosa
                st.dataframe(
                    df_val.style.format({
                        'Preço Atual': 'R$ {:,.2f}',
                        'Div. 12M (R$)': 'R$ {:,.2f}',
                        'P. Teto (Bazin)': lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "N/A",
                        'P. Justo (Graham)': lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "N/A",
                        'Margem Graham (%)': lambda x: f"{x:.2f}%" if pd.notnull(x) else "N/A"
                    }),
                    use_container_width=True, hide_index=True
                )

                # ====================================================================
        # 14. MATRIZ DE CORRELAÇÃO: DIVERSIFICAÇÃO REAL
        # ====================================================================
        st.divider()
        st.subheader("📊 Matriz de Correlação: Você está realmente diversificado?")
        st.write("Esta matriz mostra como os seus ativos se movem em relação uns aos outros. Cores muito fortes indicam que você tem ativos que se comportam de forma quase idêntica.")

        if st.button("🧬 Gerar Matriz de Risco"):
            with st.spinner("Analisando padrões de movimento dos últimos 12 meses..."):
                # 1. Baixar dados históricos de fechamento
                tickers_corr = carteira['ativo'].tolist()
                dados_corr = yf.download(tickers_corr, period="1y", progress=False)['Close']
                
                # 2. Calcular retornos diários
                retornos_diarios = dados_corr.pct_change().dropna()
                
                # 3. Calcular a Matriz de Correlação de Pearson
                matriz_corr = retornos_diarios.corr()

                # 4. Criar o Mapa de Calor com Plotly
                fig_corr = px.imshow(
                    matriz_corr,
                    text_auto=".2f", # Mostra o número dentro do quadrado
                    aspect="auto",
                    color_continuous_scale='RdBu_r', # Escala Red-Blue (Invertida)
                    zmin=-1, zmax=1, # Fixa a escala entre -1 e 1
                    title="Correlação entre Ativos (Pearson $r$)"
                )

                # Ajuste de layout para legibilidade
                fig_corr.update_layout(
                    width=800,
                    height=700,
                    xaxis_title="Ativos",
                    yaxis_title="Ativos"
                )

                st.plotly_chart(fig_corr, use_container_width=True)

                # --- INSIGHTS DE RISCO ---
                st.info("💡 **Como ler esta matriz:**")
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    st.markdown("""
                    🔴 **Zonas Vermelhas (> 0.7):** Alta dependência. 
                    Se você tem muitos quadrados vermelhos (além da diagonal principal), 
                    sua carteira pode cair toda de uma vez. Ex: Dois bancos ou duas empresas de commodities.
                    """)
                with col_i2:
                    st.markdown("""
                    🔵 **Zonas Azuis (< 0.3):** Ótima diversificação. 
                    Estes ativos reagem de forma diferente aos estímulos do mercado. 
                    É isso que protege o seu patrimônio em crises setoriais.
                    """)

                    # ====================================================================
        # 16. AGENDA DE DIVIDENDOS: DINHEIRO NO BOLSO (CASH FLOW)
        # ====================================================================
        st.divider()
        st.subheader("📅 Próximos Dividendos e JCP")
        st.write("Acompanhe os anúncios de pagamentos e datas de corte (Data Com) da sua carteira.")

        if st.button("🚀 Consultar Agenda de Proventos"):
            with st.spinner("Consultando editais de pagamento..."):
                agenda_list = []
                for ativo in carteira['ativo']:
                    try:
                        t = yf.Ticker(ativo)
                        # O 'calendar' do yfinance traz as próximas datas importantes
                        cal = t.calendar
                        
                        if 'Dividend Date' in cal:
                            data_pagamento = cal['Dividend Date']
                            # Se houver data, vamos registrar
                            if pd.notnull(data_pagamento):
                                agenda_list.append({
                                    'Ativo': ativo,
                                    'Previsão de Pagamento': data_pagamento.strftime('%d/%m/%Y'),
                                    'Tipo': 'Dividendo/JCP',
                                    'Status': 'Anunciado'
                                })
                    except:
                        continue

                if agenda_list:
                    df_agenda = pd.DataFrame(agenda_list)
                    st.success("✅ Novos pagamentos identificados!")
                    st.dataframe(df_agenda, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum novo pagamento anunciado nos editais recentes para os seus ativos.")

        st.caption("Nota: As datas são baseadas nas últimas divulgações oficiais capturadas pelo Yahoo Finance.")

        # ====================================================================
        # 17. MACRO: SENSIBILIDADE AO DÓLAR (USD/BRL)
        # ====================================================================
        st.divider()
        st.subheader("🌎 Análise Macro: Proteção Cambial (Dólar vs. Carteira)")
        st.write("Descubra se o seu patrimônio está protegido contra a alta do dólar ou se ele é dependente da economia local.")

        if st.button("💵 Analisar Exposição ao Dólar"):
            with st.spinner("Cruzando dados com o mercado de câmbio..."):
                # 1. Baixar dados do Dólar e da Carteira (1 ano)
                tickers_macro = carteira['ativo'].tolist()
                dados_macro = yf.download(tickers_macro + ['USDBRL=X'], period="1y", progress=False)['Close']
                dados_macro.ffill(inplace=True)

                # 2. Calcular retornos
                retornos_macro = dados_macro.pct_change().dropna()
                
                # Pesos para o retorno da carteira
                pesos_macro = carteira.set_index('ativo')['valor_patrimonio_atual'] / patrimonio_atual
                retornos_macro['Minha Carteira'] = (retornos_macro[tickers_list] * pesos_macro).sum(axis=1)

                # 3. Calcular Correlação de Pearson
                correl_dolar = retornos_macro['Minha Carteira'].corr(retornos_macro['USDBRL=X'])

                # 4. Exibição Visual (Gauge ou Métrica)
                col_m1, col_m2 = st.columns([1, 2])
                
                with col_m1:
                    st.metric("Correlação com USD", f"{correl_dolar:.2f}")
                
                with col_m2:
                    if correl_dolar > 0.3:
                        st.success("✅ **Carteira Dolarizada:** Seus ativos tendem a subir junto com o dólar. Ótima proteção cambial (Exportadoras/Commodities).")
                    elif correl_dolar < -0.3:
                        st.warning("⚠️ **Foco em Mercado Interno:** Sua carteira costuma cair quando o dólar sobe. Atenção a crises cambiais.")
                    else:
                        st.info("⚖️ **Neutro:** Sua carteira não tem relação direta com o câmbio. Movimentos do dólar afetam pouco o seu resultado final.")

                # Gráfico de Dispersão (Visualização Premium)
                fig_macro = px.scatter(
                    retornos_macro, 
                    x='USDBRL=X', 
                    y='Minha Carteira',
                    trendline="ols",
                    title="Dispersão: Retorno Carteira vs. Variação Dólar",
                    labels={'USDBRL=X': 'Variação Dólar (%)', 'Minha Carteira': 'Variação Carteira (%)'}
                )
                
                # Formatação fluida do hover
                fig_macro.update_traces(
                    marker=dict(size=10, color='#00CC96', opacity=0.6),
                    hovertemplate="Dólar: %{x:.2f}%<br>Carteira: %{y:.2f}%<extra></extra>"
                )
                
                st.plotly_chart(fig_macro, use_container_width=True)

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o ficheiro. Verifique se é o Excel correto da B3. Erro detalhado: {e}")

else:
    st.info("A aguardar o upload do ficheiro Excel para iniciar os cálculos.")