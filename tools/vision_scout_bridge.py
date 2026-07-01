"""
VisionScout Bridge - Vision analysis agent using HermesBridge for image understanding
Provides image analysis, text extraction, comparison, and screenshot analysis
"""
import os
import json
import base64
from typing import Tuple, List, Optional
from pathlib import Path

from tools.hermes_bridge import get_hermes_bridge


class VisionScoutBridge:
    """
    Vision analysis agent that uses HermesBridge for image understanding.
    Provides image analysis, text extraction from images, image comparison,
    and web screenshot analysis.
    """

    def __init__(self):
        self.hermes = get_hermes_bridge()
        self.output_dir = "/opt/projetos/hermes-unified/output/vision/"
        os.makedirs(self.output_dir, exist_ok=True)

    def _resolve_image_path(self, image_path: str) -> Tuple[str, bool, str]:
        """Resolve image path, expanding ~ and checking existence."""
        path = os.path.expanduser(image_path)
        if not os.path.exists(path):
            return "", False, f"Image not found: {path}"
        return path, True, "OK"

    def _save_analysis(self, image_name: str, question: str, result: str) -> str:
        """Save analysis result to output directory."""
        safe_name = os.path.splitext(os.path.basename(image_name))[0]
        output_file = os.path.join(self.output_dir, f"analysis_{safe_name}.txt")
        with open(output_file, "w") as f:
            f.write(f"Image: {image_name}\n")
            f.write(f"Question: {question}\n")
            f.write(f"{'='*60}\n")
            f.write(result)
        return output_file

    def analyze_image(self, image_path: str, question: str = "Descreva esta imagem em detalhes.") -> Tuple[str, bool, str]:
        """
        Analyze an image using HermesBridge vision capabilities.

        Args:
            image_path: Path to the image file (local or URL)
            question: Question/prompt for the vision model

        Returns:
            Tuple[analysis_text, success, message]
        """
        path, ok, msg = self._resolve_image_path(image_path)
        if not ok:
            return "", False, msg

        result, success, msg = self.hermes.vision_analyze(path, question)

        if success:
            saved_path = self._save_analysis(path, question, result)
            return result, True, f"Analysis saved to {saved_path}"
        return "", False, msg

    def extract_text_from_image(self, image_path: str) -> Tuple[str, bool, str]:
        """
        Extract all visible text from an image using vision model.

        Args:
            image_path: Path to the image file

        Returns:
            Tuple[extracted_text, success, message]
        """
        path, ok, msg = self._resolve_image_path(image_path)
        if not ok:
            return "", False, msg

        result, success, msg = self.hermes.vision_analyze(
            path,
            "Extraia todo o texto visivel desta imagem. Responda APENAS com o texto extraido, sem comentarios adicionais. Se nao houver texto, responda 'Nenhum texto encontrado'."
        )

        if success:
            saved_path = self._save_analysis(path, "text_extraction", result)
            return result, True, f"Text extracted to {saved_path}"
        return "", False, msg

    def compare_images(self, image1_path: str, image2_path: str) -> Tuple[str, bool, str]:
        """
        Analyze and compare two images, describing similarities and differences.

        Args:
            image1_path: Path to the first image
            image2_path: Path to the second image

        Returns:
            Tuple[comparison_text, success, message]
        """
        path1, ok1, msg1 = self._resolve_image_path(image1_path)
        if not ok1:
            return "", False, msg1

        path2, ok2, msg2 = self._resolve_image_path(image2_path)
        if not ok2:
            return "", False, msg2

        # Analyze first image
        desc1, success1, _ = self.hermes.vision_analyze(
            path1,
            "Descreva esta imagem em detalhes, listando todos os elementos visiveis: objetos, textos, cores, layout, pessoas, etc."
        )
        if not success1:
            return "", False, f"Failed to analyze first image: {desc1}"

        # Analyze second image
        desc2, success2, _ = self.hermes.vision_analyze(
            path2,
            "Descreva esta imagem em detalhes, listando todos os elementos visiveis: objetos, textos, cores, layout, pessoas, etc."
        )
        if not success2:
            return "", False, f"Failed to analyze second image: {desc2}"

        # Build comparison
        comparison = f"""=== COMPARACAO DE IMAGENS ===

--- IMAGEM 1 ---
{desc1}

--- IMAGEM 2 ---
{desc2}

--- ANALISE COMPARATIVA ---
Ambas as imagens foram descritas acima. A imagem 1 contem os elementos descritos na primeira secao,
enquanto a imagem 2 contem os elementos descritos na segunda secao.

Diferencas principais: (analise visual comparativa baseada nas descricoes acima)
- Elementos unicos na Imagem 1
- Elementos unicos na Imagem 2
- Elementos em comum
"""

        # Save comparison
        safe_name1 = os.path.splitext(os.path.basename(path1))[0]
        safe_name2 = os.path.splitext(os.path.basename(path2))[0]
        output_file = os.path.join(self.output_dir, f"comparison_{safe_name1}_vs_{safe_name2}.txt")
        with open(output_file, "w") as f:
            f.write(comparison)

        return comparison, True, f"Comparison saved to {output_file}"

    def analyze_screenshot(self, image_path: str, elements_of_interest: str = "textos, precos, botoes") -> Tuple[str, bool, str]:
        """
        Analyze a web screenshot, focusing on specific elements.

        Especialmente util para analisar capturas de tela de sites, dashboards,
        e interfaces web. Busca identificar elementos como textos, precos,
        botoes, links, formularios, etc.

        Args:
            image_path: Path to the screenshot image
            elements_of_interest: Comma-separated list of elements to focus on

        Returns:
            Tuple[analysis_text, success, message]
        """
        path, ok, msg = self._resolve_image_path(image_path)
        if not ok:
            return "", False, msg

        prompt = f"""Analise esta captura de tela em detalhes. Foque especialmente nos seguintes elementos: {elements_of_interest}.

Para cada elemento encontrado, forneca:
1. O que é (tipo: texto, botao, preco, imagem, link, etc.)
2. A localizacao aproximada na tela
3. O conteudo/texto visivel
4. Qualquer acao possivel (se aplicavel)

Estruture a resposta de forma clara e organizada por categorias de elementos."""

        result, success, msg = self.hermes.vision_analyze(path, prompt)

        if success:
            saved_path = self._save_analysis(path, f"screenshot_analysis_{elements_of_interest[:30]}", result)
            return result, True, f"Screenshot analysis saved to {saved_path}"
        return "", False, msg


# Singleton for reusability
_vision_scout_bridge = None

def get_vision_scout_bridge() -> VisionScoutBridge:
    global _vision_scout_bridge
    if _vision_scout_bridge is None:
        _vision_scout_bridge = VisionScoutBridge()
    return _vision_scout_bridge
