(function (root, factory) {
  'use strict';
  const urlCore = typeof module === 'object' && module.exports ? require('./urls.js') : root.QuizUrlCore;
  const api = factory(urlCore);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.QuizCatalogCore = api;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', api.init);
    else api.init();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (urlCore) {
  'use strict';

  const PAGE_SIZE = 10;
  const SORTS = new Set(['date', 'difficulty', 'title']);
  const DIRECTIONS = new Set(['down', 'up']);
  const SECTIONS = new Set(['quizzes', 'english']);
  const DIFFICULTY_ORDER = Object.freeze({ low: 1, medium: 2, high: 3 });
  const DIFFICULTY_LABELS = Object.freeze({ low: 'низкая', medium: 'средняя', high: 'высокая' });
  const ruCollator = new Intl.Collator('ru', { sensitivity: 'base', numeric: true });

  function validateQuiz(quiz, source = 'неизвестный файл') {
    const errors = [];
    ['slug', 'title', 'short_description', 'intro'].forEach((field) => {
      if (typeof quiz?.[field] !== 'string' || !quiz[field].trim()) errors.push(`поле «${field}» обязательно`);
    });
    if (!Object.hasOwn(DIFFICULTY_LABELS, quiz?.difficulty)) errors.push('поле «difficulty» должно содержать low, medium или high');
    if (typeof quiz?.published !== 'boolean') errors.push('поле «published» должно быть логическим');
    if (validDateValue(quiz?.publication_date) === null) errors.push('поле «publication_date» должно содержать дату либо ISO 8601 с часовым поясом');
    if (!Array.isArray(quiz?.tags) || quiz.tags.some((tag) => typeof tag !== 'string' || !tag.trim())) errors.push('поле «tags» должно быть массивом непустых строк');
    if (!Array.isArray(quiz?.questions) || quiz.questions.length === 0) errors.push('массив «questions» не должен быть пустым');
    const ids = new Set();
    (Array.isArray(quiz?.questions) ? quiz.questions : []).forEach((item, index) => {
      const label = `вопрос ${index + 1}`;
      if (typeof item?.id !== 'string' || !item.id.trim()) errors.push(`${label}: отсутствует id`);
      else if (ids.has(item.id)) errors.push(`${label}: id «${item.id}» повторяется`);
      else ids.add(item.id);
      if (typeof item?.question !== 'string' || !item.question.trim()) errors.push(`${label}: отсутствует текст`);
      if (!Array.isArray(item?.answers) || item.answers.length < 2 || item.answers.length > 6) errors.push(`${label}: требуется от 2 до 6 ответов`);
      else {
        const answerIds = new Set();
        item.answers.forEach((answer) => {
          if (!answer || typeof answer.id !== 'string' || typeof answer.text !== 'string') errors.push(`${label}: вариант ответа заполнен некорректно`);
          else { if (answerIds.has(answer.id)) errors.push(`${label}: id ответа «${answer.id}» повторяется`); answerIds.add(answer.id); }
        });
        if (typeof item.correct_answer_id !== 'string' || !answerIds.has(item.correct_answer_id)) errors.push(`${label}: требуется один существующий правильный вариант`);
      }
      if (typeof item?.explanation !== 'string' || !item.explanation.trim()) errors.push(`${label}: объяснение обязательно`);
    });
    if (errors.length) {
      console.error(`[Quiz] Викторина «${source}» пропущена из-за ошибок данных:\n- ${errors.join('\n- ')}`);
      return false;
    }
    return true;
  }

  function validDateValue(value) {
    if (typeof value !== 'string') return null;
    const legacyDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const zonedDateTime = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$/.test(value);
    if (!legacyDate && !zonedDateTime) return null;
    const [year, month, day] = value.slice(0, 10).split('-').map(Number);
    if (month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) return null;
    const timestamp = Date.parse(legacyDate ? `${value}T00:00:00Z` : value);
    if (!Number.isFinite(timestamp)) return null;
    if (legacyDate && new Date(timestamp).toISOString().slice(0, 10) !== value) return null;
    return timestamp;
  }

  function compareDatesNewestFirst(a, b) {
    const dateA = validDateValue(a.publication_date);
    const dateB = validDateValue(b.publication_date);
    if (dateA === null && dateB !== null) return 1;
    if (dateA !== null && dateB === null) return -1;
    if (dateA !== null && dateB !== null && dateA !== dateB) return dateB - dateA;
    return 0;
  }

  function sortQuizzes(items, sort = 'date', direction = 'down') {
    return [...items].sort((a, b) => {
      if (sort === 'difficulty') {
        const difficulty = (DIFFICULTY_ORDER[a.difficulty] - DIFFICULTY_ORDER[b.difficulty]) * (direction === 'up' ? -1 : 1);
        return difficulty || compareDatesNewestFirst(a, b) || ruCollator.compare(a.title, b.title);
      }
      if (sort === 'title') {
        const title = ruCollator.compare(a.title, b.title) * (direction === 'up' ? -1 : 1);
        return title || compareDatesNewestFirst(a, b);
      }
      const dateA = validDateValue(a.publication_date);
      const dateB = validDateValue(b.publication_date);
      if (dateA === null && dateB !== null) return 1;
      if (dateA !== null && dateB === null) return -1;
      const date = dateA !== null && dateB !== null ? (dateB - dateA) * (direction === 'up' ? -1 : 1) : 0;
      return date || ruCollator.compare(a.title, b.title);
    });
  }

  function arrangeQuizzes(quizzes, activeTag, sort, direction) {
    const filtered = activeTag === 'all' ? quizzes : quizzes.filter((quiz) => quiz.tags.includes(activeTag));
    return sortQuizzes(filtered, sort, direction);
  }

  function sectionQuizzes(quizzes, section = 'quizzes') {
    return quizzes.filter((quiz) => section === 'english' ? ['vocabulary', 'english'].includes(quiz.type) : !['vocabulary', 'english'].includes(quiz.type));
  }

  function sortTooltip(sort, direction) {
    const labels = {
      date: { down: 'Сначала новые', up: 'Сначала старые' },
      difficulty: { down: 'Сначала лёгкие', up: 'Сначала сложные' },
      title: { down: 'От А до Я', up: 'От Я до А' }
    };
    return labels[sort][direction];
  }

  function countTags(quizzes, visibleTags) {
    const counts = new Map(visibleTags.map((tag) => [tag.slug, 0]));
    quizzes.forEach((quiz) => quiz.tags.forEach((slug) => {
      if (counts.has(slug)) counts.set(slug, counts.get(slug) + 1);
    }));
    return counts;
  }

  function orderTagsByCount(quizzes, visibleTags) {
    const counts = countTags(quizzes, visibleTags);
    return visibleTags
      .map((tag) => ({ ...tag, count: counts.get(tag.slug) }))
      .filter((tag) => tag.count > 0)
      .sort((a, b) => b.count - a.count || ruCollator.compare(a.name, b.name));
  }

  function paginationItems(current, total) {
    if (total <= 1) return [];
    const pages = new Set([1, total, current - 1, current, current + 1]);
    const valid = [...pages].filter((page) => page >= 1 && page <= total).sort((a, b) => a - b);
    const result = [];
    valid.forEach((page, index) => {
      if (index && page - valid[index - 1] > 1) result.push('ellipsis');
      result.push(page);
    });
    return result;
  }

  function getStateFromUrl(search, visibleTagSlugs, totalPages = Infinity) {
    const params = new URLSearchParams(search);
    const requestedSection = params.get('section');
    const section = SECTIONS.has(requestedSection) ? requestedSection : 'quizzes';
    const requestedTag = params.get('tag');
    const tag = requestedTag && visibleTagSlugs.has(requestedTag) ? requestedTag : 'all';
    const requestedSort = params.get('sort');
    const sort = SORTS.has(requestedSort) ? requestedSort : 'date';
    const requestedDirection = params.get('direction');
    const direction = DIRECTIONS.has(requestedDirection) ? requestedDirection : 'down';
    const requestedPage = Number.parseInt(params.get('page') || '1', 10);
    const page = Math.min(Math.max(Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1, 1), Math.max(totalPages, 1));
    return { section, tag, sort, direction, page };
  }

  function buildUrl(url, state) {
    const next = new URL(url);
    if (state.section === 'english') next.searchParams.set('section', 'english');
    else next.searchParams.delete('section');
    if (state.tag === 'all') next.searchParams.delete('tag');
    else next.searchParams.set('tag', state.tag);
    next.searchParams.set('sort', state.sort);
    next.searchParams.set('direction', state.direction);
    next.searchParams.set('page', String(state.page));
    return `${next.pathname}${next.search}${next.hash}`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[character]));
  }

  function questionWord(count) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    return mod10 === 1 && mod100 !== 11 ? 'вопрос' : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'вопроса' : 'вопросов';
  }
  function vocabularyWord(count) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    return mod10 === 1 && mod100 !== 11 ? 'слово' : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'слова' : 'слов';
  }
  function volumeLabel(quiz) { return quiz.type === 'vocabulary' ? `${quiz.question_count} ${vocabularyWord(quiz.question_count)}` : `${quiz.question_count} ${questionWord(quiz.question_count)}`; }

  async function fetchJson(path) {
    const url = new URL(path, location.href);
    url.searchParams.set('v', String(Date.now()));
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function init() {
    const list = document.getElementById('quiz-list');
    const tagList = document.getElementById('tag-list');
    const sortControl = document.getElementById('sort-control');
    const sortCriterion = document.getElementById('sort-criterion');
    const sortDirection = document.querySelector('[data-sort-direction]');
    const pagination = document.getElementById('pagination');
    const status = document.getElementById('catalog-status');
    const catalogStart = document.getElementById('catalog-start');
    const sectionTabs = [...document.querySelectorAll('[data-section]')];
    const catalogTools = document.getElementById('catalog-tools');
    if (!list || !tagList || !sortControl || !sortCriterion || !sortDirection || !pagination || !sectionTabs.length) return;

    let quizzes = [];
    let tags = new Map();
    let visibleTags = [];
    let state = { section: 'quizzes', tag: 'all', sort: 'date', direction: 'down', page: 1 };

    function currentQuizzes(currentState = state) {
      return sectionQuizzes(quizzes, currentState.section);
    }

    function currentTags(currentState = state) {
      return orderTagsByCount(currentQuizzes(currentState), visibleTags);
    }

    function scrollToCatalog() {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      catalogStart?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    }

    function totalPagesFor(currentState) {
      return Math.max(1, Math.ceil(arrangeQuizzes(currentQuizzes(currentState), currentState.tag, currentState.sort, currentState.direction).length / PAGE_SIZE));
    }

    function readAndNormalizeUrl() {
      const requestedSection = getStateFromUrl(location.search, new Set()).section;
      const slugs = new Set(currentTags({ ...state, section: requestedSection }).map((tag) => tag.slug));
      let next = getStateFromUrl(location.search, slugs);
      next = getStateFromUrl(location.search, slugs, totalPagesFor(next));
      state = next;
      history.replaceState(null, '', buildUrl(location.href, state));
    }

    function writeUrl(mode = 'push') {
      history[mode === 'replace' ? 'replaceState' : 'pushState'](null, '', buildUrl(location.href, state));
    }

    function renderTags() {
      const scopedQuizzes = currentQuizzes();
      const items = [{ slug: 'all', name: 'Все', count: scopedQuizzes.length }, ...currentTags()];
      tagList.innerHTML = items.map((tag) => `<button class="catalog-tag${state.tag === tag.slug ? ' is-active' : ''}" type="button" data-tag="${escapeHtml(tag.slug)}" aria-pressed="${state.tag === tag.slug}"><span>${escapeHtml(tag.name)}</span><small>${tag.count}</small></button>`).join('');
    }

    function renderSections() {
      sectionTabs.forEach((tab) => {
        const selected = tab.dataset.section === state.section;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
      });
      const activeTab = sectionTabs.find((tab) => tab.dataset.section === state.section);
      if (activeTab) catalogTools?.setAttribute('aria-labelledby', activeTab.id);
    }

    function renderSort() {
      sortCriterion.value = state.sort;
      sortDirection.textContent = state.direction === 'down' ? '↓' : '↑';
      const tooltip = sortTooltip(state.sort, state.direction);
      sortDirection.title = tooltip;
      sortDirection.setAttribute('aria-label', tooltip);
    }

    function visibleCardTags(quiz) {
      return quiz.tags.filter((slug) => tags.has(slug) && tags.get(slug).published);
    }

    function cardTemplate(quiz) {
      const count = quiz.question_count;
      const title = `${quiz.title} (${volumeLabel(quiz)})`;
      const cover = quiz.cover
        ? `<img src="${escapeHtml(quiz.cover)}" alt="Обложка викторины «${escapeHtml(quiz.title)}»" loading="lazy">`
        : '<div class="cover-placeholder" aria-hidden="true"><span>?</span><small>Quiz</small></div>';
      const cardTags = visibleCardTags(quiz).map((slug) => `<button class="tag" type="button" data-card-tag="${escapeHtml(slug)}">${escapeHtml(tags.get(slug).name)}</button>`).join('');
      const quizHref = urlCore.quizPath(quiz.slug, location.href);
      return `<article class="quiz-card"><a class="quiz-card-link" href="${escapeHtml(quizHref)}" aria-label="Открыть викторину «${escapeHtml(quiz.title)}»"></a><div class="quiz-cover">${cover}</div><div class="quiz-card-body"><div><h3>${escapeHtml(title)}</h3><p class="quiz-card-description">${escapeHtml(quiz.short_description)}</p></div><div class="quiz-card-meta"><span class="quiz-card-difficulty">Сложность: ${DIFFICULTY_LABELS[quiz.difficulty]}</span><div class="quiz-tags" aria-label="Теги викторины">${cardTags}</div></div></div></article>`;
    }

    function renderPagination(totalPages) {
      if (totalPages <= 1) { pagination.hidden = true; pagination.innerHTML = ''; return; }
      pagination.hidden = false;
      const middle = paginationItems(state.page, totalPages).map((item) => item === 'ellipsis'
        ? '<span class="pagination-ellipsis" aria-hidden="true">…</span>'
        : `<button type="button" data-page="${item}"${item === state.page ? ' class="is-active" aria-current="page" disabled' : ''} aria-label="Страница ${item}">${item}</button>`).join('');
      pagination.innerHTML = `<button type="button" data-page="${state.page - 1}" ${state.page === 1 ? 'disabled' : ''} aria-label="Предыдущая страница">&lt;&lt; <span>НАЗАД</span></button>${middle}<button type="button" data-page="${state.page + 1}" ${state.page === totalPages ? 'disabled' : ''} aria-label="Следующая страница"><span>ВПЕРЕД</span> &gt;&gt;</button>`;
    }

    function render() {
      const scopedQuizzes = currentQuizzes();
      const ordered = arrangeQuizzes(scopedQuizzes, state.tag, state.sort, state.direction);
      const totalPages = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE));
      state.page = Math.min(Math.max(state.page, 1), totalPages);
      const start = (state.page - 1) * PAGE_SIZE;
      const pageItems = ordered.slice(start, start + PAGE_SIZE);
      renderTags();
      renderSections();
      renderSort();
      if (!scopedQuizzes.length) list.innerHTML = '<div class="empty-state"><p>Опубликованных викторин пока нет.</p></div>';
      else list.innerHTML = pageItems.map(cardTemplate).join('');
      renderPagination(totalPages);
      list.setAttribute('aria-busy', 'false');
    }

    function selectSection(section, shouldFocus = false) {
      if (!SECTIONS.has(section)) return;
      const changed = section !== state.section || state.tag !== 'all' || state.page !== 1;
      state = { ...state, section, tag: 'all', page: 1 };
      if (changed) { writeUrl(); render(); }
      if (shouldFocus) sectionTabs.find((tab) => tab.dataset.section === section)?.focus();
    }

    sectionTabs.forEach((tab) => tab.addEventListener('click', () => selectSection(tab.dataset.section)));
    catalogStart.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const activeIndex = sectionTabs.findIndex((tab) => tab.dataset.section === state.section);
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? sectionTabs.length - 1 : (activeIndex + (event.key === 'ArrowRight' ? 1 : -1) + sectionTabs.length) % sectionTabs.length;
      selectSection(sectionTabs[nextIndex].dataset.section, true);
    });

    function selectTag(slug, shouldScroll, resetActivePage = false) {
      if (slug === state.tag && !resetActivePage) return;
      const stateChanged = slug !== state.tag || state.page !== 1;
      state = { ...state, tag: slug, page: 1 };
      if (stateChanged) { writeUrl(); render(); }
      if (shouldScroll) scrollToCatalog();
    }

    tagList.addEventListener('click', (event) => {
      const button = event.target.closest('[data-tag]');
      if (!button) return;
      selectTag(button.dataset.tag, false);
    });
    sortCriterion.addEventListener('change', () => {
      state = { ...state, sort: sortCriterion.value, direction: 'down', page: 1 };
      writeUrl(); render(); scrollToCatalog();
    });
    sortDirection.addEventListener('click', () => {
      state = { ...state, direction: state.direction === 'down' ? 'up' : 'down', page: 1 };
      writeUrl(); render(); scrollToCatalog();
    });
    list.addEventListener('click', (event) => {
      const button = event.target.closest('[data-card-tag]');
      if (!button) return;
      event.preventDefault(); event.stopPropagation(); selectTag(button.dataset.cardTag, true, true);
    });
    pagination.addEventListener('click', (event) => {
      const button = event.target.closest('[data-page]');
      if (!button || button.disabled) return;
      const page = Number(button.dataset.page);
      if (page === state.page) return;
      state = { ...state, page }; writeUrl(); render(); scrollToCatalog();
    });
    window.addEventListener('popstate', () => { readAndNormalizeUrl(); render(); });

    (async function load() {
      try {
        const catalog = await fetchJson('data/catalog.json');
        if (!Array.isArray(catalog?.tags) || !Array.isArray(catalog?.quizzes)) throw new Error('Некорректный формат каталога');
        visibleTags = catalog.tags.map((tag) => ({ ...tag, published: true }));
        visibleTags.forEach((tag) => tags.set(tag.slug, tag));
        quizzes = catalog.quizzes;
        readAndNormalizeUrl(); render();
      } catch (error) {
        console.error('[Quiz] Каталог не удалось загрузить.', error);
        list.innerHTML = '<div class="error-state" role="alert"><strong>Не удалось загрузить каталог.</strong><p>Попробуйте обновить страницу немного позже.</p></div>';
        tagList.innerHTML = '<span class="tag is-muted">Теги недоступны</span>';
        pagination.hidden = true; list.setAttribute('aria-busy', 'false');
      }
    })();
  }

  return { PAGE_SIZE, DIFFICULTY_LABELS, DIFFICULTY_ORDER, validateQuiz, validDateValue, sortQuizzes, arrangeQuizzes, sectionQuizzes, sortTooltip, countTags, orderTagsByCount, paginationItems, getStateFromUrl, buildUrl, questionWord, vocabularyWord, volumeLabel, quizPath: urlCore.quizPath, init };
});
