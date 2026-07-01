"""
Config do Hermes Unified
Carrega chaves de API de arquivo próprio (não depende de env vars do Hermes)
"""
import os
import json
from pathlib import Path

# Arquivo de configuração
CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "secrets.json"

def load_secrets() -> dict:
    """Carrega secrets do arquivo de configuração."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def get_api_key(name: str) -> str:
    """Busca chave: primeiro no secrets.json, depois no environment."""
    secrets = load_secrets()
    if name in secrets:
        return secrets[name]
    return os.environ.get(name, "")

def save_api_key(name: str, value: str):
    """Salva uma chave no secrets.json."""
    secrets = load_secrets()
    secrets[name] = value
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(secrets, f, indent=2)
    # Protege o arquivo
    os.chmod(CONFIG_FILE, 0o600)
