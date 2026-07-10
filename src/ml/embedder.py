"""src/ml/embedder.py — Єдиний менеджер Sentence-BERT (Singleton + Lazy Load)."""

import gc

from src.logger import logger


class EmbedderSingleton:
    _instance = None
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            logger.info("🧠 Завантаження Sentence-BERT (all-MiniLM-L6-v2)...")
            from sentence_transformers import SentenceTransformer

            cls._model = SentenceTransformer("all-MiniLM-L6-v2")
        return cls._model

    @classmethod
    def cleanup(cls):
        """Звільняє модель з RAM для економії пам'яті."""
        if cls._model is not None:
            del cls._model
            cls._model = None
            gc.collect()
            logger.info("🧹 Sentence-BERT видалено з RAM.")
