# Motor de dados: BRAPI, YFinance, CDI, Cripto, FIIs, Scanner
import logging
import urllib.request
import json
from datetime import datetime

import pandas as pd
import requests
import yfinance as yf
import streamlit as st

from config import TICKERS_FALLBACK, MINUTOS_PREGAO, GRAHAM_MULTIPLICADOR, SCANNER_TICKERS

logger = logging.getLogger(__name__)


def _remover_tz(series: pd.Series) -> pd.Series:
    """Remove timezone de um índice de datas para comparações seguras."""
    if getattr(series.index, "tz", None) is not None:
        series.index = series.index.tz_localize(None)
    return series


@st.cache_data(ttl=86400, show_spinner=False)
def buscar_tickers_brapi(token_brapi: str, pesquisa: str | None = None) -> list[str]:
    """Busca a lista oficial de ações na API da B3."""
    url = f"https://brapi.dev/api/quote/list?token={token_brapi}"
    if pesquisa:
        url += f"&search={pesquisa}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [acao["stock"] for acao in data.get("stocks", [])]
    except (requests.RequestException, KeyError, TypeError) as e:
        logger.warning("BRAPI list falhou: %s. Usando fallback.", e)
        return TICKERS_FALLBACK


@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_atual(token_brapi: str, ticker: str) -> float:
    """Cotação em tempo real B3 (BRAPI com fallback YFinance)."""
    ticker_limpo = ticker.replace(".SA", "")
    url = f"https://brapi.dev/api/quote/{ticker_limpo}?token={token_brapi}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        dados = resp.json()
        return float(dados["results"][0]["regularMarketPrice"])
    except (requests.RequestException, KeyError, TypeError, IndexError):
        try:
            df_hist = yf.Ticker(ticker_limpo + ".SA").history(period="1d")
            if not df_hist.empty:
                return float(df_hist["Close"].iloc[-1])
        except Exception as e:
            logger.debug("Preço YF fallback falhou para %s: %s", ticker, e)
    return 0.0


@st.cache_data(ttl=3600, show_spinner=False)
def obter_dividendos(token_brapi: str, ticker: str) -> pd.Series:
    """Dividendos (YFinance com fallback BRAPI); remove timezone."""
    ticker_limpo = ticker.replace(".SA", "")
    try:
        acao = yf.Ticker(ticker_limpo + ".SA")
        divs = acao.dividends
        if not divs.empty:
            return _remover_tz(divs.copy())
    except Exception as e:
        logger.debug("Dividendos YF falharam para %s: %s", ticker, e)

    try:
        url = f"https://brapi.dev/api/quote/{ticker_limpo}?token={token_brapi}&dividends=true"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        dados = resp.json()
        divs_list = dados["results"][0].get("dividendsData", {}).get("cashDividends", [])
        if divs_list:
            df = pd.DataFrame(divs_list)
            col_valor = "rate" if "rate" in df.columns else "assetIssuedDividend"
            df["date"] = pd.to_datetime(df["paymentDate"])
            if hasattr(df["date"].dt, "tz") and df["date"].dt.tz is not None:
                df["date"] = df["date"].dt.tz_localize(None)
            df.set_index("date", inplace=True)
            return df[col_valor]
    except (requests.RequestException, KeyError, TypeError) as e:
        logger.debug("Dividendos BRAPI falharam para %s: %s", ticker, e)
    return pd.Series()


@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados_historicos(tickers: str | list[str], start=None, end=None, period: str = "1y") -> pd.DataFrame:
    """Histórico de preços (YFinance)."""
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers_yf = [
        t + ".SA" if not t.endswith(".SA") and not t.startswith("^") and "=" not in t else t
        for t in tickers
    ]
    try:
        kwargs = {"progress": False}
        if start and end:
            kwargs["start"], kwargs["end"] = start, end
        else:
            kwargs["period"] = period
        df = yf.download(tickers_yf, **kwargs)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(name=tickers[0])
        else:
            mapa = {yf_t: orig for yf_t, orig in zip(tickers_yf, tickers)}
            df.rename(columns=mapa, inplace=True)
        return df.ffill()
    except Exception as e:
        logger.warning("Histórico YF falhou: %s", e)
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def obter_preco_cripto(ticker: str) -> float:
    """Cotação cripto (Mercado Bitcoin)."""
    moeda = str(ticker).upper().strip().split("-")[0]
    try:
        req = urllib.request.Request(
            f"https://www.mercadobitcoin.net/api/{moeda}/ticker/",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            return float(json.loads(response.read().decode())["ticker"]["last"])
    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.debug("Preço cripto falhou para %s: %s", ticker, e)
    return 0.0


@st.cache_data(ttl=86400, show_spinner=False)
def carregar_cdi_historico(data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Série CDI (BCB)."""
    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={data_inicio}&dataFinal={data_fim}"
        df_cdi = pd.read_json(url)
        df_cdi["data"] = pd.to_datetime(df_cdi["data"], dayfirst=True)
        df_cdi.set_index("data", inplace=True)
        return df_cdi
    except Exception as e:
        logger.warning("CDI histórico falhou: %s", e)
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_pvp_fiis(lista_fiis_config: dict) -> pd.DataFrame:
    """P/VP e DY de FIIs (YFinance)."""
    dados = []
    for fii, segmento in lista_fiis_config.items():
        try:
            ticker_nome = f"{fii.strip()}.SA"
            info = yf.Ticker(ticker_nome).info
            preco_atual = info.get("previousClose") or info.get("regularMarketPrice") or 0.0
            vpa = info.get("bookValue") or 0.0
            pvp = info.get("priceToBook")
            if (pvp is None or pvp == 0) and vpa > 0:
                pvp = preco_atual / vpa
            dy_bruto = info.get("dividendYield") or info.get("trailingAnnualDividendYield", 0.0)
            dy_pct = dy_bruto if (dy_bruto and dy_bruto > 1) else (dy_bruto * 100 if dy_bruto else 0.0)

            if pvp and pvp > 0:
                if segmento == "Papel":
                    status_texto = (
                        "🟢 Paridade"
                        if 0.98 <= pvp <= 1.02
                        else ("🟠 Alerta: Risco" if pvp < 0.98 else "🔴 Ágio")
                    )
                else:
                    status_texto = "🟢 Desconto" if pvp < 1.0 else "🔴 Ágio"
                dados.append({
                    "FII": fii,
                    "Tipo": segmento,
                    "Preço": preco_atual,
                    "VPA": vpa,
                    "P/VP": pvp,
                    "DY Anual (%)": dy_pct,
                    "DY Mensal Est. (%)": dy_pct / 12,
                    "Status": status_texto,
                })
        except Exception as e:
            logger.debug("FII %s falhou: %s", fii, e)
            continue
    return pd.DataFrame(dados)


@st.cache_data(ttl=600, show_spinner=False)
def scanner_volume_atipico() -> pd.DataFrame:
    """Fluxo institucional: volume atípico vs média 20 dias. Uma chamada em lote para histórico."""
    agora = datetime.now()
    inicio = agora.replace(hour=10, minute=0, second=0)
    proporcao_esperada = min(max((agora - inicio).total_seconds() / 60, 1) / MINUTOS_PREGAO, 1.0)
    anomalias = []

    try:
        data_5d = yf.download(SCANNER_TICKERS, period="5d", interval="5m", progress=False, auto_adjust=True)
        data_25d = yf.download(SCANNER_TICKERS, period="25d", progress=False, auto_adjust=True)
    except Exception as e:
        logger.warning("Scanner download falhou: %s", e)
        return pd.DataFrame()

    if data_5d.empty:
        return pd.DataFrame()

    # yf.download com lista retorna MultiIndex (level0=OHLCV, level1=ticker)
    def get_vol_df(df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.columns, pd.MultiIndex):
            return pd.DataFrame()
        if "Volume" in df.columns.get_level_values(0):
            return df["Volume"].copy()
        return pd.DataFrame()

    def get_close_df(df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.columns, pd.MultiIndex):
            return pd.DataFrame()
        if "Close" in df.columns.get_level_values(0):
            return df["Close"].copy()
        return pd.DataFrame()

    vol_5d = get_vol_df(data_5d)
    close_5d = get_close_df(data_5d)
    vol_25d_df = get_vol_df(data_25d) if not data_25d.empty else pd.DataFrame()

    for t in SCANNER_TICKERS:
        try:
            if t not in vol_5d.columns or t not in close_5d.columns:
                continue
            hoje_v = vol_5d[t].dropna()
            hoje_p = close_5d[t].dropna()
            if hoje_v.empty or hoje_p.empty:
                continue
            vol_hoje = hoje_v.sum()
            preco_atual = float(hoje_p.iloc[-1])
            preco_abertura = float(hoje_p.iloc[0])
            if t not in vol_25d_df.columns or len(vol_25d_df[t].dropna()) < 20:
                continue
            media_vol_20d = vol_25d_df[t].dropna().iloc[-21:-1].mean()
            vol_esperado = media_vol_20d * proporcao_esperada
            rvol = vol_hoje / vol_esperado if vol_esperado > 0 else 0
            var_dia = ((preco_atual / preco_abertura) - 1) * 100
            if rvol > 0.8:
                fluxo = "🏦 Institucional" if rvol > 1.2 else "⚖️ Fluxo Normal"
                fluxo += " (Compra)" if var_dia > 0.2 else (" (Venda)" if var_dia < -0.2 else " (Lateral)")
                ticker_limpo = t.replace(".SA", "").upper()
                anomalias.append({
                    "Logo": f"https://static.itaucpa.com.br/itau-corretora/logos-acoes/{ticker_limpo}.png",
                    "Ativo": ticker_limpo,
                    "Ritmo (RVOL)": f"{rvol:.2f}x",
                    "Variação": f"{var_dia:+.2f}%",
                    "Análise de Fluxo": fluxo,
                    "score": rvol,
                })
        except Exception as e:
            logger.debug("Scanner ticker %s: %s", t, e)
            continue

    df = pd.DataFrame(anomalias)
    if df.empty:
        return pd.DataFrame()
    return df.sort_values(by="score", ascending=False).head(8).drop(columns=["score"])
