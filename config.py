# Constantes e configuração visual do InvestiTerminal

# Fórmula Graham: preço justo = sqrt(22.5 * LPA * VPA)
GRAHAM_MULTIPLICADOR = 22.5

# Pregão B3: 10h às 17h = 420 minutos
MINUTOS_PREGAO = 420

# Fallback de tickers quando a API falha
TICKERS_FALLBACK = ["PETR4", "VALE3", "ITUB4", "BBDC4", "WEGE3"]

# Tickers do scanner de volume atípico
SCANNER_TICKERS = [
    "VALE3.SA", "PETR4.SA", "ITUB4.SA", "BBDC4.SA", "ABEV3.SA", "MGLU3.SA",
    "B3SA3.SA", "BBAS3.SA", "RENT3.SA", "WEGE3.SA", "HAPV3.SA", "GGBR4.SA",
    "PRIO3.SA", "ELET3.SA", "SUZB3.SA", "CSAN3.SA", "LREN3.SA", "RADL3.SA",
    "RAIL3.SA", "JBSS3.SA", "VBBR3.SA", "CPLE6.SA", "EQTL3.SA",
]

PAGE_CSS = """
<style>
    :root {
        --success: #00CC96;
        --danger: #EF553B;
        --warning: #FFA500;
        --muted: #888;
    }
    div[data-testid="metric-container"] {
        background-color: rgba(40, 40, 40, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 18px;
        border-radius: 14px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
    }
    div[data-testid="stTabs"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.06);
    }
    div[data-testid="stTabs"] > div:first-child {
        border-radius: 12px 12px 0 0;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        border-radius: 12px 12px 0 0;
        padding: 4px 8px 0;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        border-radius: 8px;
    }
    div[data-testid="stTabs"] > div[data-baseweb="tab-panel"] {
        border-radius: 0 0 12px 12px;
        padding: 1rem;
    }
    [data-testid="stSidebar"] {
        border-radius: 0 12px 12px 0;
        box-shadow: 4px 0 20px rgba(0, 0, 0, 0.15);
    }
    [data-testid="stSidebar"] > div:first-child {
        border-radius: 0 12px 12px 0;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.06);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }
    div[data-testid="stExpander"] {
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.06);
        overflow: hidden;
    }
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        padding: 1rem;
        border-radius: 12px;
    }
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
    .stDeployButton { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
</style>
"""
