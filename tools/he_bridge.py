"""
Hyper-Extract Bridge - Integra extração de conhecimento com LangGraph
Converte documentos em grafos de conhecimento utilizáveis
"""

import subprocess
import os
import json
from typing import Dict, Optional, List, Tuple
from pathlib import Path

class HyperExtractBridge:
    """
    Bridge entre LangGraph e Hyper-Extract.
    Permite extrair conhecimento de documentos e buscar no grafo.
    """
    
    def __init__(self, output_base: str = "/opt/data/knowledge_graphs"):
        self.output_base = output_base
        os.makedirs(self.output_base, exist_ok=True)
        self.available_templates = self._discover_templates()
    
    def _discover_templates(self) -> List[str]:
        """Descobre templates disponíveis no Hyper-Extract."""
        try:
            result = subprocess.run(
                ["he", "template", "list"],
                capture_output=True,
                text=True,
                timeout=15
            )
            return [t.strip() for t in result.stdout.split('\n') if t.strip()]
        except:
            return ["general/concept_graph"]  # Fallback
    
    def extract_from_pdf(
        self, 
        pdf_path: str, 
        project_id: str,
        template: str = "general/concept_graph",
        language: str = "pt"
    ) -> Tuple[Dict, bool, str]:
        """
        Extrai conhecimento de um PDF usando Hyper-Extract.
        
        Returns:
            Tuple[grafo, sucesso, mensagem]
        """
        if not os.path.exists(pdf_path):
            return {}, False, f"PDF não encontrado: {pdf_path}"
        
        output_dir = f"{self.output_base}/{project_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            cmd = [
                "he", "parse", pdf_path,
                "-t", template,
                "-o", output_dir,
                "-l", language
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Carrega o grafo gerado
                graph = self._load_graph(output_dir)
                return graph, True, f"Extraído com sucesso para {output_dir}"
            else:
                return {}, False, f"Erro Hyper-Extract: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return {}, False, "Timeout após 2 minutos na extração"
        except Exception as e:
            return {}, False, f"Exceção: {str(e)}"
    
    def extract_from_text(
        self,
        text_content: str,
        project_id: str,
        template: str = "general/concept_graph",
        language: str = "pt"
    ) -> Tuple[Dict, bool, str]:
        """Extrai conhecimento de texto puro."""
        # Salva texto temporário
        temp_file = f"/tmp/he_temp_{project_id}.txt"
        with open(temp_file, 'w') as f:
            f.write(text_content)
        
        return self.extract_from_pdf(temp_file, project_id, template, language)
    
    def search_graph(
        self, 
        project_id: str, 
        query: str,
        max_results: int = 3
    ) -> Tuple[List[Dict], bool, str]:
        """
        Busca no grafo de conhecimento extraído.
        
        Returns:
            Tuple[resultados, sucesso, mensagem]
        """
        graph_dir = f"{self.output_base}/{project_id}"
        
        if not os.path.exists(graph_dir):
            return [], False, f"Grafo não encontrado para projeto {project_id}"
        
        try:
            cmd = [
                "he", "search", graph_dir,
                query,
                "--max-results", str(max_results)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Tenta parsear resultado como JSON
                try:
                    results = json.loads(result.stdout)
                    return results, True, f"{len(results)} resultados encontrados"
                except:
                    # Retorna texto puro
                    return [{"text": result.stdout}], True, "Resultado textual"
            else:
                return [], False, f"Erro na busca: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return [], False, "Timeout na busca"
        except Exception as e:
            return [], False, f"Exceção: {str(e)}"
    
    def talk_to_graph(
        self,
        project_id: str,
        question: str
    ) -> Tuple[str, bool, str]:
        """
        Faz perguntas ao grafo de conhecimento (modo chat).
        """
        graph_dir = f"{self.output_base}/{project_id}"
        
        if not os.path.exists(graph_dir):
            return "", False, f"Grafo não encontrado para projeto {project_id}"
        
        try:
            cmd = [
                "he", "talk", graph_dir,
                "-q", question
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return result.stdout, True, "Resposta obtida"
            else:
                return result.stderr, False, "Erro na consulta"
                
        except subprocess.TimeoutExpired:
            return "", False, "Timeout na consulta"
        except Exception as e:
            return "", False, f"Exceção: {str(e)}"
    
    def get_available_projects(self) -> List[str]:
        """Lista projetos com grafos extraídos."""
        projects = []
        for item in os.listdir(self.output_base):
            project_dir = os.path.join(self.output_base, item)
            if os.path.isdir(project_dir) and os.path.exists(os.path.join(project_dir, "data.json")):
                projects.append(item)
        return projects
    
    def _load_graph(self, graph_dir: str) -> Dict:
        """Carrega o grafo de conhecimento do disco."""
        data_file = os.path.join(graph_dir, "data.json")
        metadata_file = os.path.join(graph_dir, "metadata.json")
        
        graph = {}
        
        if os.path.exists(data_file):
            with open(data_file, 'r') as f:
                try:
                    graph["data"] = json.load(f)
                except:
                    graph["data"] = {}
        
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                try:
                    graph["metadata"] = json.load(f)
                except:
                    graph["metadata"] = {}
        
        return graph
    
    def graph_summary(self, project_id: str) -> Dict:
        """Resumo estatístico do grafo."""
        graph = self._load_graph(f"{self.output_base}/{project_id}")
        
        if not graph.get("data"):
            return {"error": "Grafo vazio ou não encontrado"}
        
        data = graph["data"]
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        
        # Conta tipos de nós
        node_types = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "node_types": node_types,
            "top_nodes": [n.get("name", n.get("label", "unknown")) for n in nodes[:5]]
        }


# Singleton
_he_bridge = None

def get_he_bridge() -> HyperExtractBridge:
    global _he_bridge
    if _he_bridge is None:
        _he_bridge = HyperExtractBridge()
    return _he_bridge
