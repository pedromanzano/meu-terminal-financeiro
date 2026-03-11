# Autenticação e banco: Supabase + streamlit-authenticator (credenciais via secrets)
import logging
import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Hash padrão para desenvolvimento quando AUTH_PASSWORD_HASH não está em secrets
# Gerado com gerar_senha.py; altere a senha em produção via secrets.
_DEFAULT_PASSWORD_HASH = "$2b$12$eaa2xg5WmNGWTfJL8Y09buVjlBAThqlMwsogcnyYfUFodd3VZt6jO"


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
    password_hash = st.secrets.get("AUTH_PASSWORD_HASH") or _DEFAULT_PASSWORD_HASH
    if not st.secrets.get("AUTH_PASSWORD_HASH"):
        st.sidebar.caption("Dica: defina AUTH_PASSWORD_HASH em secrets (use gerar_senha.py para gerar o hash).")
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
