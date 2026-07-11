/**
 * DP_SHW Confirm Modal System
 * Брендовані модалки для деструктивних дій з поясненням наслідків
 */
const ConfirmModal = {
    show(options) {
        // Find or clone the template
        const template = document.getElementById('confirm-modal-template');
        if (!template) {
            console.error('Confirm modal template not found!');
            // Fallback to native confirm if template is missing
            if (confirm(options.title + '\n\n' + options.body)) {
                if (options.onConfirm) options.onConfirm();
            }
            return;
        }

        const clone = template.content.cloneNode(true);
        const overlay = clone.querySelector('.modal-overlay');
        
        // Populate content
        clone.querySelector('.modal__title').textContent = options.title || 'Увага';
        clone.querySelector('.modal__body').textContent = options.body || '';
        
        const consequencesList = clone.querySelector('.modal__consequences-list');
        if (options.consequences && options.consequences.length > 0) {
            options.consequences.forEach(c => {
                const li = document.createElement('li');
                li.textContent = c;
                consequencesList.appendChild(li);
            });
        } else {
            clone.querySelector('.modal__consequences').style.display = 'none';
        }
        
        const btnCancel = clone.querySelector('[data-action="cancel"]');
        const btnConfirm = clone.querySelector('[data-action="confirm"]');
        
        btnCancel.textContent = options.cancelText || 'Скасувати';
        btnConfirm.textContent = options.confirmText || 'Так, підтверджую';
        
        // Setup handlers
        const cleanup = () => {
            document.body.removeChild(overlay);
        };
        
        btnCancel.addEventListener('click', () => {
            cleanup();
            if (options.onCancel) options.onCancel();
        });
        
        btnConfirm.addEventListener('click', () => {
            cleanup();
            if (options.onConfirm) options.onConfirm();
        });
        
        // Append and show
        document.body.appendChild(overlay);
    }
};

window.ConfirmModal = ConfirmModal;
