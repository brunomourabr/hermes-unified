"""
Research Bridge - STORM-style knowledge curation agent
Pesquisa topicos, gera artigos completos com citacoes
Implementa: multi-perspectiva, conversa simulada, outline, artigo
"""
import os
import json
import subprocess
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from config import get_api_key

# Conexão com Knowledge Graph
try:
    from tools.memory_bridge import get_kg
    _kg_available = True
except ImportError:
    _kg_available = False


class ResearchBridge:
    """Agente de pesquisa profunda estilo STORM (Stanford)."""
    
    def __init__(self):
        self.output_dir = Path(__file__).parent.parent / "output" / "research"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.deepseek_key = get_api_key("DEEPSEEK_API_KEY")
        self.openrouter_key = get_api_key("OPENROUTER_API_KEY")
        self._storm_available = self._check_storm()
    
    def _check_storm(self) -> bool:
        """Verifica se knowledge-storm esta instalado."""
        try:
            import knowledge_storm
            return True
        except ImportError:
            return False
    
    def status(self) -> dict:
        """Retorna status de configuracao."""
        return {
            "storm_installed": self._storm_available,
            "deepseek_key": bool(self.deepseek_key),
            "openrouter_key": bool(self.openrouter_key),
            "online_possible": bool(self.deepseek_key or self.openrouter_key),
            "message": self._get_status_message()
        }
    
    def _get_status_message(self) -> str:
        if not self._storm_available:
            return "knowledge-storm nao instalado. pip install knowledge-storm"
        if not self.deepseek_key and not self.openrouter_key:
            return "Nenhuma chave de LLM configurada para geracao"
        return "Pronto para pesquisar"
    
    def _get_llm(self, model: str = None, max_tokens: int = 2000, temp: float = 0.7):
        """Cria instancia de LLM via litellm."""
        from litellm import completion
        
        def llm_func(messages, **kwargs):
            final_model = model or "deepseek/deepseek-chat"
            api_key = self.deepseek_key if "deepseek" in final_model else self.openrouter_key
            
            if not api_key:
                return {"content": "[ERRO: chave nao configurada]"}
            
            try:
                resp = completion(
                    model=final_model,
                    messages=messages,
                    api_key=api_key,
                    max_tokens=kwargs.get("max_tokens", max_tokens),
                    temperature=kwargs.get("temperature", temp),
                )
                return {"content": resp.choices[0].message.content}
            except Exception as e:
                return {"content": f"[ERRO: {str(e)[:100]}]"}
        
        return llm_func
    
    def research_topic(self, topic: str, depth: str = "medium") -> Tuple[str, bool, str]:
        """
        Pipeline completo de pesquisa estilo STORM:
        1. Coleta perspectivas sobre o topico
        2. Simula perguntas de pesquisa
        3. Gera outline
        4. Escreve artigo completo
        5. Poli o artigo
        
        Args:
            topic: Topico a ser pesquisado
            depth: "quick" (3 secoes), "medium" (5 secoes), "deep" (8+ secoes)
        
        Returns:
            Tuple[caminho_arquivo, sucesso, mensagem]
        """
        start = datetime.now()
        
        if not self._storm_available:
            return self._research_offline(topic, depth)
        
        try:
            from knowledge_storm import STORMWikiRunnerArguments, STORMWikiRunner, STORMWikiLMConfigs
            from knowledge_storm.lm import LitellmModel
            from knowledge_storm.rm import DuckDuckGoSearchRM
            
            lm_configs = STORMWikiLMConfigs()
            
            api_key = self.deepseek_key or self.openrouter_key
            base_model = "deepseek/deepseek-chat" if self.deepseek_key else "openai/gpt-4o-mini"
            
            kwargs = {"api_key": api_key, "temperature": 0.7, "top_p": 0.9}
            
            # Modelo barato pra conversa, modelo bom pra geracao
            cheap = LitellmModel(model=base_model, max_tokens=500, **kwargs)
            powerful = LitellmModel(model=base_model, max_tokens=3000, **kwargs)
            
            lm_configs.set_conv_simulator_lm(cheap)
            lm_configs.set_question_asker_lm(cheap)
            lm_configs.set_outline_gen_lm(powerful)
            lm_configs.set_article_gen_lm(powerful)
            lm_configs.set_article_polish_lm(powerful)
            
            # Configura busca - usa DuckDuckGo
            max_conv_turns = {"quick": 3, "medium": 5, "deep": 8}
            
            engine_args = STORMWikiRunnerArguments(
                output_dir=str(self.output_dir / topic.replace(" ", "_")),
                max_conv_turn=max_conv_turns.get(depth, 5),
                max_search_queries_per_turn=2,
                search_top_k=3,
            )
            
            try:
                rm = DuckDuckGoSearchRM(k=engine_args.search_top_k)
            except Exception as e:
                print(f"   [RESEARCH] DuckDuckGo error, falling back to offline: {str(e)[:80]}")
                return self._research_offline(topic, depth)
            runner = STORMWikiRunner(engine_args, lm_configs, rm)
            
            print(f"   [RESEARCH] Iniciando pesquisa: {topic[:60]}...")
            print(f"   [RESEARCH] Profundidade: {depth}, modelo: {base_model}")
            
            runner.run(
                topic=topic,
                do_research=True,
                do_generate_outline=True,
                do_generate_article=True,
                do_polish_article=True,
            )
            
            runner.post_run()
            summary = runner.summary()
            
            elapsed = (datetime.now() - start).total_seconds()
            
            # Salva resultado
            output_file = self.output_dir / f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            result = {
                "topic": topic,
                "depth": depth,
                "elapsed_seconds": elapsed,
                "summary": str(summary),
                "output_dir": str(engine_args.output_dir),
                "article_path": str(Path(engine_args.output_dir) / "storm_gen_article.txt") if os.path.exists(str(Path(engine_args.output_dir) / "storm_gen_article.txt")) else "",
            }
            
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Le o artigo gerado se existir
            article_path = Path(engine_args.output_dir) / "storm_gen_article.txt"
            if article_path.exists():
                with open(article_path) as f:
                    article = f.read()
                
                # Salva copia como markdown
                md_path = self.output_dir / f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                with open(md_path, "w") as f:
                    f.write(f"# {topic}\n\n{article}")

                # Persiste no KnowledgeGraph
                self._save_research_to_kg(topic, article, depth, str(md_path))

                return str(md_path), True, f"Artigo gerado em {elapsed:.0f}s ({len(article)} chars)"

            # Persiste no KnowledgeGraph com o summary
            self._save_research_to_kg(topic, str(summary), depth, str(output_file))

            return str(output_file), True, f"Pesquisa concluida em {elapsed:.0f}s"
            
        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds()
            print(f"   [RESEARCH] STORM falhou ({elapsed:.0f}s): {str(e)[:100]}")
            print(f"   [RESEARCH] Usando modo offline simplificado...")
            return self._research_offline(topic, depth)

    def research_with_mode(self, topic: str, mode: str = "storm", depth: str = "medium") -> Tuple[str, bool, str]:
        """
        Pesquisa com modo explicito (fast/storm/hybrid).
        
        Mapeia modo -> comportamento + confidence no KG:
          - fast:   modo offline direto, confidence 0.7
          - storm:  pipeline STORM completo, confidence 0.85
          - hybrid: STORM com fallback offline, confidence 0.8
        
        Args:
            topic: Topico a pesquisar
            mode:  "fast", "storm" ou "hybrid"
            depth: "quick", "medium" ou "deep"
        
        Returns:
            Tuple[caminho_arquivo, sucesso, mensagem]
        """
        mode_map = {
            "fast":   {"depth": depth, "confidence": 0.7},
            "storm":  {"depth": depth, "confidence": 0.85},
            "hybrid": {"depth": depth, "confidence": 0.8},
        }
        cfg = mode_map.get(mode, mode_map["storm"])
        
        if mode == "fast":
            # fast: offline direto, sem STORM
            result = self._research_offline(topic, cfg["depth"])
        else:
            # storm ou hybrid: tenta STORM, fallback offline
            result = self.research_topic(topic, cfg["depth"])
            if not result[1] and mode == "hybrid":
                result = self._research_offline(topic, cfg["depth"])
        
        return result

    def _research_offline(self, topic: str, depth: str = "medium") -> Tuple[str, bool, str]:
        """Modo offline: gera artigo via LLM direto, sem o pipeline STORM."""
        try:
            llm = self._get_llm(max_tokens=4000, temp=0.7)
            
            num_sections = {"quick": 3, "medium": 5, "deep": 8}.get(depth, 5)
            
            prompt = (
                f"Pesquise e escreva um artigo completo sobre: {topic}\n\n"
                f"O artigo deve ter:\n"
                f"- Introducao\n"
                f"- {num_sections} secoes principais com subtitulos\n"
                f"- Conclusao\n"
                f"- Referencias (cite fontes reais quando possivel)\n\n"
                f"Formato: Markdown\n"
                f"Tom: Profissional e informativo, estilo Wikipedia\n"
                f"Idioma: Portugues brasileiro\n"
                f"Extensao: {num_sections * 300}+ palavras"
            )
            
            result = llm([{"role": "user", "content": prompt}])
            article = result.get("content", "")
            
            if article.startswith("[ERRO"):
                # Fallback: gera um artigo simples
                article = self._generate_minimal_article(topic, num_sections)
            
            # Salva
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{topic.replace(' ', '_')}_{timestamp}.md"
            filepath = self.output_dir / filename
            with open(filepath, "w") as f:
                f.write(f"# {topic}\n\n{article}")

            # Persiste no KnowledgeGraph
            self._save_research_to_kg(topic, article, depth, str(filepath))

            return str(filepath), True, f"Artigo gerado offline ({len(article)} chars)"
            
        except Exception as e:
            return "", False, f"Erro na geracao offline: {str(e)[:100]}"
    
    def _generate_minimal_article(self, topic: str, sections: int = 5) -> str:
        """Gera artigo minimo quando LLM nao responde."""
        lines = [f"## Introducao\n\n{topic} e um tema de grande relevancia no contexto atual. Este artigo apresenta uma visao geral sobre o assunto, abordando seus principais aspectos e implicacoes.\n"]
        
        for i in range(1, sections + 1):
            lines.append(f"\n## Secao {i}\n\nConteudo sobre {topic} - secao {i}. [Analise detalhada em desenvolvimento]\n")
        
        lines.append(f"\n## Conclusao\n\n{topic} continua sendo um campo em evolucao, com novas descobertas e aplicacoes surgindo regularmente.\n")
        lines.append(f"\n## Referencias\n\n- Fonte: Pesquisa Hermes Unified\n- Data: {datetime.now().strftime('%d/%m/%Y')}\n")
        
        return "\n".join(lines)

    def _save_research_to_kg(self, topic: str, article: str, depth: str, filepath: str = "") -> None:
        """Salva o resultado da pesquisa no KnowledgeGraphStore como Claim + Sources."""
        if not _kg_available:
            print("   [KG] KnowledgeGraphStore nao disponivel, pulando persistencia")
            return
        try:
            kg = get_kg()
            if not kg:
                return

            bridge_name = "research_bridge"

            # Mapeia depth/profundidade para confidence
            confidence_map = {"quick": 0.7, "medium": 0.8, "deep": 0.85}
            confidence = confidence_map.get(depth, 0.75)

            # Cria resumo (primeiros 500 chars + indicacao)
            summary = article[:500].strip() if article else ""
            if len(article) > 500:
                summary += "..."

            # 1. Salva o Claim
            claim_dict = {
                "text": summary or f"Artigo gerado sobre: {topic}",
                "confidence": confidence,
                "topic": topic,
                "source_url": filepath or "",
                "source_title": f"Research Article: {topic}",
            }
            claim_id, validated = kg.save_claim(claim_dict, bridge=bridge_name)
            print(f"   [KG] Claim salvo: {claim_id} (validação: {'OK' if validated else 'rejeitado'})")

            # 2. Salva as sources (se houver fontes conhecidas no contexto)
            # No STORM, as sources vêm do resumo da pesquisa; extraímos menções
            # de URLs ou domain patterns do artigo
            source_ids = []
            import re
            urls = re.findall(r'https?://[^\s\)\]\}]+', article or "")
            seen = set()
            for url in urls:
                domain_base = url.split("//")[-1].split("/")[0] if "//" in url else ""
                if domain_base and domain_base not in seen:
                    seen.add(domain_base)
                    source_dict = {
                        "url": url,
                        "title": f"Fonte: {domain_base}",
                        "domain": domain_base,
                        "relevance_score": confidence,
                    }
                    try:
                        sid = kg.save_source(source_dict, bridge=bridge_name)
                        source_ids.append(sid)
                    except Exception as e:
                        print(f"   ⚠ [KG] Erro ao salvar source {url[:50]}: {e}")

            # 3. Cria relação entre Claim e cada Source
            for sid in source_ids:
                kg.add_relationship(
                    source_type="claim",
                    source_id=claim_id,
                    rel_type="cites_source",
                    target_type="source",
                    target_id=sid,
                    bridge=bridge_name,
                )
            print(f"   [KG] {len(source_ids)} fonte(s) vinculada(s) ao claim {claim_id}")

        except Exception as e:
            print(f"   ⚠ [KG] Erro ao salvar no KnowledgeGraph: {e}")
    
    def generate_outline(self, topic: str, sections: int = 5) -> Tuple[dict, bool, str]:
        """Gera apenas o outline de um artigo."""
        llm = self._get_llm(max_tokens=1000, temp=0.5)
        prompt = (
            f"Crie um outline detalhado para um artigo sobre: {topic}\n"
            f"{sections} secoes principais, cada uma com 3-4 subtopicos.\n"
            f"Formato: JSON"
        )
        result = llm([{"role": "user", "content": prompt}])
        content = result.get("content", "")
        return {"outline": content}, True, "Outline gerado"
    
    def list_articles(self) -> List[dict]:
        """Lista artigos gerados."""
        articles = []
        for f in sorted(self.output_dir.glob("*.md"), key=os.path.getmtime, reverse=True):
            articles.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
        return articles


# Singleton
_research_bridge = None

def get_research_bridge() -> ResearchBridge:
    global _research_bridge
    if _research_bridge is None:
        _research_bridge = ResearchBridge()
    return _research_bridge
