(function () {
  'use strict';
  const config = window.SiteConfig?.publicUrl || new URL('./', location.href).href;
  const basePath = new URL(config).pathname;
  const relative = location.pathname.startsWith(basePath) ? location.pathname.slice(basePath.length) : location.pathname.replace(/^\//, '');
  if (!relative.startsWith('en/')) return;
  document.documentElement.lang = 'en';
  document.title = 'Page not found — Horse Quizzes';
  const values = {
    '.skip-link': 'Skip to main content', '.eyebrow': 'Error 404', '#error-title': 'Page not found',
    '.error-intro .lead': 'This page does not exist or its address is incorrect. Return to the English home page or browse the quiz catalog.',
    '.error-actions a:first-child': 'Home', '.error-actions a:last-child': 'Browse quizzes', '.site-footer a': 'About the project'
  };
  Object.entries(values).forEach(([selector, value]) => { const element = document.querySelector(selector); if (element) element.textContent = value; });
  const brand = document.querySelector('.brand');
  if (brand) {
    brand.setAttribute('href', `${basePath}en/`);
    brand.setAttribute('aria-label', 'Horse Quizzes — Home');
  }
  const navigation = document.querySelector('.site-nav');
  if (navigation) navigation.setAttribute('aria-label', 'Main navigation');
  const navigationLinks = document.querySelectorAll('.site-nav a');
  const navigationValues = [
    ['Home', `${basePath}en/`],
    ['Quizzes', `${basePath}en/quizzes.html`],
    ['Contacts', `${basePath}en/contacts.html`]
  ];
  navigationLinks.forEach((link, index) => {
    const localized = navigationValues[index];
    if (!localized) return;
    link.textContent = localized[0];
    link.setAttribute('href', localized[1]);
  });
  document.querySelector('.error-actions a:first-child')?.setAttribute('href', `${basePath}en/`);
  document.querySelector('.error-actions a:last-child')?.setAttribute('href', `${basePath}en/quizzes.html`);
  document.querySelector('.site-footer a')?.setAttribute('href', `${basePath}en/contacts.html`);
  const toggle = document.querySelector('.menu-toggle');
  if (toggle) toggle.setAttribute('aria-label', 'Open menu');
  document.querySelector('.language-switch')?.setAttribute('aria-label', 'Language');
  const switchLinks = document.querySelectorAll('.language-switch a');
  switchLinks[0]?.removeAttribute('aria-current'); switchLinks[1]?.setAttribute('aria-current', 'page');
})();
