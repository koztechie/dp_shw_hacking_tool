/**
 * DP_SHW_Hacking_Tool - Global JavaScript
 * 
 * УВАГА: Специфічні функції для кожної сторінки (analyzeHackathon, generateTechSpec, pollTraining)
 * безпечно інкапсульовані у відповідних HTML-шаблонах (analyze.html, ideas.html, training.html).
 * Це запобігає помилкам Null Reference Error під час пошуку DOM-елементів на інших сторінках.
 */

document.addEventListener("DOMContentLoaded", () => {
    console.log("⚡ DP_SHW Global JS успішно завантажено.");
    
    // АНТИКРИХКІСТЬ: Мобільне меню
    const navToggle = document.querySelector('.nav-toggle');
    const navLinks = document.querySelector('.nav-links');
    
    if (navToggle && navLinks) {
        navToggle.addEventListener('click', () => {
            const isOpen = navLinks.classList.toggle('open');
            navToggle.setAttribute('aria-expanded', isOpen);
            navToggle.textContent = isOpen ? '✕' : '☰';
        });
    }
});
