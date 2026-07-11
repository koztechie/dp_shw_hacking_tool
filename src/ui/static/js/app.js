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

/**
 * DP_SHW Toast System - Антикрихкі сповіщення
 */
class Toast {
    static container = null;
    
    static init() {
        if (!this.container) {
            // Reuse existing toast container from base.html to avoid duplicates
            this.container = document.getElementById('toast-container')
                || document.querySelector('.toast-container');
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'toast-container';
                this.container.className = 'toast-container';
                this.container.setAttribute('aria-live', 'polite');
                this.container.setAttribute('aria-atomic', 'true');
                document.body.appendChild(this.container);
            }
        }
    }
    
    static show({ type = 'info', title, message, duration = 5000 }) {
        this.init();
        
        const icons = {
            success: '✅',
            warning: '⚠️',
            error: '❌',
            info: 'ℹ️'
        };
        
        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;
        toast.innerHTML = `
            <div class="toast__icon">${icons[type]}</div>
            <div class="toast__content">
                <div class="toast__title">${title}</div>
                ${message ? `<div class="toast__message">${message}</div>` : ''}
            </div>
            <button class="toast__close" aria-label="Закрити">×</button>
            <div class="toast__progress" style="animation-duration: ${duration}ms"></div>
        `;
        
        const closeBtn = toast.querySelector('.toast__close');
        closeBtn.addEventListener('click', () => this.hide(toast));
        
        this.container.appendChild(toast);
        
        setTimeout(() => this.hide(toast), duration);
        
        return toast;
    }
    
    static hide(toast) {
        toast.style.animation = 'toastSlideIn 200ms reverse';
        setTimeout(() => toast.remove(), 200);
    }
    
    static success(title, message) { return this.show({ type: 'success', title, message }); }
    static warning(title, message) { return this.show({ type: 'warning', title, message }); }
    static error(title, message) { return this.show({ type: 'error', title, message }); }
    static info(title, message) { return this.show({ type: 'info', title, message }); }
}

window.Toast = Toast;
