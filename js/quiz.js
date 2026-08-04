(function (root, factory) {
  'use strict';
  const catalogCore = typeof module === 'object' && module.exports ? require('./quizzes.js') : root.QuizCatalogCore;
  const urlCore = typeof module === 'object' && module.exports ? require('./urls.js') : root.QuizUrlCore;
  const core = factory(catalogCore, urlCore);
  if (typeof module === 'object' && module.exports) module.exports = core;
  else {
    root.QuizEngineCore = core;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init(core));
    else init(core);
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function (catalogCore, urlCore) {
  'use strict';
  const STATE_VERSION = 3;
  const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

  function canOpenQuiz(data, previewMode) { return data?.published === true || (data?.published === false && previewMode === true); }
  function validateQuiz(data) {
    if (!data || !SLUG_PATTERN.test(data.slug || '') || !/^[0-9a-f]{64}$/.test(data.content_version || '') || typeof data.title !== 'string' || typeof data.intro !== 'string' || typeof data.published !== 'boolean') return false;
    if (data.questionImagesAlt != null && typeof data.questionImagesAlt !== 'string') return false;
    if (data.next_quiz != null && data.next_quiz !== '' && !SLUG_PATTERN.test(data.next_quiz)) return false;
    if (data.type === 'vocabulary') return Array.isArray(data.vocabulary) && data.vocabulary.length > 0 && data.vocabulary.every((word) => word && typeof word.english === 'string' && word.english && typeof word.russian === 'string' && word.russian && typeof word.category === 'string');
    if (!Array.isArray(data.questions) || !data.questions.length) return false;
    const questionIds = new Set();
    return data.questions.every((question) => {
      if (!question || !SLUG_PATTERN.test(question.id || '') || questionIds.has(question.id) || typeof question.question !== 'string' || typeof question.explanation !== 'string' || !Array.isArray(question.answers) || question.answers.length < 2 || question.answers.length > 6) return false;
      questionIds.add(question.id);
      const answerIds = new Set();
      const answersValid = question.answers.every((answer) => {
        if (!answer || !SLUG_PATTERN.test(answer.id || '') || answerIds.has(answer.id) || typeof answer.text !== 'string') return false;
        answerIds.add(answer.id); return true;
      });
      return answersValid && typeof question.correct_answer_id === 'string' && answerIds.has(question.correct_answer_id);
    });
  }
  function structureSignature(quiz) {
    const progressContent = quiz.questions.map((question) => ({
      id: question.id,
      question: question.question,
      image: question.image || '',
      explanation: question.explanation,
      correct_answer_id: question.correct_answer_id,
      answers: question.answers.map((answer) => ({ id: answer.id, text: answer.text }))
    }));
    return `${quiz.content_version || ''}|${JSON.stringify(progressContent)}`;
  }
  function versionedUrl(path, version) {
    const url = new URL(path, 'https://quiz.invalid/');
    url.searchParams.set('v', version || String(Date.now()));
    return `${url.pathname.replace(/^\//, '')}${url.search}${url.hash}`;
  }
  function cloneValue(value) {
    if (Array.isArray(value)) return value.map(cloneValue);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
    return value;
  }
  function vocabularyQuestions(sourceQuiz) {
    const groups = new Map();
    sourceQuiz.vocabulary.forEach((word, index) => {
      const entry = { ...word, index };
      if (!groups.has(word.category)) groups.set(word.category, []);
      groups.get(word.category).push(entry);
    });
    return sourceQuiz.vocabulary.map((word, index) => ({
      id: `question-${String(index + 1).padStart(2, '0')}`, question: word.english,
      explanation: word.russian, vocabulary: true,
      correct_answer_id: `word-${String(index + 1).padStart(2, '0')}`,
      answers: groups.get(word.category).map((choice) => ({ id: `word-${String(choice.index + 1).padStart(2, '0')}`, text: choice.russian }))
    }));
  }
  function fisherYates(items, random = Math.random) {
    const shuffled = items.slice();
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(random() * (index + 1));
      [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
    }
    return shuffled;
  }
  function createAttemptQuiz(sourceQuiz, shuffle = false, random = Math.random) {
    const attempt = cloneValue(sourceQuiz);
    if (attempt.type === 'vocabulary') attempt.questions = vocabularyQuestions(attempt);
    attempt.questions = attempt.questions.map((question) => ({
      ...question,
      answers: (() => {
        let answers = question.answers;
        if (attempt.type === 'vocabulary' && shuffle && answers.length > 6) {
          const correct = answers.find((answer) => answer.id === question.correct_answer_id);
          answers = [correct, ...fisherYates(answers.filter((answer) => answer.id !== question.correct_answer_id && answer.text !== correct.text), random).slice(0, 5)];
        }
        return shuffle ? fisherYates(answers, random) : answers;
      })()
    }));
    if (shuffle || attempt.type === 'vocabulary') attempt.questions = fisherYates(attempt.questions, random);
    return attempt;
  }
  function restoreAttemptOrder(sourceQuiz, saved) {
    const attempt = createAttemptQuiz(sourceQuiz, sourceQuiz.type === 'vocabulary' && (!saved || !Array.isArray(saved.question_ids)));
    if (!saved || !Array.isArray(saved.question_ids) || !saved.answer_ids) return attempt;
    const questions = new Map(attempt.questions.map((question) => [question.id, question]));
    if (saved.question_ids.length !== questions.size) return attempt;
    const ordered = saved.question_ids.map((id) => questions.get(id));
    if (ordered.some((question) => !question)) return attempt;
    for (const question of ordered) {
      const ids = saved.answer_ids[question.id];
      const answers = new Map(question.answers.map((answer) => [answer.id, answer]));
      if (!Array.isArray(ids) || (sourceQuiz.type !== 'vocabulary' && ids.length !== answers.size)) return attempt;
      const orderedAnswers = ids.map((id) => answers.get(id));
      if (orderedAnswers.some((answer) => !answer)) return attempt;
      question.answers = orderedAnswers;
    }
    attempt.questions = ordered;
    return attempt;
  }
  function freshState(quiz, now = new Date().toISOString()) {
    return { version: STATE_VERSION, signature: structureSignature(quiz), question_ids: quiz.questions.map((question) => question.id), answer_ids: Object.fromEntries(quiz.questions.map((question) => [question.id, question.answers.map((answer) => answer.id)])), current_index: 0, answers: {}, correct_count: 0, saved_at: now, completed: false };
  }
  function restoreState(raw, quiz, now) {
    const fresh = freshState(quiz, now);
    if (!raw) return fresh;
    let saved;
    try { saved = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return fresh; }
    if (!saved || saved.version !== STATE_VERSION || saved.signature !== fresh.signature || JSON.stringify(saved.question_ids) !== JSON.stringify(fresh.question_ids) || !Number.isInteger(saved.current_index) || saved.current_index < 0 || saved.current_index > quiz.questions.length || !saved.answers || typeof saved.answers !== 'object' || !Number.isInteger(saved.correct_count) || typeof saved.saved_at !== 'string' || typeof saved.completed !== 'boolean') return fresh;
    const verified = {};
    let correctCount = 0;
    for (const [questionId, record] of Object.entries(saved.answers)) {
      const question = quiz.questions.find((item) => item.id === questionId);
      const answer = question?.answers.find((item) => item.id === record?.answer_id);
      const correct = answer?.id === question?.correct_answer_id;
      if (!question || !answer || typeof record.correct !== 'boolean' || record.correct !== correct) return fresh;
      verified[questionId] = { answer_id: answer.id, correct };
      if (correct) correctCount += 1;
    }
    if (correctCount !== saved.correct_count) return fresh;
    for (let index = 0; index < quiz.questions.length; index += 1) {
      const answered = Boolean(verified[quiz.questions[index].id]);
      if (index < saved.current_index && !answered) return fresh;
      if (index > saved.current_index && answered) return fresh;
    }
    if (saved.completed !== (saved.current_index === quiz.questions.length) || (saved.completed && Object.keys(verified).length !== quiz.questions.length)) return fresh;
    return { ...saved, answers: verified };
  }
  function answerQuestion(state, quiz, answerId, now = new Date().toISOString()) {
    if (state.completed) return { state, accepted: false, correct: false };
    const question = quiz.questions[state.current_index];
    if (!question || state.answers[question.id]) return { state, accepted: false, correct: false };
    const answer = question.answers.find((item) => item.id === answerId);
    if (!answer) return { state, accepted: false, correct: false };
    const correct = answer.id === question.correct_answer_id;
    const next = { ...state, answers: { ...state.answers, [question.id]: { answer_id: answer.id, correct } }, correct_count: state.correct_count + (correct ? 1 : 0), saved_at: now };
    return { state: next, accepted: true, correct };
  }
  function advance(state, quiz, now = new Date().toISOString()) {
    if (state.completed) return { state, advanced: false };
    const question = quiz.questions[state.current_index];
    if (!question || !state.answers[question.id]) return { state, advanced: false };
    const nextIndex = state.current_index + 1;
    return { state: { ...state, current_index: Math.min(nextIndex, quiz.questions.length), completed: nextIndex >= quiz.questions.length, saved_at: now }, advanced: true };
  }
  function resultPercent(correct, total) { return total > 0 ? Math.round(correct / total * 100) : 0; }
  function resultRecommendation(percent) {
    if (percent < 50) return 'Что ж, некоторые вопросы оказались непростыми — и это отличный повод узнать больше! Если желаете разобраться в теме глубже, откройте сборник статей о лошадках, а затем попробуйте пройти викторину еще раз. Наверняка после этого результат вас приятно удивит.';
    if (percent < 75) return 'Неплохой результат! Вы уже многое знаете о лошадках, но некоторые вопросы все же оказались непростыми. Если желаете разобраться в теме глубже, откройте сборник статей, а затем попробуйте пройти викторину повторно. Наверняка после этого результат окажется еще лучше.';
    if (percent < 100) return 'Хороший результат! Вы разбираетесь в теме и уже совсем близки к безупречности. В сборнике статей о лошадках можно найти еще больше интересных фактов, которые помогут заполнить оставшиеся пробелы и, возможно, в следующий раз ответить правильно на все вопросы.';
    return 'Вы правильно ответили на все вопросы и прекрасно разбираетесь в данной теме. Вас не так-то просто запутать! А в сборнике статей о лошадках наверняка найдется еще много интересного.';
  }
  function resultMessage(percent) {
    if (percent >= 90) return 'Отличный результат!';
    return '';
  }
  function formatQuestionCount(count, type = 'quiz') { return type === 'vocabulary' ? `${count} слов` : `${count} ${catalogCore.questionWord(count)}`; }
  function coverAlt(quiz) { return `Обложка викторины «${String(quiz.title).trim()}»`; }
  function questionImageAlt(quiz) { return String(quiz.questionImagesAlt || '').trim() || 'Фотография лошади к вопросу'; }
  function shareText(quiz, correct, total, quizUrl) { const percent = resultPercent(correct, total); const title = String(quiz.title).replace(/\s+/g, ' ').trim(); return `Мой результат — ${correct} из ${total} (${percent}%) в викторине «${title}». А какой у вас? Проверьте: ${quizUrl}`; }
  function directQuizUrl(currentUrl, slug) { const url = new URL(currentUrl); url.search = ''; url.hash = ''; url.pathname = url.pathname.replace(/[^/]*$/, 'quiz.html'); url.searchParams.set('quiz', slug); return url.href; }
  function shareQuizUrl(slug) { return `https://tssrkt.github.io/quiz/v/${encodeURIComponent(slug)}/`; }
  function slugFromUrl(currentUrl) {
    const url = new URL(currentUrl);
    const querySlug = url.searchParams.get('quiz');
    if (querySlug !== null) return SLUG_PATTERN.test(querySlug) ? querySlug : '';
    const match = url.pathname.match(/\/v\/([a-z0-9]+(?:-[a-z0-9]+)*)\/(?:index\.html)?$/);
    return match ? match[1] : '';
  }
  function prefersReducedMotion(matchMedia) { return Boolean(matchMedia?.('(prefers-reduced-motion: reduce)').matches); }
  function autoAdvanceDelay(correct) { return correct ? 800 : null; }
  function shouldConfetti(correct, reducedMotion) { return Boolean(correct && !reducedMotion); }
  function shareMethod(webShareAvailable) { return webShareAvailable ? 'share' : 'copy'; }
  return { STATE_VERSION, canOpenQuiz, validateQuiz, structureSignature, vocabularyQuestions, versionedUrl, cloneValue, fisherYates, createAttemptQuiz, restoreAttemptOrder, freshState, restoreState, answerQuestion, advance, resultPercent, resultRecommendation, resultMessage, formatQuestionCount, coverAlt, questionImageAlt, shareText, directQuizUrl, shareQuizUrl, slugFromUrl, siteRootUrl: urlCore.siteRootUrl, siteUrl: urlCore.siteUrl, quizPath: urlCore.quizPath, prefersReducedMotion, autoAdvanceDelay, shouldConfetti, shareMethod };
});

function init(core) {
  'use strict';
  const app = document.getElementById('quiz-app');
  const main = document.getElementById('main');
  const previewBanner = document.getElementById('preview-banner');
  if (!app) return;
  const params = new URLSearchParams(location.search);
  const slug = core.slugFromUrl(location.href);
  const preview = params.get('preview') === '1';
  const reduceMotion = core.prefersReducedMotion(window.matchMedia.bind(window));
  let sourceQuiz, quiz, state, nextQuiz = null, answerLocked = false, transitionScheduled = false;
  const escapeHtml = (value) => String(value).replace(/[&<>"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[character]));
  const storageKey = () => `quiz-progress:${quiz.slug}`;
  const saveState = () => { try { localStorage.setItem(storageKey(), JSON.stringify(state)); } catch (error) { console.warn('[Quiz] Не удалось сохранить прогресс.', error); } };
  const clearState = () => { try { localStorage.removeItem(storageKey()); } catch (error) { console.warn('[Quiz] Не удалось очистить прогресс.', error); } };
  const setWideLayout = (wide) => main?.classList.toggle('quiz-layout-wide', wide);
  const pageUrl = (path) => core.siteUrl(path, location.href);
  const errorScreen = (message) => { setWideLayout(false); app.setAttribute('aria-busy', 'false'); app.innerHTML = `<div class="error-state" role="alert"><strong>${escapeHtml(message)}</strong><p><a class="button" href="${escapeHtml(pageUrl('quizzes.html'))}">К списку викторин</a></p></div>`; };

  function confetti(count = 22) {
    if (reduceMotion) return;
    const layer = document.createElement('div'); layer.className = 'confetti-layer'; layer.setAttribute('aria-hidden', 'true');
    for (let index = 0; index < count; index += 1) {
      const piece = document.createElement('i'); piece.style.setProperty('--x', `${8 + Math.random() * 84}%`); piece.style.setProperty('--delay', `${Math.random() * 100}ms`); piece.style.setProperty('--spin', `${Math.random() * 300 - 150}deg`); piece.className = `confetti-piece confetti-${index % 4}`; layer.appendChild(piece);
    }
    document.body.appendChild(layer); window.setTimeout(() => layer.remove(), 1100);
  }
  function preloadNextImage() { const next = quiz.questions[state.current_index + 1]; if (next?.image) { const image = new Image(); image.src = pageUrl(core.versionedUrl(next.image, quiz.content_version)); } }
  function coverTemplate() { return quiz.cover ? `<img class="quiz-intro-cover" src="${escapeHtml(pageUrl(quiz.cover))}" alt="${escapeHtml(core.coverAlt(quiz))}">` : ''; }
  function imageTemplate(question) {
    if (!question.image) return '';
    const source = question.image_source_url ? `<a href="${escapeHtml(question.image_source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(question.image_source || 'Источник изображения')}</a>` : escapeHtml(question.image_source || '');
    const credit = [question.image_author ? `Автор: ${escapeHtml(question.image_author)}` : '', source].filter(Boolean).join(' · ');
    return `<figure class="question-image"><img src="${escapeHtml(pageUrl(core.versionedUrl(question.image, quiz.content_version)))}" alt="${escapeHtml(core.questionImageAlt(quiz))}">${credit ? `<figcaption>${credit}</figcaption>` : ''}</figure>`;
  }
  function restart() { transitionScheduled = false; answerLocked = false; clearState(); quiz = core.createAttemptQuiz(sourceQuiz, true); state = core.freshState(quiz); saveState(); renderQuestion(); }
  function renderIntro() {
    setWideLayout(false);
    const hasProgress = Object.keys(state.answers).length > 0 && !state.completed;
    app.innerHTML = `<section class="quiz-intro">${coverTemplate()}<p class="eyebrow">${escapeHtml(core.formatQuestionCount(quiz.questions.length, quiz.type))}</p><h1 class="page-title">${escapeHtml(quiz.title)}</h1><p class="lead">${escapeHtml(quiz.intro)}</p><div class="quiz-intro-actions"><button class="button" type="button" data-start>${hasProgress ? 'Продолжить' : 'Начать викторину'}</button>${hasProgress ? '<button class="button button-secondary" type="button" data-restart>Начать заново</button>' : ''}</div></section>`;
    app.querySelector('[data-start]').addEventListener('click', renderQuestion);
    app.querySelector('[data-restart]')?.addEventListener('click', restart);
  }
  function advanceOnce() {
    if (!transitionScheduled) return;
    transitionScheduled = false;
    const result = core.advance(state, quiz); if (!result.advanced) return;
    state = result.state; saveState(); answerLocked = false;
    if (state.completed) renderResult(); else renderQuestion();
  }
  function renderQuestion(celebrateCorrect = false) {
    if (state.completed || state.current_index >= quiz.questions.length) { renderResult(); return; }
    transitionScheduled = false; answerLocked = Boolean(state.answers[quiz.questions[state.current_index].id]);
    const question = quiz.questions[state.current_index]; const record = state.answers[question.id];
    const withImage = Boolean(question.image);
    setWideLayout(withImage);
    const answers = question.answers.map((answer) => {
      const selected = record?.answer_id === answer.id;
      const isCorrect = answer.id === question.correct_answer_id;
      const status = record ? (isCorrect ? ' is-correct' : selected ? ' is-wrong' : '') : '';
      const icon = record && isCorrect ? '<span class="answer-icon" aria-hidden="true">✓</span><span class="visually-hidden">Правильный ответ.</span>' : record && selected ? '<span class="answer-icon" aria-hidden="true">×</span><span class="visually-hidden">Неправильный ответ.</span>' : '';
      return `<button class="answer-option${status}" type="button" data-answer="${escapeHtml(answer.id)}" ${record ? 'disabled' : ''}>${icon}<span>${escapeHtml(answer.text)}</span></button>`;
    }).join('');
    const correct = record?.correct === true;
    const feedback = record ? `<div class="answer-feedback${correct ? ' is-success' : ' is-error'}" role="status" aria-live="polite"><strong>${correct ? 'Верно!' : 'Неверно'}</strong>${correct ? '' : `<p>${escapeHtml(question.explanation)}</p><button class="button" type="button" data-next>${state.current_index + 1 === quiz.questions.length ? 'Показать результат' : 'Следующий вопрос'}</button>`}</div>` : '<div class="answer-feedback-placeholder" aria-live="polite"></div>';
    const questionContent = `<div class="question-content${quiz.type === 'vocabulary' ? ' vocabulary-question' : ''}"><p class="quiz-name">${escapeHtml(quiz.title)}</p><div class="quiz-progress"><span id="question-position">${quiz.type === 'vocabulary' ? 'Слово' : 'Вопрос'} ${state.current_index + 1} из ${quiz.questions.length}</span><progress aria-labelledby="question-position" value="${state.current_index + 1}" max="${quiz.questions.length}">${state.current_index + 1}/${quiz.questions.length}</progress></div><h1>${escapeHtml(quiz.type === 'vocabulary' ? question.question.toUpperCase() : question.question)}</h1><div class="answer-list" aria-label="Варианты ответа">${answers}</div>${feedback}</div>`;
    app.innerHTML = withImage
      ? `<section class="question-card question-card--with-image"><div class="question-layout">${imageTemplate(question)}${questionContent}</div></section>`
      : `<section class="question-card">${questionContent}</section>`;
    preloadNextImage();
    app.querySelectorAll('[data-answer]').forEach((button) => button.addEventListener('click', () => selectAnswer(button.dataset.answer)));
    app.querySelector('[data-next]')?.addEventListener('click', () => { if (transitionScheduled) return; transitionScheduled = true; advanceOnce(); });
    if (correct) { if (celebrateCorrect) confetti(); transitionScheduled = true; window.setTimeout(advanceOnce, core.autoAdvanceDelay(true)); }
  }
  function selectAnswer(answerId) {
    if (answerLocked || transitionScheduled) return;
    answerLocked = true;
    const result = core.answerQuestion(state, quiz, answerId);
    if (!result.accepted) return;
    state = result.state; saveState(); renderQuestion(result.correct);
  }
  async function copyResult(text, status) {
    try {
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) { try { await navigator.clipboard.writeText(text); copied = true; } catch (error) { console.warn('[Quiz] Clipboard API недоступен, используется резервное копирование.', error); } }
      if (!copied) { const area = document.createElement('textarea'); area.value = text; area.setAttribute('readonly', ''); area.className = 'copy-helper'; document.body.appendChild(area); area.select(); copied = document.execCommand('copy'); area.remove(); }
      if (!copied) throw new Error('copy failed');
      status.textContent = 'Результат скопирован.'; window.setTimeout(() => { status.textContent = ''; }, 2500); return true;
    } catch (error) { console.warn('[Quiz] Копирование недоступно.', error); status.textContent = 'Не удалось скопировать результат.'; return false; }
  }
  function renderResult() {
    setWideLayout(false);
    state = { ...state, completed: true, current_index: quiz.questions.length, saved_at: new Date().toISOString() }; saveState();
    const total = quiz.questions.length; const percent = core.resultPercent(state.correct_count, total); const message = core.resultMessage(percent); const url = core.shareQuizUrl(quiz.slug); const sharePayload = core.shareText(quiz, state.correct_count, total, url);
    const recommendation = core.resultRecommendation(percent);
    const explanation = message ? `${message} ${recommendation}` : recommendation;
    const resultDetails = `<p class="result-summary">Ваш результат: ${state.correct_count} из ${total} (${percent}%)</p><div class="result-recommendation"><p>${escapeHtml(explanation)}</p><a class="result-recommendation__articles" href="https://author.today/work/439719" target="_blank" rel="noopener noreferrer"><span class="result-recommendation__articles-content">📖 СБОРНИК СТАТЕЙ О ЛОШАДКАХ</span></a></div>`;
    const nextQuizBlock = nextQuiz ? `<div class="next-quiz"><p class="next-quiz__label">Следующая викторина</p><a class="next-quiz__link" href="${escapeHtml(core.quizPath(nextQuiz.slug, location.href))}"><span>${escapeHtml(nextQuiz.title)}</span></a></div>` : '';
    app.innerHTML = `<section class="result-card"><p class="eyebrow">Викторина завершена</p><h1>${escapeHtml(quiz.title)}</h1>${resultDetails}<div class="share-actions"><button class="button" type="button" data-share>Поделиться результатом</button><button class="button button-secondary" type="button" data-copy>Скопировать результат</button></div><div class="result-actions"><button class="button" type="button" data-restart>Пройти еще раз</button><a class="button button-secondary" href="${escapeHtml(pageUrl('quizzes.html'))}">К списку викторин</a></div><p class="share-status" role="status" aria-live="polite"></p>${nextQuizBlock}</section>`;
    const status = app.querySelector('.share-status');
    app.querySelector('[data-share]').addEventListener('click', async () => { if (navigator.share) { try { await navigator.share({ title: quiz.title, text: sharePayload }); return; } catch (error) { if (error.name === 'AbortError') return; } } await copyResult(sharePayload, status); });
    app.querySelector('[data-copy]').addEventListener('click', () => copyResult(sharePayload, status));
    app.querySelector('[data-restart]').addEventListener('click', restart);
    if (percent >= 90) confetti(34);
  }
  async function load() {
    if (location.protocol === 'file:') { errorScreen('Для запуска викторины откройте собранный сайт через локальный HTTP-сервер.'); return; }
    if (!slug) { errorScreen('Не указана викторина для открытия.'); return; }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) { errorScreen('Викторина не найдена.'); return; }
    try {
      const catalogResponse = await fetch(pageUrl(core.versionedUrl('data/catalog.json')), { cache: 'no-store' });
      if (!catalogResponse.ok) throw new Error(`Catalog HTTP ${catalogResponse.status}`);
      const catalog = await catalogResponse.json();
      const catalogQuiz = Array.isArray(catalog?.quizzes) ? catalog.quizzes.find((item) => item?.slug === slug) : null;
      const contentVersion = catalogQuiz?.content_version || String(Date.now());
      const response = await fetch(pageUrl(core.versionedUrl(`data/quizzes/${encodeURIComponent(slug)}.json`, contentVersion)), { cache: 'no-store' });
      if (response.status === 404) { errorScreen('Викторина не найдена.'); return; }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      sourceQuiz = await response.json();
      quiz = sourceQuiz;
      nextQuiz = quiz.next_quiz && Array.isArray(catalog?.quizzes) ? catalog.quizzes.find((item) => item?.slug === quiz.next_quiz) || null : null;
      if (catalogQuiz && quiz.content_version !== catalogQuiz.content_version) throw new Error('Версия викторины не совпадает с каталогом');
      if (!core.validateQuiz(quiz) || quiz.slug !== slug) { console.error('[Quiz] Повреждённый JSON или несовместимые данные викторины.'); errorScreen('Эту викторину сейчас невозможно открыть.'); return; }
      if (!core.canOpenQuiz(quiz, preview)) { errorScreen('Эта викторина пока не опубликована.'); return; }
      if (!quiz.published) previewBanner.hidden = false;
      let raw = null; try { raw = localStorage.getItem(storageKey()); } catch {}
      let savedOrder = null; try { savedOrder = raw ? JSON.parse(raw) : null; } catch {}
      quiz = core.restoreAttemptOrder(sourceQuiz, savedOrder);
      state = core.restoreState(raw, quiz); saveState(); app.setAttribute('aria-busy', 'false');
      if (state.completed) renderResult(); else renderIntro();
    } catch (error) { console.error('[Quiz] Ошибка загрузки викторины.', error); errorScreen('Не удалось загрузить викторину. Попробуйте позже.'); }
  }
  load();
}
