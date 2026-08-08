(function () {
  'use strict';
  const toggle = document.querySelector('.menu-toggle');
  const menu = document.querySelector('.site-nav');
  const closeMenu = (restoreFocus) => {
    if (!toggle || !menu) return;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Открыть меню');
    menu.classList.remove('is-open');
    if (restoreFocus) toggle.focus();
  };
  if (toggle && menu) {
    toggle.addEventListener('click', () => {
      const isOpen = toggle.getAttribute('aria-expanded') === 'true';
      if (isOpen) closeMenu(false);
      else {
        toggle.setAttribute('aria-expanded', 'true');
        toggle.setAttribute('aria-label', 'Закрыть меню');
        menu.classList.add('is-open');
        menu.querySelector('a')?.focus();
      }
    });
    menu.addEventListener('click', (event) => { if (event.target.closest('a')) closeMenu(false); });
    document.addEventListener('click', (event) => { if (!menu.contains(event.target) && !toggle.contains(event.target)) closeMenu(false); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && menu.classList.contains('is-open')) closeMenu(true); });
    window.addEventListener('resize', () => { if (window.matchMedia('(min-width: 769px)').matches) closeMenu(false); });
  }
  document.querySelectorAll('[data-current-year]').forEach((item) => { item.textContent = new Date().getFullYear(); });
  const copyDonate = document.querySelector('[data-copy]');
  if (copyDonate) {
    const activateCopy = async () => {
      const value = copyDonate.dataset.copy?.trim();
      const status = document.querySelector('.copy-message');
      if (!value || !status) return;

      const showStatus = (message) => {
        status.textContent = message;
        window.setTimeout(() => { status.textContent = ''; }, 2200);
      };

      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
        else {
          const input = document.createElement('textarea');
          input.value = value;
          input.setAttribute('readonly', '');
          input.style.position = 'fixed';
          input.style.left = '-9999px';
          input.style.top = '-9999px';
          document.body.appendChild(input);
          input.select();
          const copied = document.execCommand('copy');
          input.remove();
          if (!copied) throw new Error('Команда копирования недоступна');
        }

        copyDonate.title = 'Скопировано!';
        showStatus('Номер ЮMoney скопирован.');
        window.setTimeout(() => { copyDonate.title = 'Нажмите, чтобы скопировать'; }, 2200);
      } catch (error) {
        showStatus('Не удалось скопировать автоматически. Выделите номер вручную.');
        console.warn('[Quiz] Ошибка копирования:', error);
      }
    };

    copyDonate.addEventListener('click', activateCopy);
    copyDonate.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activateCopy();
      }
    });
  }
})();
