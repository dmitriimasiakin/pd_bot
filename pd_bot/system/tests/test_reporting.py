from reporting.formatter import ReportFormatter
from reporting.exporter import ReportExporter

def test_formatter_and_export(tmp_path):
    formatter = ReportFormatter()
    exporter = ReportExporter(out_dir=str(tmp_path))

    fake_results = {"scoring": {"total_score": 10, "max_score": 14, "PD": 0.28, "risk_class": "Средний риск"}}
    md = formatter.format_report(fake_results)
    assert "# 📊 Отчёт" in md

    md_file = exporter.export_markdown(md, "test.md")
    pdf_file = exporter.export_pdf(md, [], "test.pdf")
    txt_file = exporter.export_txt(md, "test.txt")

    assert md_file.endswith(".md")
    assert pdf_file.endswith(".pdf")
    assert txt_file.endswith(".txt")
