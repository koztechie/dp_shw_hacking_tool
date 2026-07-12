import os
import logging
import warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="huggingface_hub")

from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
