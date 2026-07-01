"""
MiMo Bridge - Adaptador para integrar MiMo Code com LangGraph
Converte o MiMo interativo em ferramentas callable
"""

import subprocess
import os
import json
from typing import Dict, Optional, Tuple
from pathlib import Path

class MiMoBridge:
    """
    Bridge entre LangGraph e MiMo Code.
    Permite chamadas programáticas ao MiMo sem interação TUI.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek/deepseek-chat"):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.model = model
        self.work_dir = "/tmp/mimo_work"
        os.makedirs(self.work_dir, exist_ok=True)
    
    def generate_code(
        self, 
        specification: str, 
        file_path: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> Tuple[str, bool, str]:
        """
        Gera código usando MiMo.
        
        Returns:
            Tuple[conteúdo, sucesso, mensagem]
        """
        # Prepara o comando mimo
        if file_path:
            work_file = file_path
            work_dir = os.path.dirname(os.path.abspath(file_path))
        else:
            work_file = os.path.join(self.work_dir, "generated.py")
            work_dir = self.work_dir
        
        os.makedirs(work_dir, exist_ok=True)
        
        # Contexto enriquecido
        enriched_spec = self._enrich_prompt(specification, context)
        
        # Executa MiMo
        cmd = [
            "mimo", "run",
            "-m", self.model,
            enriched_spec
        ]
        
        env = os.environ.copy()
        env["DEEPSEEK_API_KEY"] = str(self.api_key or "")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                cwd=work_dir
            )
            
            # Analisa resultado
            if result.returncode == 0:
                # Tenta ler o arquivo gerado
                if os.path.exists(work_file):
                    with open(work_file, 'r') as f:
                        content = f.read()
                    return content, True, "Código gerado com sucesso"
                else:
                    return result.stdout or "Código gerado", True, "Código gerado (stdout)"
            else:
                return result.stderr or "", False, f"Erro MiMo: {result.returncode}"
                
        except subprocess.TimeoutExpired:
            return "", False, "Timeout após 5 minutos"
        except Exception as e:
            return "", False, f"Exceção: {str(e)}"
    
    def refactor_code(
        self, 
        file_path: str, 
        instructions: str,
        backup: bool = True
    ) -> Tuple[str, bool, str]:
        """
        Refatora código existente.
        """
        if not os.path.exists(file_path):
            return "", False, f"Arquivo não encontrado: {file_path}"
        
        # Backup se solicitado
        if backup:
            backup_path = f"{file_path}.backup"
            os.system(f"cp {file_path} {backup_path}")
        
        # Lê conteúdo atual
        with open(file_path, 'r') as f:
            current_code = f.read()
        
        # Prompt de refatoração
        spec = f"""Refatore o código no arquivo {file_path}.
        
Instruções: {instructions}

Código atual:
```
{current_code}
```

Mantenha a mesma funcionalidade mas aplique as melhorias solicitadas."""

        return self.generate_code(spec, file_path)
    
    def validate_code(self, file_path: str, language: str = "python") -> Tuple[bool, str]:
        """
        Valida sintaxe do código gerado.
        """
        if not os.path.exists(file_path):
            return False, "Arquivo não existe"
        
        if language == "python":
            # Validação Python
            result = subprocess.run(
                ["python3", "-m", "py_compile", file_path],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, "Sintaxe válida"
            else:
                return False, f"Erro de sintaxe: {result.stderr}"
        
        # Adicionar validações para outras linguagens
        return True, "Validação básica OK"
    
    def test_code(
        self, 
        file_path: str, 
        test_command: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Executa testes no código.
        """
        if test_command:
            result = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, result.stdout + result.stderr
        
        # Teste básico: tenta importar se for Python
        if file_path.endswith('.py'):
            result = subprocess.run(
                ["python3", "-c", f"import {file_path.replace('.py', '').replace('/', '.')}"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0, result.stderr if result.returncode != 0 else "Import OK"
        
        return True, "Nenhum teste configurado"
    
    def _enrich_prompt(self, specification: str, context: Optional[Dict]) -> str:
        """Enriquece o prompt com contexto."""
        if not context:
            return specification
        
        enriched = specification
        
        if "stack" in context:
            enriched += f"\n\nStack tecnológica: {context['stack']}"
        
        if "style_guide" in context:
            enriched += f"\n\nGuia de estilo: {context['style_guide']}"
        
        if "existing_files" in context:
            enriched += f"\n\nArquivos existentes no projeto: {', '.join(context['existing_files'])}"
        
        return enriched

# Singleton para reutilização
_mimo_bridge = None

def get_mimo_bridge() -> MiMoBridge:
    global _mimo_bridge
    if _mimo_bridge is None:
        _mimo_bridge = MiMoBridge()
    return _mimo_bridge
