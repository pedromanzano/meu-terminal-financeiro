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

        # 6. Apresentação no ecrã (Tabela Atualizada)
        st.divider()
        st.subheader("📊 Posição Atual e Indicadores Técnicos")
        
        carteira_formatada = carteira.copy()
        # Formatar as novas colunas como moeda
        colunas_moeda = ['custo_total_investido', 'preco_medio', 'preco_atual', 'valor_patrimonio_atual', 'lucro_prejuizo', 'MM200', 'Min_52S', 'Max_52S']

        for col in colunas_moeda:
            carteira_formatada[col] = carteira_formatada[col].apply(lambda x: f"R$ {x:,.2f}")
            
        carteira_formatada['rentabilidade_%'] = carteira_formatada['rentabilidade_%'].apply(lambda x: f"{x:,.2f}%")

        # Organizar as colunas para o que importa ficar visível primeiro
        colunas_exibicao = ['ativo', 'quantidade_total', 'preco_medio', 'preco_atual', 'Tendência', 'MM200', 'Min_52S', 'Max_52S', 'lucro_prejuizo', 'rentabilidade_%']
        
        st.dataframe(carteira_formatada[colunas_exibicao], use_container_width=True, hide_index=True)

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

        carteira['var_dia_pct'] = carteira['var_dia_pct'].fillna(0.0)
        
        # Tamanho dinâmico mas conservador para evitar quebras no motor do Plotly
        carteira['font_size'] = (14 + carteira['var_dia_pct'].abs() * 2).clip(upper=22)

        fig_tree = px.treemap(
            carteira, 
            path=['ativo'], 
            values='valor_patrimonio_atual',
            color='var_dia_pct', 
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0,
            custom_data=['var_dia_pct', 'font_size'] 
        )

        fig_tree.update_traces(
            textposition="middle center",
            # Sem DIVs, apenas SPANs simples que o Plotly entende bem
            texttemplate=(
                "<span style='font-size:%{customdata[1]}px'><b>%{label}</b></span><br>"
                "<span style='font-size:%{customdata[1]}px'>%{customdata[0]:.2f}%</span>"
            ),
            hovertemplate="<b>%{label}</b><br>Variação: %{customdata[0]:.2f}%<extra></extra>"
        )
        
        fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10))
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

        # 9. Máquina do Tempo: Comparação com Ibovespa (Últimos 12 meses)
        st.divider()
        st.subheader("📈 Máquina do Tempo: Carteira vs Ibovespa (1 Ano)")
        st.write("Esta simulação compara o rendimento da sua composição de carteira atual contra o índice Bovespa nos últimos 12 meses.")

        # Cria uma animação de carregamento enquanto o Python vai à internet baixar o histórico
        with st.spinner("A baixar histórico de 12 meses. Aguarde..."):
            
            # Pegar a lista de ações que você tem hoje e adicionar o Ibovespa (^BVSP)
            tickers_carteira = carteira['ativo'].tolist()
            tickers_hist = tickers_carteira + ['^BVSP']

            # Baixar o histórico de fechamento de 1 ano de todos eles de uma vez
            # suppress_warnings evita que mensagens sujem o terminal
            dados_hist = yf.download(tickers_hist, period="1y", progress=False)['Close']

            # Preencher eventuais buracos nos dados (como feriados que uma ação negociou e outra não)
            dados_hist.ffill(inplace=True)

            # A Magia da Normalização: Faz todo mundo começar do 0% no primeiro dia do gráfico
            retornos_acumulados = (dados_hist / dados_hist.iloc[0]) - 1

            # Calcular o peso de cada ação no seu patrimônio atual
            pesos = carteira.set_index('ativo')['valor_patrimonio_atual'] / carteira['valor_patrimonio_atual'].sum()

            # Multiplicar o retorno histórico de cada ação pelo peso que ela tem na sua carteira
            # Isso cria uma "Linha da sua Carteira" perfeitamente balanceada
            retorno_carteira = (retornos_acumulados[tickers_carteira] * pesos).sum(axis=1)

            # Juntar a sua linha com a linha do Ibovespa numa tabela nova para o gráfico
            df_grafico = pd.DataFrame({
                'A Minha Carteira': retorno_carteira * 100, # x100 para virar porcentagem
                'Ibovespa': retornos_acumulados['^BVSP'] * 100
            })

            # Criar o gráfico de linhas com o Plotly
            fig_linha = px.line(
                df_grafico, 
                labels={'value': 'Rentabilidade Acumulada (%)', 'Date': 'Data', 'variable': 'Comparativo'},
                color_discrete_map={'A Minha Carteira': '#1f77b4', 'Ibovespa': '#d62728'} # Azul para você, Vermelho para IBOV
            )
            
            # Formatação elegante para o gráfico
            fig_linha.update_layout(
                hovermode="x unified", # Mostra uma linha vertical acompanhando o mouse com os dois valores
                yaxis_ticksuffix="%"   # Adiciona o símbolo de porcentagem no eixo Y
            )

            # Desenhar o gráfico na tela
            st.plotly_chart(fig_linha, use_container_width=True)

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
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o ficheiro. Verifique se é o Excel correto da B3. Erro detalhado: {e}")

else:
    st.info("A aguardar o upload do ficheiro Excel para iniciar os cálculos.")