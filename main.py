"""
Hermes Unified - Entry Point
Orquestrador LangGraph integrando MiMo, Hyper-Extract e Web Tools
"""

import sys
import os
import json
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from core.graph import run_agent

def main():
    print("""
╔══════════════════════════════════════════╗
║     HERMES UNIFIED - LANGGRAPH ORCH      ║
║   Integrando MiMo + Hyper-Extract + Web  ║
╚══════════════════════════════════════════╝
    """)
    
    if len(sys.argv) < 2:
        print("Uso: python main.py <objetivo> [--files arquivo1.pdf arquivo2.py ...]")
        print()
        print("Exemplos:")
        print("  python main.py \"Crie uma calculadora em Python\"")
        print("  python main.py \"Extraia conceitos deste PDF\" --files documento.pdf")
        print("  python main.py \"Crie API baseada na spec\" --files spec.pdf")
        sys.exit(1)
    
    # Parse argumentos
    objective = sys.argv[1]
    input_files = []
    
    if "--files" in sys.argv:
        idx = sys.argv.index("--files")
        input_files = sys.argv[idx+1:]
    
    # Executa
    result = run_agent(objective, input_files)
    
    # Salva resultado
    output_file = f"/tmp/hermes_unified_result_{result.get('task_id', 'unknown')}.json"
    with open(output_file, 'w') as f:
        # Converte para serializável
        serializable = {
            "task_id": result.get("task_id"),
            "objective": result.get("objective"),
            "success": result.get("success"),
            "completed": result.get("completed"),
            "iteration": result.get("iteration"),
            "error": result.get("error"),
            "artifacts": result.get("artifacts", []),
            "summary": result.get("context", {}).get("summary", ""),
        }
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Resultado salvo em: {output_file}")

if __name__ == "__main__":
    main()
