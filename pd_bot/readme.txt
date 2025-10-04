pd-model/
│
├── app.py                        # API (FastAPI)
├── requirements.txt              # окружение
├── README.md                     # инструкция
│
├── infra/                        # инфраструктура
│   ├── logger.py
│   ├── error_handler.py
│   └── watchdog.py
│
├── core/                         # загрузка и парсеры
│   ├── document_loader.py
│   ├── parser_opu.py
│   ├── parser_balance.py
│   ├── parser_51.py
│   ├── parser_osv.py
│   ├── parser_kp.py
│   └── utils.py
│
├── analysis/                     # анализ
│   ├── financials.py
│   ├── balance.py
│   ├── cashflow.py
│   ├── receivables.py
│   ├── payables.py
│   ├── deal.py
│   ├── retro.py
│   └── scoring.py
│
├── reporting/                    # отчёты
│   ├── formatter.py
│   ├── visualizer.py
│   └── exporter.py
│
├── system/                       # системные настройки
│   ├── config.py
│   ├── main.py
│   └── tests/
│       ├── test_loaders.py
│       ├── test_parsers.py
│       ├── test_analysis.py
│       └── test_reporting.py
│
├── input/                        # сюда менеджер грузит документы
├── output/                       # результаты
│   ├── reports/                  # PDF/MD/TXT отчёты
│   └── plots/                    # графики
└── logs/                         # лог-файлы
