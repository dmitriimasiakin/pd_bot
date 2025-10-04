# -*- coding: utf-8 -*-
"""
app.py
Боевой REST API для загрузки документов и запуска PD-модели.
"""

import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from system.main import run_pipeline
from system import config
from infra.logger import get_logger
from infra.error_handler import safe_run


logger = get_logger()
app = FastAPI(title="PD Model API", description="API для PD-модели (Probability of Default) в лизинге")


# ---------- Upload документов ----------
@app.post("/upload-doc")
@safe_run(stage="Upload Document", retries=1)
async def upload_doc(file: UploadFile = File(...)):
    """Загрузка документа в input/"""
    try:
        file_path = os.path.join(config.INPUT_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Загружен документ: {file.filename}")
        return {"status": "ok", "filename": file.filename, "path": file_path}
    except Exception as e:
        logger.error(f"Ошибка загрузки документа: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при загрузке документа")


# ---------- Запуск PD-модели ----------
@app.post("/run-pd")
@safe_run(stage="Запуск пайплайна PD", retries=1)
def run_pd():
    """Запуск анализа PD по всем документам из input/"""
    try:
        run_pipeline()
        logger.info("Анализ PD завершён")
        return {
            "status": "ok",
            "report_pdf": f"/download/report/pdf",
            "report_md": f"/download/report/md",
            "report_txt": f"/download/report/txt",
        }
    except Exception as e:
        logger.error(f"Ошибка в пайплайне PD: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при запуске пайплайна")


# ---------- Download отчётов ----------
@app.get("/download/report/{format}")
@safe_run(stage="Скачивание отчёта", retries=1)
def download_report(format: str):
    """Скачивание отчёта в выбранном формате: pdf/md/txt"""
    mapping = {
        "pdf": os.path.join(config.REPORTS_DIR, "report.pdf"),
        "md": os.path.join(config.REPORTS_DIR, "report.md"),
        "txt": os.path.join(config.REPORTS_DIR, "report.txt"),
    }
    path = mapping.get(format.lower())
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Файл отчёта {format} не найден")
    return FileResponse(path, filename=f"report.{format}")


# ---------- Healthcheck ----------
@app.get("/health")
def health():
    """Проверка состояния сервера"""
    return JSONResponse({"status": "running", "reports_dir": config.REPORTS_DIR})
