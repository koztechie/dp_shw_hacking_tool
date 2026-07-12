import sys
from pathlib import Path
import json

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover

def generate_project_assets(techspec: dict) -> dict:
    """
    Генерує стартовий код та промпти для медіа-генераторів на основі ТЗ.
    ОПТИМІЗАЦІЯ ВИТРАТ ТА ШВИДКОСТІ: вимагаємо лаконічний boilerplate для запобігання таймаутам.
    """
    logger.info(f"💻 Запуск генерації коду та медіа-промптів для: {techspec.get('project_name', 'Unknown')}")
    
    prompt = f"""
    You are an AI Auto-Coder, DevOps Cloud Engineer, and Creative Director. 
    Based on the following Technical Specification, generate starter assets for a developer.
    
    TECHSPEC:
    {json.dumps(techspec, ensure_ascii=False)[:2000]}
    
    Return EXACTLY a JSON object matching this schema:
    {{
      "bash_setup_script": "A valid, highly CONCISE bash script (using mkdir, touch, and cat << 'EOF') that creates the project structure. CRITICAL: DO NOT GENERATE Dockerfiles unless explicitly requested. If the project targets mobile stores, include lightweight bash commands in the setup script to: 1) Verify physical device connection via `adb devices`. 2) Add android platform: `npx cap add android`. 3) Run on device: `npx cap run android`. Instruct the developer to avoid Android Studio. Keep files under 15 lines.",
      "ui_prompts": ["Highly detailed Midjourney prompt for the app dashboard", "Prompt for the mobile view"],
      "video_prompts": ["RunwayML Gen-2 prompt for the intro video shot", "Prompt for the app UI animation"]
    }}
    """
    
    # Вимикаємо роздуми для швидкості та упередження таймаутів
    result = generate_json_with_failover(prompt, thinking=False)
    
    if "fallback" in result or "bash_setup_script" not in result:
        return {
            "bash_setup_script": "mkdir -p project\ntouch project/main.py\necho 'print(\"Fallback\")' > project/main.py",
            "ui_prompts": ["Modern UI dashboard, dark theme, neon accents, UI/UX --v 6.0"],
            "video_prompts": ["A cinematic shot of a computer screen showing futuristic code, glowing."]
        }
        
    return result

if __name__ == "__main__":
    mock_ts = {"project_name": "Test App", "architecture": {"backend": "FastAPI", "frontend": "React"}}
    print(json.dumps(generate_project_assets(mock_ts), indent=2, ensure_ascii=False))
