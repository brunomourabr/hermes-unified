"""
Reporter Bridge - PDF and HTML Report Generator
Generates professional reports using fpdf2, Jinja2, and optionally python-pptx
"""
import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime

# Try to import fpdf2 for PDF generation
try:
    from fpdf import FPDF
    FPDF2_AVAILABLE = True
except ImportError:
    FPDF2_AVAILABLE = False

# Try to import Jinja2 for HTML templates
try:
    from jinja2 import Environment, FileSystemLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

# Try to import KnowledgeGraphStore for saving report sources
try:
    from tools.memory_bridge import get_kg
    KG_AVAILABLE = True
except ImportError:
    KG_AVAILABLE = False


class ReporterBridge:
    """
    Bridge between LangGraph and Report Generation.
    Creates professional PDF reports, HTML reports, and full reports with charts.
    """

    def __init__(self):
        self.output_dir = "/opt/projetos/hermes-unified/output/reports/"
        os.makedirs(self.output_dir, exist_ok=True)

        # 42c brand colors
        self.colors = {
            "primary": "#1a1a2e",
            "secondary": "#e94560",
            "accent": "#0f3460",
            "text": "#16213e",
            "light_bg": "#f8f9fa",
            "white": "#ffffff"
        }

    def _sanitize_filename(self, title: str) -> str:
        """Create a safe filename from title."""
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe}_{timestamp}"

    def _save_report_to_kg(self, title: str, sections: list, filepath: str) -> None:
        """Save report and its sections as Sources in KnowledgeGraphStore."""
        if not KG_AVAILABLE:
            return
        try:
            kg = get_kg()
            if kg is None:
                return

            bridge_name = "reporter_bridge"
            filename = os.path.basename(filepath) if filepath else ""
            report_url = filepath  # Use filepath as the URL reference

            # Save the report itself as a source
            report_source = {
                "title": title,
                "url": report_url,
                "domain": "report",
                "relevance_score": 1.0
            }
            report_id = kg.save_source(report_source, bridge=bridge_name)

            # Save each section as a source, linked to the report
            for i, sec in enumerate(sections, start=1):
                heading = sec.get("heading", f"Section {i}")
                content = sec.get("content", "")
                section_id = kg.save_source({
                    "title": f"{title} - {heading}",
                    "url": report_url,
                    "domain": "report_section",
                    "relevance_score": 0.8
                }, bridge=bridge_name)

                # Link section -> report (child_of relationship)
                kg.add_relationship(
                    source_type="source", source_id=section_id,
                    rel_type="child_of",
                    target_type="source", target_id=report_id,
                    bridge=bridge_name
                )

        except Exception as e:
            print(f"   ⚠ [ReporterBridge] Error saving to KG: {e}")

    def generate_pdf(self, title: str, sections: list, filename: str = None) -> Tuple[str, bool, str]:
        """
        Generate a professional PDF report with cover page, TOC, sections, and page numbers.

        Args:
            title: Report title
            sections: List of dicts with "heading" and "content" keys
            filename: Optional output filename

        Returns:
            Tuple[filepath, success, message]
        """
        if not FPDF2_AVAILABLE:
            return "", False, "fpdf2 not installed. Install with: pip install fpdf2"

        if not filename:
            filename = self._sanitize_filename(title) + ".pdf"

        filepath = os.path.join(self.output_dir, filename)

        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=20)

            # ============================================
            # COVER PAGE
            # ============================================
            pdf.add_page()
            pdf.set_fill_color(26, 26, 46)  # #1a1a2e
            pdf.rect(0, 0, 210, 297, "F")

            # Title
            pdf.set_text_color(233, 69, 96)  # #e94560
            pdf.set_font("Helvetica", "B", 32)
            pdf.set_y(80)
            pdf.cell(0, 20, title, align="C", new_x="LMARGIN", new_y="NEXT")

            # Decorative line
            pdf.set_draw_color(233, 69, 96)
            pdf.set_line_width(0.8)
            pdf.line(60, pdf.get_y() + 5, 150, pdf.get_y() + 5)

            # Subtitle / date
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "", 14)
            pdf.set_y(pdf.get_y() + 20)
            pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 10, f"Sections: {len(sections)}", align="C", new_x="LMARGIN", new_y="NEXT")

            # ============================================
            # TABLE OF CONTENTS
            # ============================================
            pdf.add_page()
            pdf.set_text_color(26, 26, 46)
            pdf.set_font("Helvetica", "B", 22)
            pdf.cell(0, 15, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(233, 69, 96)
            pdf.set_line_width(0.5)
            pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
            pdf.ln(10)

            pdf.set_font("Helvetica", "", 12)
            for i, section in enumerate(sections, start=1):
                heading = section.get("heading", f"Section {i}")
                pdf.set_text_color(15, 52, 96)  # #0f3460
                pdf.cell(0, 10, f"  {i}. {heading}", new_x="LMARGIN", new_y="NEXT")

            # ============================================
            # SECTIONS
            # ============================================
            for i, section in enumerate(sections, start=1):
                heading = section.get("heading", f"Section {i}")
                content = section.get("content", "")

                pdf.add_page()

                # Section header with accent line
                pdf.set_fill_color(15, 52, 96)  # #0f3460
                pdf.rect(10, pdf.get_y(), 4, 12, "F")
                pdf.set_text_color(26, 26, 46)
                pdf.set_font("Helvetica", "B", 18)
                pdf.set_x(18)
                pdf.cell(0, 12, f"{i}. {heading}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)

                pdf.set_draw_color(233, 69, 96)
                pdf.set_line_width(0.3)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(6)

                # Content
                pdf.set_text_color(22, 33, 62)
                pdf.set_font("Helvetica", "", 11)

                # Handle multi-line content
                for paragraph in content.split("\n"):
                    paragraph = paragraph.strip()
                    if paragraph:
                        # Check if it's a bullet point
                        if paragraph.startswith("- ") or paragraph.startswith("* "):
                            pdf.set_x(20)
                            pdf.cell(5, 7, "-")
                            pdf.multi_cell(0, 7, paragraph[2:])
                        else:
                            pdf.multi_cell(0, 7, paragraph)
                        pdf.ln(2)

            # ============================================
            # FOOTER with page numbers
            # ============================================
            pdf.footer = lambda: None  # Reset
            page_count = pdf.page_no()

            for page_num in range(1, page_count + 1):
                pdf.page = page_num
                pdf.set_y(-15)
                pdf.set_font("Helvetica", "I", 8)
                pdf.set_text_color(128, 128, 128)
                pdf.cell(0, 10, f"Page {page_num} of {page_count}", align="C")

            pdf.output(filepath)
            self._save_report_to_kg(title, sections, filepath)
            return filepath, True, f"PDF report generated: {filename}"

        except Exception as e:
            return "", False, f"PDF generation error: {str(e)[:200]}"

    def generate_html_report(self, title: str, sections: list, filename: str = None) -> Tuple[str, bool, str]:
        """
        Generate a professional HTML report with 42c branding using Jinja2.

        Args:
            title: Report title
            sections: List of dicts with "heading" and "content" keys
            filename: Optional output filename

        Returns:
            Tuple[filepath, success, message]
        """
        if not filename:
            filename = self._sanitize_filename(title) + ".html"

        filepath = os.path.join(self.output_dir, filename)

        try:
            # Build TOC
            toc_items = ""
            for i, sec in enumerate(sections, start=1):
                toc_items += f'<li><a href="#sec{i}">{sec.get("heading", f"Section {i}")}</a></li>\n'

            # Build sections HTML
            sections_html = ""
            for i, sec in enumerate(sections, start=1):
                heading = sec.get("heading", f"Section {i}")
                content = sec.get("content", "")

                # Convert plain text to HTML paragraphs, handling bullet points
                content_html = ""
                for line in content.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("- ") or line.startswith("* "):
                        content_html += f"<li>{line[2:]}</li>\n"
                    else:
                        content_html += f"<p>{line}</p>\n"

                if "<li>" in content_html:
                    content_html = f"<ul>{content_html}</ul>"

                sections_html += f"""
                <section id="sec{i}" class="section">
                    <div class="section-header">
                        <span class="section-number">{i}</span>
                        <h2>{heading}</h2>
                    </div>
                    <div class="section-content">
                        {content_html}
                    </div>
                </section>
                """

            # Build full HTML
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
            color: #16213e;
            background: #f5f5f5;
            line-height: 1.6;
        }}
        .cover {{
            background: #1a1a2e;
            color: white;
            padding: 100px 40px 60px;
            text-align: center;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .cover h1 {{
            font-size: 2.8em;
            color: #e94560;
            margin-bottom: 20px;
            font-weight: 800;
        }}
        .cover .line {{
            width: 80px;
            height: 3px;
            background: #e94560;
            margin: 20px auto;
        }}
        .cover p {{
            font-size: 1.1em;
            color: #aaa;
            margin-top: 30px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        .toc {{
            background: white;
            border-radius: 8px;
            padding: 30px 40px;
            margin-bottom: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .toc h2 {{
            color: #1a1a2e;
            font-size: 1.5em;
            margin-bottom: 15px;
            border-bottom: 2px solid #e94560;
            padding-bottom: 8px;
        }}
        .toc ul {{
            list-style: none;
        }}
        .toc li {{
            padding: 6px 0;
        }}
        .toc a {{
            color: #0f3460;
            text-decoration: none;
            font-size: 1.05em;
        }}
        .toc a:hover {{
            color: #e94560;
        }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 30px 35px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            border-bottom: 1px solid #eee;
            padding-bottom: 12px;
        }}
        .section-number {{
            background: #e94560;
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 0.9em;
            flex-shrink: 0;
        }}
        .section-header h2 {{
            color: #1a1a2e;
            font-size: 1.4em;
        }}
        .section-content p {{
            margin-bottom: 12px;
            font-size: 1em;
        }}
        .section-content ul {{
            margin: 10px 0 10px 20px;
        }}
        .section-content li {{
            margin-bottom: 6px;
        }}
        .footer {{
            text-align: center;
            padding: 30px;
            color: #999;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>{title}</h1>
        <div class="line"></div>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p style="font-size:0.9em;margin-top:5px;">{len(sections)} sections</p>
    </div>

    <div class="container">
        <div class="toc">
            <h2>Table of Contents</h2>
            <ul>
                {toc_items}
            </ul>
        </div>

        {sections_html}

        <div class="footer">
            <p>Generated by Hermes-Unified Reporter Agent &mdash; 42c</p>
        </div>
    </div>
</body>
</html>"""

            with open(filepath, "w") as f:
                f.write(html)

            self._save_report_to_kg(title, sections, filepath)
            return filepath, True, f"HTML report generated: {filename}"

        except Exception as e:
            return "", False, f"HTML report error: {str(e)[:200]}"

    def generate_full_report(self, title: str, sections: list, charts: list = None) -> Tuple[dict, bool, str]:
        """
        Generate a full report (PDF + HTML) and optionally embed chart images.

        Args:
            title: Report title
            sections: List of dicts with "heading" and "content" keys
            charts: Optional list of chart image file paths to include

        Returns:
            Tuple[{"pdf_path": ..., "html_path": ...}, success, message]
        """
        results = {}
        errors = []

        # Generate PDF
        pdf_path, pdf_ok, pdf_msg = self.generate_pdf(title, sections)
        if pdf_ok:
            results["pdf_path"] = pdf_path
        else:
            errors.append(f"PDF: {pdf_msg}")

        # Generate HTML
        html_path, html_ok, html_msg = self.generate_html_report(title, sections)
        if html_ok:
            results["html_path"] = html_path
        else:
            errors.append(f"HTML: {html_msg}")

        # Add charts to results if provided
        if charts:
            results["charts"] = charts

        if results:
            msg = "Report generated: "
            parts = []
            if "pdf_path" in results:
                parts.append("PDF")
            if "html_path" in results:
                parts.append("HTML")
            msg += " + ".join(parts)
            if errors:
                msg += " (warnings: " + "; ".join(errors) + ")"
            return results, True, msg

        return results, False, "Report generation failed: " + "; ".join(errors)


# Singleton
_reporter_bridge = None

def get_reporter_bridge() -> ReporterBridge:
    global _reporter_bridge
    if _reporter_bridge is None:
        _reporter_bridge = ReporterBridge()
    return _reporter_bridge
