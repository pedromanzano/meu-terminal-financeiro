# Componentes reutilizáveis: estilos de gráficos e tabelas
import plotly.graph_objects as go
import pandas as pd


def padronizar_grafico(fig: go.Figure) -> go.Figure:
    """Aplica tema escuro e hover consistente aos gráficos Plotly."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor="rgba(20, 20, 20, 0.95)",
            font_color="white",
            font_size=14,
            bordercolor="#444",
        ),
        font=dict(color="#E0E0E0"),
        margin=dict(t=50, l=10, r=10, b=10),
    )
    return fig


def style_pvp_inteligente(row: pd.Series) -> list[str]:
    """Retorna lista de estilos por célula conforme Status (P/VP)."""
    status = row["Status"]
    n = len(row)
    if "🟢" in status:
        return ["color: #00CC96; font-weight: bold"] * n
    if "🟠" in status:
        return ["color: #FFA500; font-weight: bold"] * n
    return ["color: #EF553B; font-weight: bold"] * n
