#!/bin/bash
# АНТИКРИХКІСТЬ: Створення ефемерного PyPI-сумісного зліпку для аудиту безпеки

cd "$(dirname "$0")"

echo "====================================================="
echo "🛡️ ЗАПУСК АУДИТУ БЕЗПЕКИ ЗАЛЕЖНОСТЕЙ (CVE SCANNER)"
echo "====================================================="

if [ ! -f "venv/bin/python" ]; then
    echo "❌ Віртуальне середовище не знайдено!"
    exit 1
fi

source venv/bin/activate

echo "🧹 Створення тимчасового сумісного файлу для PyPI аудиту..."
python3 -c "
from pathlib import Path
import re
req_file = Path('requirements.txt')
audit_file = Path('requirements.audit.txt')
if req_file.exists():
    lines = req_file.read_text(encoding='utf-8').splitlines()
    clean_lines = []
    for l in lines:
        # Вирізаємо локальні git-посилання
        if 'dp_shw_hacking_tool' in l.lower() or 'git+' in l.lower() or 'github.com' in l.lower():
            continue
        if l.strip() == '':
            continue
        # АНТИКРИХКІСТЬ: Видаляємо суфікси +cpu / +cu, щоб pip-audit міг знайти їх на PyPI
        l_clean = re.sub(r'\+cpu|\+cu\d+', '', l)
        clean_lines.append(l_clean)
    audit_file.write_text('\n'.join(clean_lines) + '\n', encoding='utf-8')
"

echo "📦 Встановлення/оновлення pip-audit..."
pip install --prefer-binary pip-audit > /dev/null 2>&1

echo "🔍 Аналіз на відомі вразливості..."
if [ -f "requirements.audit.txt" ]; then
    # Запускаємо аудит на сумісному зліпку
    pip-audit -r requirements.audit.txt
    
    # Видаляємо тимчасовий файл, зберігаючи requirements.txt незайманим
    rm -f requirements.audit.txt
else
    echo "❌ Помилка створення тимчасового файлу для аудиту!"
fi

echo "====================================================="
echo "✅ Аудит завершено."
