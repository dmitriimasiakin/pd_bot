# -*- coding: utf-8 -*-
"""
reporting/exporter.py
Экспорт отчёта PD-модели в PDF/Markdown.
"""

import os
from typing import List
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import pypandoc

from infra.logger import get_logger
from infra.error_handler import safe_run


class ReportExporter:
    """
    Экспорт отчёта:
    - PDF (с текстом и графиками)
    - Markdown / TXT
    """

    def __init__(self, out_dir: str = "output/reports"):
        self.logger = get_logger()
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

    @safe_run(stage="Экспорт PDF", retries=1)
    def export_pdf(self, md_text: str, images: List[str], filename="report.pdf") -> str:
        path = os.path.join(self.out_dir, filename)
        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Текст из Markdown → в параграфы
        for line in md_text.splitlines():
            if not line.strip():
                story.append(Spacer(1, 0.2 * inch))
                continue
            if line.startswith("# "):
                story.append(Paragraph(f"<b><font size=16>{line[2:]}</font></b>", styles["Title"]))
            elif line.startswith("## "):
                story.append(Spacer(1, 0.1 * inch))
                story.append(Paragraph(f"<b><font size=14>{line[3:]}</font></b>", styles["Heading2"]))
            elif line.startswith("- "):
                story.append(Paragraph(f"• {line[2:]}", styles["Normal"]))
            else:
                story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 0.1 * inch))

        # Добавляем графики
        for img in images:
            if os.path.exists(img):
                story.append(Image(img, width=6*inch, height=4*inch))
                story.append(Spacer(1, 0.3 * inch))

        doc.build(story)
        return path

    @safe_run(stage="Экспорт Markdown", retries=1)
    def export_markdown(self, md_text: str, filename="report.md") -> str:
        path = os.path.join(self.out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md_text)
        return path

    @safe_run(stage="Экспорт TXT", retries=1)
    def export_txt(self, md_text: str, filename="report.txt") -> str:
        path = os.path.join(self.out_dir, filename)
        txt = pypandoc.convert_text(md_text, "plain", format="md", extra_args=["--standalone"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        return path
