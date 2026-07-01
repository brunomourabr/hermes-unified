"""
Ontology Engine — Carrega, valida e consulta a ontologia central.
Serve como camada semântica compartilhada entre todas as bridges.
"""
import os
import yaml
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


class OntologyEngine:
    """Motor de ontologia: carrega schema YAML e fornece validação semântica."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config", "ontology.yaml"
            )
        self.config_path = config_path
        self.data = self._load(config_path)
        self.entities = self.data.get("entities", {})
        self.relationships = self.data.get("relationships", {})
        self.constraints = self.data.get("constraints", {})
        self.bridge_mapping = self.data.get("bridge_mapping", {})
        self.metadata = self.data.get("metadata", {})

    def _load(self, path: str) -> dict:
        """Carrega o arquivo YAML de ontologia."""
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Ontology file not found: {path}\n"
                f"Run 'cp config/ontology.yaml.example config/ontology.yaml' or create it."
            )
        with open(path) as f:
            return yaml.safe_load(f)

    # =====================================================================
    # ENTIDADES
    # =====================================================================

    def get_entity(self, name: str) -> Optional[dict]:
        """Retorna definição de uma entidade."""
        return self.entities.get(name)

    def list_entities(self) -> List[str]:
        """Lista todas as entidades definidas."""
        return list(self.entities.keys())

    def validate_entity_attributes(self, entity_name: str, attrs: dict) -> Tuple[bool, List[str]]:
        """
        Valida atributos de uma entidade contra a ontologia.
        Retorna (valido, [lista_de_erros]).
        """
        errors = []
        entity_def = self.get_entity(entity_name)
        if not entity_def:
            errors.append(f"Entidade desconhecida: {entity_name}")
            return False, errors

        attr_defs = entity_def.get("attributes", {})

        # Verifica campos obrigatórios
        for attr_name, attr_def in attr_defs.items():
            if attr_def.get("required") and attr_name not in attrs:
                errors.append(f"{entity_name}.{attr_name}: campo obrigatório ausente")

        # Verifica valores contra enum
        for attr_name, value in attrs.items():
            attr_def = attr_defs.get(attr_name)
            if not attr_def:
                continue  # Campo extra permitido

            enum_vals = attr_def.get("enum")
            if enum_vals and value not in enum_vals:
                errors.append(
                    f"{entity_name}.{attr_name}: valor '{value}' inválido. "
                    f"Esperado: {enum_vals}"
                )

            # Verifica constraints
            constraints = attr_def.get("constraints", "")
            if constraints:
                if ">= 0" in constraints and isinstance(value, (int, float)):
                    if value < 0:
                        errors.append(f"{entity_name}.{attr_name}: deve ser >= 0 (valor: {value})")

        # Aplica constraints específicas da entidade
        for constraint in self.constraints.get("entity_validation", []):
            rule = constraint.get("rule", "")
            if entity_name in rule:
                # Validação simples por regex no nome
                if "budget = 0" in rule and attrs.get("budget", 1) == 0:
                    if attrs.get("status") == "active":
                        errors.append(f"{entity_name}: budget=0 não pode ter status=active")

        return len(errors) == 0, errors

    # =====================================================================
    # RELAÇÕES
    # =====================================================================

    def get_relationships(self, entity_name: str) -> dict:
        """Retorna todas as relações de uma entidade."""
        return self.relationships.get(entity_name, {})

    def has_relationship(self, source: str, relationship: str, target: str) -> bool:
        """Verifica se uma relação válida existe."""
        rels = self.get_relationships(source)
        rel_def = rels.get(relationship)
        return rel_def is not None and rel_def.get("target") == target

    # =====================================================================
    # CONSTRAINTS DE ATRIBUTOS
    # =====================================================================

    def validate_metric(self, metric: dict) -> Tuple[bool, str]:
        """Valida uma métrica específica contra constraints semânticas."""
        name = metric.get("name", "")
        value = metric.get("value", 0)

        for rule in self.constraints.get("attribute_validation", []):
            if rule.get("entity") == "Metric":
                rule_text = rule.get("rule", "")
                if "CTR" in rule_text and name == "CTR":
                    if not (0 <= value <= 100):
                        return False, f"CTR deve estar entre 0 e 100 (valor: {value})"
                if "CPC" in rule_text and name == "CPC":
                    if value < 0:
                        return False, f"CPC deve ser >= 0 (valor: {value})"
                if "ROAS" in rule_text and name == "ROAS":
                    if value < 0:
                        return False, f"ROAS deve ser >= 0 (valor: {value})"

        if name in ["CTR", "CPC", "ROAS", "impressions", "clicks", "conversions"]:
            if "value" not in metric:
                return False, "Campo 'value' obrigatório para métricas"

        return True, "ok"

    def validate_claim(self, claim: dict) -> Tuple[bool, str]:
        """Valida um claim contra constraints."""
        conf = claim.get("confidence", 0)
        if not (0.0 <= conf <= 1.0):
            return False, f"Confidence deve estar entre 0.0 e 1.0 (valor: {conf})"
        if "source" not in claim and "sources" not in claim:
            return False, "Claim precisa de ao menos uma source"
        return True, "ok"

    # =====================================================================
    # DESAMBIGUAÇÃO SEMÂNTICA
    # =====================================================================

    def disambiguate(self, term: str, context: str) -> dict:
        """
        Desambigua um termo conforme o contexto (bridge).
        Ex: disambiguate("CPC", "dv360") -> { meaning: "Cost Per Click", unit: "BRL" }
        """
        disamb = self.constraints.get("disambiguation", [])
        for entry in disamb:
            if entry.get("term") == term:
                contexts = entry.get("contexts", {})
                if context in contexts:
                    return contexts[context]
                # Fallback: primeiro contexto disponível
                for ctx_name, ctx_data in contexts.items():
                    return {**ctx_data, "_fallback_context": ctx_name}
        return {"meaning": term, "_unknown": True}

    def disambiguate_metric(self, metric_name: str, platform: str) -> str:
        """Retorna o significado de uma métrica no contexto de uma plataforma."""
        info = self.disambiguate(metric_name, platform)
        meaning = info.get("meaning", metric_name)
        unit = info.get("unit", "")
        if unit:
            return f"{meaning} ({unit})"
        return meaning

    # =====================================================================
    # BRIDGE MAPPING
    # =====================================================================

    def get_bridge_for_entity(self, entity_name: str) -> List[str]:
        """Retorna quais bridges operam sobre uma entidade."""
        bridges = []
        for bridge_name, bridge_def in self.bridge_mapping.items():
            if entity_name in bridge_def.get("entities", []):
                bridges.append(bridge_name)
        return bridges

    def get_bridge_info(self, bridge_name: str) -> dict:
        """Retorna informações sobre uma bridge na ontologia."""
        return self.bridge_mapping.get(bridge_name, {})

    def bridge_produces(self, bridge_name: str, entity_name: str) -> bool:
        """Verifica se uma bridge produz determinada entidade."""
        info = self.get_bridge_info(bridge_name)
        return entity_name in info.get("produces", [])

    def bridge_reads(self, bridge_name: str, entity_name: str) -> bool:
        """Verifica se uma bridge lê determinada entidade."""
        info = self.get_bridge_info(bridge_name)
        return entity_name in info.get("reads", [])

    # =====================================================================
    # QUERY / BUSCA
    # =====================================================================

    def search_entities(self, text: str) -> List[dict]:
        """Busca entidades relacionadas a um texto (usado pelo router)."""
        text_lower = text.lower()
        results = []

        # Entidades
        for name, defn in self.entities.items():
            desc = defn.get("description", "").lower()
            attrs_names = list(defn.get("attributes", {}).keys())
            if (text_lower in name.lower() or
                text_lower in desc or
                any(text_lower in a for a in attrs_names)):
                results.append({
                    "type": "entity",
                    "name": name,
                    "description": defn.get("description", ""),
                    "relevance": 0.8 if text_lower in name.lower() else 0.5
                })

        # Relações
        for src, rels in self.relationships.items():
            for rel_name, rel_defn in rels.items():
                if text_lower in rel_name.lower() or text_lower in src.lower():
                    results.append({
                        "type": "relationship",
                        "source": src,
                        "name": rel_name,
                        "target": rel_defn.get("target", ""),
                        "description": rel_defn.get("description", ""),
                        "relevance": 0.6
                    })

        # Ordena por relevância
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results

    def summarize(self) -> dict:
        """Retorna sumário da ontologia."""
        return {
            "version": self.metadata.get("version", "unknown"),
            "entities": len(self.entities),
            "relationships": sum(len(v) for v in self.relationships.values()),
            "bridges_mapped": len(self.bridge_mapping),
            "entity_names": list(self.entities.keys()),
            "constraint_rules": len(self.constraints.get("attribute_validation", [])) +
                                len(self.constraints.get("entity_validation", [])),
            "disambiguation_terms": len(self.constraints.get("disambiguation", []))
        }


# =====================================================================
# SINGLETON
# =====================================================================
_ontology_engine = None


def get_ontology() -> OntologyEngine:
    global _ontology_engine
    if _ontology_engine is None:
        _ontology_engine = OntologyEngine()
    return _ontology_engine


# =====================================================================
# CLI RÁPIDO
# =====================================================================
if __name__ == "__main__":
    ont = get_ontology()
    summary = ont.summarize()
    print(json.dumps(summary, indent=2))
    print("\n--- Entidades ---")
    for e in ont.list_entities():
        print(f"  {e}")
    print(f"\nTotal: {len(ont.list_entities())} entidades")
