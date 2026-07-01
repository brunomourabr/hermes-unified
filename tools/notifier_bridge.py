"""
Notifier Bridge - Sistema de notificacoes multicanal
Conecta watchers do Observer ao Hermes Bridge (Telegram)
"""
import os
import json
from typing import Dict, Optional, Tuple, List
from pathlib import Path
from datetime import datetime

from tools.hermes_bridge import get_hermes_bridge


class NotifierBridge:
    """Sistema de notificacoes para eventos do Hermes Unified."""
    
    def __init__(self):
        self.output_dir = Path(__file__).parent.parent / "output" / "notifications"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def notify_watcher_result(self, watcher_name: str, check_type: str, 
                               target: str, result: str, changed: bool = False) -> Tuple[bool, str]:
        """Notifica resultado de um watcher."""
        icon = "🔔" if changed else "✅"
        message = (
            f"{icon} <b>Watcher: {watcher_name}</b>\n"
            f"Tipo: {check_type}\n"
            f"Alvo: {target[:80]}\n"
            f"{'🚨 Mudanca detectada!' if changed else 'Sem alteracoes'}\n"
            f"{result[:200]}"
        )
        
        bridge = get_hermes_bridge()
        return bridge.send_notification(message)
    
    def notify_task_complete(self, task_id: str, objective: str, 
                              success: bool, artifacts: list) -> Tuple[bool, str]:
        """Notifica conclusao de uma tarefa."""
        status = "✅" if success else "❌"
        message = (
            f"{status} <b>Tarefa Concluida</b>\n"
            f"ID: {task_id}\n"
            f"Objetivo: {objective[:100]}\n"
            f"Status: {'Sucesso' if success else 'Falha'}\n"
            f"Artefatos: {len(artifacts)}"
        )
        
        bridge = get_hermes_bridge()
        return bridge.send_notification(message)
    
    def notify_error(self, agent: str, task_id: str, error: str) -> Tuple[bool, str]:
        """Notifica erro de execucao."""
        message = (
            f"⚠️ <b>Erro no agente {agent}</b>\n"
            f"Task: {task_id}\n"
            f"Erro: {error[:200]}"
        )
        
        bridge = get_hermes_bridge()
        return bridge.send_notification(message)
    
    def notify_alert(self, title: str, message_body: str, 
                     level: str = "info") -> Tuple[bool, str]:
        """Notifica alerta generico."""
        icons = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
        icon = icons.get(level, "ℹ️")
        message = f"{icon} <b>{title}</b>\n{message_body}"
        
        bridge = get_hermes_bridge()
        return bridge.send_notification(message)

    def get_notification_history(self, limit: int = 10) -> List[Dict]:
        """Recupera historico de notificacoes."""
        history = []
        files = sorted(self.output_dir.glob("*.txt"), key=os.path.getmtime, reverse=True)[:limit]
        for f in files:
            with open(f) as fh:
                history.append({
                    "file": f.name,
                    "content": fh.read()[:200],
                    "time": datetime.fromtimestamp(os.path.getmtime(f)).isoformat()
                })
        return history


# Singleton
_notifier_bridge = None

def get_notifier_bridge() -> NotifierBridge:
    global _notifier_bridge
    if _notifier_bridge is None:
        _notifier_bridge = NotifierBridge()
    return _notifier_bridge
