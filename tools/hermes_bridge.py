"""
Hermes Bridge - Conecta o Hermes Unified às tools nativas do Hermes
Usa as mesmas APIs que o Hermes usa internamente (OpenRouter, Telegram)
Funciona standalone sem dependência do runtime do Hermes
"""
import os
import json
import base64
import requests
from typing import Optional, Tuple
from pathlib import Path
from config import get_api_key


class HermesBridge:
    """Bridge para tools do Hermes (visao, mensagem, notificacao)."""
    
    def __init__(self):
        self.openrouter_key = get_api_key("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
        self.deepseek_key = get_api_key("DEEPSEEK_API_KEY")
    
    def vision_analyze(self, image_url: str, question: str = "Descreva esta imagem em detalhes.") -> Tuple[str, bool, str]:
        """
        Analisa uma imagem usando modelo de visao via OpenRouter.
        Aceita URL http/https ou caminho de arquivo local.
        """
        try:
            # Se for arquivo local, converte pra base64 data URL
            if not image_url.startswith(("http://", "https://")):
                image_path = os.path.expanduser(image_url)
                if not os.path.exists(image_path):
                    return "", False, f"Arquivo nao encontrado: {image_path}"
                
                with open(image_path, "rb") as f:
                    img_data = f.read()
                    img_b64 = base64.b64encode(img_data).decode()
                
                # Detecta MIME type
                ext = os.path.splitext(image_path)[1].lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", 
                           ".png": "image/png", ".webp": "image/webp",
                           ".gif": "image/gif"}
                mime = mime_map.get(ext, "image/png")
                image_url = f"data:{mime};base64,{img_b64}"
            
            # Tenta OpenRouter primeiro (modelo de visao)
            if self.openrouter_key:
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "google/gemini-3-flash-preview",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }],
                    "max_tokens": 2000
                }
                
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return content, True, "Analise concluida via OpenRouter"
            
            # Fallback: DeepSeek não tem visao, entao retorna erro
            return "", False, "OpenRouter API key nao configurada para visao"
            
        except requests.exceptions.Timeout:
            return "", False, "Timeout na analise da imagem (60s)"
        except Exception as e:
            return "", False, f"Erro na analise: {str(e)[:100]}"
    
    def send_notification(self, message: str, target: str = "telegram") -> Tuple[bool, str]:
        """
        Envia notificacao via Telegram.
        Usa a API Telegram diretamente se tiver token configurado,
        ou retorna instrucoes para envio.
        """
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "")
        
        if bot_token and chat_id:
            try:
                resp = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                    timeout=15
                )
                if resp.status_code == 200:
                    return True, "Notificacao enviada via Telegram"
                return False, f"Erro Telegram: {resp.status_code}"
            except Exception as e:
                return False, f"Erro ao enviar: {str(e)[:80]}"
        
        # Sem bot token: salva como log
        log_dir = Path(__file__).parent.parent / "output" / "notifications"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"notification_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(log_file, "w") as f:
            f.write(f"Target: {target}\n{message}")
        return True, f"Notificacao salva em {log_file}"


# Singleton
_hermes_bridge = None

def get_hermes_bridge() -> HermesBridge:
    global _hermes_bridge
    if _hermes_bridge is None:
        _hermes_bridge = HermesBridge()
    return _hermes_bridge
