/**
 * DP_SHW Loading Copy System
 * Тексти змінюються залежно від етапу і часу очікування
 */
const LoadingCopy = {
    stages: {
        scraping: {
            title: "Зчитую сторінку хакатону…",
            detail: "Обходжу захист Cloudflare, витягую основні дані.",
            eta: "5–10 секунд"
        },
        constraints: {
            title: "Аналізую правила…",
            detail: "Шукаю обмеження: розмір команди, дозволені технології, IP.",
            eta: "5–8 секунд"
        },
        "ai-analysis": {
            title: "Збираю контекст…",
            detail: "Дивлюсь, хто спонсори, хто судді, що вони цінують.",
            eta: "10–15 секунд"
        },
        "idea-generation": {
            title: "Генерую ідеї в 3 етапи…",
            detail: "1) Brainstorm · 2) Критика · 3) Фінальний відбір",
            eta: "15–25 секунд"
        },
        "ml-scoring": {
            title: "Оцінюю шанси ML-моделлю…",
            detail: "Порівнюю з 10 000 минулих проектів.",
            eta: "3–5 секунд"
        }
    },
    
    // Фрази для тривалого очікування (> 60 сек)
    longWaitMessages: [
        "Це триває довше, ніж зазвичай. Система не зависла — працює.",
        "Ваш AMD A4 робить усе можливе. Дякуємо за терпіння.",
        "Можете відкрити іншу вкладку — процес іде у фоні.",
        "Якщо за 2 хвилини нічого не зміниться — спробуйте ще раз."
    ],
    
    getCurrentMessage(stage, elapsedSeconds) {
        const base = this.stages[stage];
        if (!base) return { title: "Працюю…", detail: "" };
        
        if (elapsedSeconds > 60) {
            const idx = Math.floor((elapsedSeconds - 60) / 15) % this.longWaitMessages.length;
            return {
                ...base,
                detail: this.longWaitMessages[idx]
            };
        }
        return base;
    }
};

window.LoadingCopy = LoadingCopy;
