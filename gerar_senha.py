import streamlit_authenticator as stauth

# 1. Coloque a sua senha aqui
senha_plana = "jose" 

# 2. A nova forma de gerar o hash (mais simples)
hash_gerado = stauth.Hasher.hash(senha_plana)

print("-" * 30)
print(f"Copie este código: {hash_gerado}")
print("-" * 30)