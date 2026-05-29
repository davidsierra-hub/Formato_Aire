"""
Script de autorización OAuth para Gmail — correr UNA SOLA VEZ.

Genera `gmail_token.json` con un refresh token para que la app pueda crear
borradores en Gmail como operaciones@bia.app sin más interacción.

Requisitos previos:
  1. Tener `oauth_client.json` en este mismo directorio (descargado desde
     GCP Console → APIs & Services → Credentials → OAuth Client ID).
  2. Haber habilitado Gmail API en el proyecto GCP.

Uso:
    python authorize_gmail.py

Se abrirá una ventana del navegador. Inicia sesión con `operaciones@bia.app`
y otorga los permisos. Al cerrar el flujo, se crea `gmail_token.json` y la
app ya puede crear borradores.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
CLIENT_SECRET = "oauth_client.json"
TOKEN_FILE    = "gmail_token.json"


def main() -> None:
    if not os.path.exists(CLIENT_SECRET):
        print(f"❌ No se encontró {CLIENT_SECRET} en esta carpeta.")
        print("   Descárgalo desde GCP Console → Credentials → tu OAuth Client ID y guárdalo acá.")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        print(f"✅ Ya tienes un token válido en {TOKEN_FILE}. No hace falta re-autorizar.")
        return

    if creds and creds.expired and creds.refresh_token:
        print("🔄 Token expirado, intentando refrescar…")
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"⚠️  No se pudo refrescar ({e}). Re-autorizando desde cero…")
            creds = None

    if not creds:
        print("🌐 Abriendo navegador para autorización. Inicia sesión con operaciones@bia.app…")
        flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"✅ Autorización completa. Token guardado en {TOKEN_FILE}")
    print("   Ya puedes usar el botón 'Enviar vía email' en la app.")


if __name__ == "__main__":
    main()
