# Autenticação e banco: Supabase + streamlit-authenticator (credenciais via secrets)
import logging
import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client, Client

logger = logging.getLogger(__name__)


def get_supabase() -> Client:
    """Inicializa e retorna o client Supabase. Para em caso de falha."""
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY")
    if not url or not key:
        st.error("⚠️ Banco de dados não configurado. Adicione SUPABASE_URL e SUPABASE_KEY no secrets.toml.")
        st.stop()
    try:
        return create_client(url, key)
    except Exception as e:
        logger.exception("Erro ao inicializar Supabase")
        st.error(f"Erro ao inicializar o Supabase: {e}")
        st.stop()


def get_authenticator():
    """Constrói credenciais e authenticator a partir de st.secrets."""
    cookie_key = st.secrets.get("AUTH_COOKIE_KEY") or "chave_secreta_altere_em_producao"
    username = st.secrets.get("AUTH_USERNAME") or "admin"
    name = st.secrets.get("AUTH_NAME") or "Admin"
    password_hash = st.secrets.get("AUTH_PASSWORD_HASH") or ""
    if not password_hash:
        st.warning("AUTH_PASSWORD_HASH não definido em secrets. Use gerar_senha.py para gerar o hash.")
    credentials = {
        "usernames": {
            username: {
                "name": name,
                "password": password_hash,
            }
        }
    }
    return stauth.Authenticate(
        credentials,
        "investimentos_dashboard",
        cookie_key,
        cookie_expiry_days=30,
    )
