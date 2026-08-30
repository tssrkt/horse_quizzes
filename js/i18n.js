(function (root) {
  'use strict';
  const en = document.documentElement.lang === 'en';
  const dictionary = Object.freeze({
    'Открыть меню': 'Open menu', 'Закрыть меню': 'Close menu', 'Все': 'All',
    'Сначала новые': 'Newest first', 'Сначала старые': 'Oldest first', 'Сначала лёгкие': 'Easy first',
    'Сначала сложные': 'Hard first', 'От А до Я': 'A to Z', 'От Я до А': 'Z to A',
    'низкая': 'Easy', 'средняя': 'Medium', 'высокая': 'Hard', 'НАЗАД': 'BACK', 'ВПЕРЕД': 'NEXT',
    'Опубликованных викторин пока нет.': 'No published quizzes yet.', 'К списку викторин': 'Back to quizzes',
    'Начать викторину': 'Start quiz', 'Продолжить': 'Continue', 'Начать заново': 'Start over',
    'Верно!': 'Correct!', 'Неверно': 'Incorrect', 'Следующий вопрос': 'Next question',
    'Показать результат': 'Show result', 'Вопрос': 'Question', 'Правильный ответ.': 'Correct answer.',
    'Неправильный ответ.': 'Incorrect answer.', 'Варианты ответа': 'Answer choices',
    'Викторина завершена': 'Quiz complete', 'Следующая викторина': 'Next quiz',
    'Поделиться результатом': 'Share result', 'Скопировать результат': 'Copy result',
    'Пройти еще раз': 'Try again', 'Результат скопирован.': 'Result copied.',
    'Не удалось скопировать результат.': 'Could not copy the result.', 'Источник изображения': 'Image source',
    'Загружаем викторину…': 'Loading quiz…', 'Викторина не найдена.': 'Quiz not found.',
    'Эту викторину сейчас невозможно открыть.': 'This quiz cannot be opened right now.',
    'Эта викторина пока не опубликована.': 'This quiz has not been published yet.',
    'Не удалось загрузить викторину. Попробуйте позже.': 'Could not load the quiz. Please try again later.'
  });
  function text(ru, english) { return en ? (english || dictionary[ru] || ru) : ru; }
  function translateNode(node) {
    if (!en || node.nodeType !== Node.TEXT_NODE || !node.parentElement || ['SCRIPT', 'STYLE'].includes(node.parentElement.tagName)) return;
    const raw = node.nodeValue; const trimmed = raw.trim();
    if (dictionary[trimmed]) node.nodeValue = raw.replace(trimmed, dictionary[trimmed]);
  }
  function translateTree(rootNode) {
    if (!en) return;
    const walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT); let node;
    while ((node = walker.nextNode())) translateNode(node);
  }
  root.SiteI18n = Object.freeze({ locale: en ? 'en' : 'ru', text, translateTree });
  if (en) {
    const start = () => {
      translateTree(document.body);
      new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) translateNode(node);
        else if (node.nodeType === Node.ELEMENT_NODE) translateTree(node);
      }))).observe(document.body, { childList: true, subtree: true });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
