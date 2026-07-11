"""
DP_SHW Copy System — Українська локалізація
Антикрихкий копірайтинг: тексти, що працюють навіть при помилках системи
"""

COPY = {
    # === BRAND ===
    "brand.name": "DP_SHW",
    "brand.tagline": "MLOps для хакатонів",
    "brand.claim": "Ваша локальна машина для перемог",
    
    # === NAVIGATION ===
    "nav.dashboard": "Дашборд",
    "nav.training": "Навчання моделі",
    "nav.analyze": "Новий аналіз",
    "nav.history": "Історія",
    "nav.settings": "Налаштування",
    
    # === DASHBOARD ===
    "dashboard.title": "Стан системи",
    "dashboard.subtitle": "ML-модель і база даних у реальному часі",
    "dashboard.metric.hackathons": "Хакатонів у базі",
    "dashboard.metric.projects": "Проаналізовано проектів",
    "dashboard.metric.winners": "Відомих переможців",
    "dashboard.metric.predictions": "Зроблено прогнозів",
    "dashboard.metric.win_rate": "Історичний win rate",
    "dashboard.ml_health": "Здоров'я ML-моделі",
    "dashboard.last_updated": "Останнє оновлення",
    
    # === EMPTY STATES (антикрихкі — ведуть до дії) ===
    "empty.history.title": "Історія поки порожня",
    "empty.history.description": "Щойно ви проаналізуєте перший хакатон, усі прогнози та ідеї з'являться тут. Так ви зможете порівнювати шанси на різних змаганнях.",
    "empty.history.cta": "Проаналізувати перший хакатон",
    
    "empty.training.title": "Модель ще не навчена",
    "empty.training.description": "Щоб прогнози були точними, системі потрібно побачити ~10 000 минулих проектів. Це одноразова процедура на 2–4 години.",
    "empty.training.cta": "Почати збір даних",
    "empty.training.footnote": "Працює у фоні. Ви можете продовжувати працювати.",
    
    "empty.ideas.title": "Немає згенерованих ідей",
    "empty.ideas.description": "Спочатку проаналізуйте хакатон — система витягне правила, спонсорів і критерії суддівства. Потім згенерує 3 ідеї з оцінкою шансів.",
    "empty.ideas.cta": "Перейти до аналізу",
    
    # === ONBOARDING (послідовність кроків) ===
    "onboarding.welcome": "Ласкаво просимо",
    "onboarding.intro": "Це ваша локальна MLOps-машина. Вона не надсилає дані в хмару і працює навіть без інтернету — окрім етапу збору.",
    "onboarding.step1.title": "Крок 1. Навчіть модель",
    "onboarding.step1.body": "Скрапер збере історію Devpost. Це потрібно зробити один раз. Чим більше даних — тим точніші прогнози.",
    "onboarding.step1.meta": "≈ 2–4 години · ≈ 500 МБ на диску",
    "onboarding.step2.title": "Крок 2. Вставте URL хакатону",
    "onboarding.step2.body": "Система обійде захист Cloudflare, витягне правила, спонсорів і суддів. Триває 15–40 секунд.",
    "onboarding.step3.title": "Крок 3. Оберіть ідею",
    "onboarding.step3.body": "Отримайте 3 ідеї з відсотком перемоги від ML-моделі. Модель пояснить, чому саме ці ідеї мають шанси.",
    "onboarding.step4.title": "Крок 4. Експортуйте TechSpec",
    "onboarding.step4.body": "Погодинний план розробки на 48 годин — з урахуванням вашого заліза (AMD A4, 6 ГБ RAM).",
    "onboarding.skip": "Більше не показувати",
    
    # === ANALYZE PAGE ===
    "analyze.title": "Аналіз нового хакатону",
    "analyze.subtitle": "Вставте URL або завантажте HTML. Решту зробить система.",
    "analyze.tab.url": "Через URL",
    "analyze.tab.html": "Через HTML-файл",
    "analyze.input.label": "URL хакатону на Devpost",
    "analyze.input.placeholder": "https://devpost.com/software/...",
    "analyze.input.hint": "Приймаються лише HTTPS-посилання з домену devpost.com",
    "analyze.input.error.invalid": "Це не схоже на коректний URL Devpost. Перевірте адресу.",
    "analyze.input.error.http": "Приймаються лише безпечні HTTPS-посилання.",
    "analyze.input.error.ssrf": "З міркувань безпеки приймаються лише посилання на devpost.com.",
    "analyze.submit": "🔮 Запустити аналіз",
    "analyze.submit.loading": "Аналізую…",
    
    # === LOADING STATES (деталізовані, заспокійливі) ===
    "loading.title": "Аналіз триває",
    "loading.subtitle": "Зазвичай це 30–90 секунд. Система працює, навіть якщо екран не оновлюється.",
    "loading.step.scraping": "Зчитую сторінку хакатону…",
    "loading.step.constraints": "Витягую правила та обмеження…",
    "loading.step.osint": "Шукаю контекст про спонсорів і суддів…",
    "loading.step.ideas": "Генерую ідеї в кілька етапів (brainstorm → критика → відбір)…",
    "loading.step.scoring": "Оцінюю шанси кожної ідеї ML-моделлю…",
    "loading.tip.1": "Підказка: система імітує погляд трьох різних суддів.",
    "loading.tip.2": "Підказка: ідеї перевіряються на відповідність технологіям спонсорів.",
    "loading.tip.3": "Підказка: ML-модель враховує час подання — ранні проекти часто виграють.",
    "loading.cancel": "Скасувати",
    
    # === IDEAS PAGE ===
    "ideas.title": "3 ідеї для цього хакатону",
    "ideas.subtitle": "Кожна оцінена ML-моделлю. Натисніть, щоб побачити детальний TechSpec.",
    "ideas.score_label": "Шанс перемоги",
    "ideas.top_pick": "🏆 Найкраща ставка",
    "ideas.safe_bet": "✅ Надійний варіант",
    "ideas.risky": "⚡ Високий ризик — висока нагорода",
    "ideas.avoid": "⚠️ Низькі шанси",
    "ideas.cta.spec": "Створити TechSpec",
    "ideas.cta.regen": "🔄 Інші ідеї",
    "ideas.why_wins": "Чому це може виграти",
    "ideas.risk": "Головний ризик",
    "ideas.tech_stack": "Технології",
    "ideas.sponsor_match": "Відповідність спонсорам",
    
    # === TECHSPEC ===
    "techspec.title": "Технічне завдання",
    "techspec.subtitle": "Погодинний план на 48 годин. Адаптовано під ваше залізо.",
    "techspec.export.md": "⬇ Завантажити .md",
    "techspec.export.notion": "📋 Копіювати для Notion",
    "techspec.export.gist": "📦 Створити GitHub Gist",
    "techspec.section.architecture": "Архітектура",
    "techspec.section.timeline": "Погодинний план",
    "techspec.section.stack": "Стек технологій",
    "techspec.section.avoid": "Чого уникати",
    "techspec.section.demo": "Сценарій демо (60 секунд)",
    "techspec.hardware_warning": "⚙ План побудовано з урахуванням AMD A4 / 6 ГБ RAM. Локальна збірка мобільних застосунків неможлива — використовуйте cloud build.",
    
    # === TRAINING ===
    "training.title": "Навчання ML-моделі",
    "training.subtitle": "Система збере дані з Devpost і побудує ансамбль моделей.",
    "training.status.idle": "Готова до запуску",
    "training.status.running": "Збір триває…",
    "training.status.done": "Навчання завершено",
    "training.status.error": "Сталася помилка під час навчання",
    "training.progress.scraped": "Зібрано проектів",
    "training.progress.hackathons": "Оброблено хакатонів",
    "training.progress.eta": "Орієнтовно залишилось",
    "training.start": "▶ Почати збір даних",
    "training.pause": "⏸ Призупинити",
    "training.resume": "▶ Продовжити",
    "training.stop": "⏹ Зупинити",
    "training.warning": "Процес тривалий. Можна закрити вкладку — збір продовжиться у фоні.",
    
    # === HISTORY ===
    "history.title": "Історія аналізів",
    "history.subtitle": "Усі ваші прогнози. Порівнюйте шанси, шукайте патерни.",
    "history.search.placeholder": "Пошук за назвою хакатону…",
    "history.empty_search": "Нічого не знайдено за цим запитом.",
    "history.item.open": "Відкрити →",
    "history.item.delete": "Видалити назавжди",
    "history.delete.confirm.title": "Видалити цей аналіз?",
    "history.delete.confirm.body": "Відновити буде неможливо. ML-модель втратить цей кейс для навчання.",
    "history.delete.confirm.yes": "Видалити назавжди",
    "history.delete.confirm.no": "Скасувати",
    
    # === ERRORS (антикрихкі — завжди кажуть, ЩО РОБИТИ) ===
    "error.generic.title": "Щось пішло не так",
    "error.generic.body": "Система зіткнулася з неочікуваною проблемою. Спробуйте ще раз — або подивіться деталі нижче.",
    "error.generic.retry": "🔄 Спробувати знову",
    "error.generic.home": "← На дашборд",
    "error.generic.details": "Технічні деталі (для розробника)",
    
    "error.network.title": "Немає з'єднання з інтернетом",
    "error.network.body": "Система працює локально, але для цього кроку потрібен інтернет. Перевірте з'єднання і спробуйте знову.",
    
    "error.rate_limit.title": "Занадто багато запитів",
    "error.rate_limit.body": "Щоб не перевантажувати ваше залізо, система обмежує частоту запитів. Зачекайте хвилину і спробуйте знову.",
    "error.rate_limit.wait": "Зачекати {seconds} с",
    
    "error.api_down.title": "AI-сервіс тимчасово недоступний",
    "error.api_down.body": "Система автоматично перемикається на резервну модель (Llama 3.3). Якість може бути трохи нижчою, але результат ви отримаєте.",
    "error.api_down.fallback": "✓ Використовується резервна модель",
    
    "error.circuit_open.title": "AI-сервіс перевантажений",
    "error.circuit_open.body": "Запобіжник спрацював: система тимчасово не надсилає запити, щоб не витрачати ліміти. Зачекайте 5 хвилин або використовуйте офлайн-режим.",
    "error.circuit_open.timer": "Автоматична перевірка через {minutes} хв",
    
    "error.db_locked.title": "База даних зараз зайнята",
    "error.db_locked.body": "Інший процес (навчання або збір) використовує базу. Зачекайте завершення або зупиніть його на вкладці «Навчання».",
    
    "error.file_too_large.title": "Файл завеликий",
    "error.file_too_large.body": "Максимальний розмір — 5 МБ. Якщо HTML більший, спробуйте вставити URL хакатону.",
    
    "error.invalid_file.title": "Цей тип файлу не підтримується",
    "error.invalid_file.body": "Приймаються лише HTML-файли (.html, .htm). Інші формати можуть містити шкідливий код.",
    
    "error.ssrf_blocked.title": "Небезпечне посилання",
    "error.ssrf_blocked.body": "З міркувань безпеки приймаються лише посилання на devpost.com. Перевірте URL.",
    
    "error.validation.title": "Некоректні дані",
    "error.validation.body": "Перевірте введені дані. Вони мають неправильний формат.",
    
    
    # === MICROCOPY (деталі) ===
    "microcopy.or": "або",
    "microcopy.required": "обов'язкове поле",
    "microcopy.optional": "необов'язково",
    "microcopy.learn_more": "Детальніше",
    "microcopy.copied": "Скопійовано ✓",
    "microcopy.saving": "Зберігаю…",
    "microcopy.saved": "Збережено",
    
    # === HELP TEXTS (пояснення ML-концептів простою мовою) ===
    "help.pr_auc": "PR-AUC показує, наскільки модель відрізняє переможців від решти. Чим ближче до 1.0 — тим краще.",
    "help.f1_score": "F1 — баланс між точністю і повнотою. Важливий, бо переможців мало (~3–5%).",
    "help.data_drift": "Data Drift — коли нові хакатони сильно відрізняються від тих, на яких модель вчилась. Система запропонує перенавчання.",
    "help.shap": "SHAP пояснює, які саме фактори підвищують або знижують шанси кожної ідеї.",
    "help.win_probability": "Цей відсоток — не гарантія. Це оцінка моделі на основі 10 000 минулих проектів.",
    "help.circuit_breaker": "Запобіжник захищає від нескінченних запитів, коли AI-сервіс падає.",
    
    # === TOASTS ===
    "toast.analysis_started": "Аналіз запущено",
    "toast.analysis_done": "Готово! 3 ідеї згенеровано",
    "toast.spec_ready": "TechSpec готовий до експорту",
    "toast.training_started": "Збір даних розпочато",
    "toast.training_done": "Модель перенавчено. Точність: {accuracy}%",
    "toast.backup_done": "Резервна копія створена",
    "toast.drift_detected": "Виявлено зміну в даних. Рекомендуємо перенавчання.",
    "toast.copy_success": "Скопійовано в буфер обміну",
    "toast.offline": "Працюємо офлайн — AI-генерація недоступна, ML-прогнози працюють",
    
    # === CONFIRMATIONS (деструктивні дії) ===
    "confirm.reset_db.title": "Очистити базу даних?",
    "confirm.reset_db.body": "Це видалить усі зібрані дані про хакатони та проекти. ML-модель доведеться навчати з нуля.",
    "confirm.reset_db.yes": "Так, очистити",
    "confirm.reset_db.no": "Скасувати",
    
    "confirm.stop_training.title": "Зупинити навчання?",
    "confirm.stop_training.body": "Прогрес буде збережено. Ви зможете продовжити пізніше.",
    
    # === CTA Library ===
    "cta.confirm": "Так, підтверджую",
}
