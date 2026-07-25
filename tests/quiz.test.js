'use strict';
const assert = require('node:assert/strict');
const core = require('../js/quiz.js');

function makeQuiz(published = true) {
  return {
    slug: 'demo-quiz', title: 'Демо', intro: 'Вступление', published, content_version: 'a'.repeat(64),
    questions: [
      { id: 'question-01', question: 'Первый?', explanation: 'Пояснение 1', correct_answer_id: 'a-01', answers: [{ id: 'a-01', text: 'Да' }, { id: 'a-02', text: 'Нет' }] },
      { id: 'question-02', question: 'Второй?', explanation: 'Пояснение 2', correct_answer_id: 'a-02', answers: [{ id: 'a-01', text: 'Нет' }, { id: 'a-02', text: 'Да' }] }
    ]
  };
}
function answerAndAdvance(state, quiz, answerId) {
  const answered = core.answerQuestion(state, quiz, answerId, '2026-01-01T00:00:00.000Z');
  const advanced = core.advance(answered.state, quiz, '2026-01-01T00:00:01.000Z');
  return { answered, advanced };
}

const quiz = makeQuiz(true);
const originalSnapshot = JSON.stringify(quiz);
const firstAttempt = core.createAttemptQuiz(quiz);
assert.deepEqual(firstAttempt.questions.map((question) => question.id), ['question-01', 'question-02'], 'первое прохождение сохраняет порядок вопросов');
assert.deepEqual(firstAttempt.questions[0].answers.map((answer) => answer.id), ['a-01', 'a-02'], 'первое прохождение сохраняет порядок вариантов');
const randomValues = [0, 0, 0];
const shuffledAttempt = core.createAttemptQuiz(quiz, true, () => randomValues.shift());
assert.deepEqual(shuffledAttempt.questions.map((question) => question.id), ['question-02', 'question-01'], 'вопросы перемешиваются предсказуемым RNG');
assert.deepEqual(shuffledAttempt.questions[0].answers.map((answer) => answer.id), ['a-02', 'a-01'], 'варианты перемешиваются как объекты');
assert.equal(shuffledAttempt.questions[0].answers[0].text, quiz.questions[1].answers[1].text, 'текст остаётся связан со своим id');
assert.equal(shuffledAttempt.questions[0].explanation, quiz.questions[1].explanation, 'пояснение остаётся у вопроса');
assert.equal(JSON.stringify(quiz), originalSnapshot, 'исходная викторина не мутирует');
assert.notEqual(shuffledAttempt.questions[0], quiz.questions[1], 'вопросы скопированы');
assert.notEqual(shuffledAttempt.questions[0].answers[0], quiz.questions[1].answers[1], 'варианты глубоко скопированы');
const shuffledState = core.freshState(shuffledAttempt);
const restoredAttempt = core.restoreAttemptOrder(quiz, shuffledState);
assert.deepEqual(restoredAttempt.questions.map((question) => question.id), shuffledAttempt.questions.map((question) => question.id), 'порядок попытки стабилен после восстановления');
assert.deepEqual(restoredAttempt.questions[0].answers.map((answer) => answer.id), shuffledAttempt.questions[0].answers.map((answer) => answer.id));
const shuffledCorrect = core.answerQuestion(shuffledState, shuffledAttempt, shuffledAttempt.questions[0].correct_answer_id);
assert.equal(shuffledCorrect.correct, true, 'правильность не зависит от новой позиции');
const variedQuiz = makeQuiz();
variedQuiz.questions[0].image = 'img/with-image.webp';
variedQuiz.questions[0].answers.push({ id: 'a-03', text: 'Возможно', metadata: { weight: 3 } });
delete variedQuiz.questions[1].image;
const variedSnapshot = JSON.stringify(variedQuiz);
const variedAttempt = core.createAttemptQuiz(variedQuiz, true, () => 0);
assert.equal(variedAttempt.questions.find((question) => question.id === 'question-01').image, 'img/with-image.webp', 'изображение остаётся у своего вопроса');
assert.equal(variedAttempt.questions.find((question) => question.id === 'question-02').image, undefined, 'вопрос без изображения поддерживается');
assert.equal(variedAttempt.questions.find((question) => question.id === 'question-01').answers.length, 3, 'разное количество вариантов сохраняется');
assert.notEqual(variedAttempt.questions.find((question) => question.id === 'question-01').answers.find((answer) => answer.id === 'a-03').metadata, variedQuiz.questions[0].answers[2].metadata, 'вложенные данные варианта скопированы глубоко');
assert.equal(JSON.stringify(variedQuiz), variedSnapshot);
let repeatedAttempt = shuffledCorrect.state;
for (const random of [() => 0, () => 0.999999]) {
  const nextQuiz = core.createAttemptQuiz(quiz, true, random);
  repeatedAttempt = core.freshState(nextQuiz);
  assert.equal(repeatedAttempt.current_index, 0, 'повтор начинается с первого вопроса новой попытки');
  assert.equal(repeatedAttempt.correct_count, 0, 'счёт повторной попытки сброшен');
  assert.deepEqual(repeatedAttempt.answers, {}, 'выбранные ответы и обратная связь сброшены');
  assert.equal(repeatedAttempt.completed, false, 'результат предыдущей попытки сброшен');
}
assert.equal(core.validateQuiz(quiz), true, '1: опубликованная викторина валидна');
assert.equal(core.canOpenQuiz(quiz, false), true, '1: опубликованная открывается');
assert.equal(core.canOpenQuiz(makeQuiz(false), true), true, '2: черновик открывается в preview');
assert.equal(core.canOpenQuiz(makeQuiz(false), false), false, '3: черновик закрыт без preview');
assert.equal(core.validateQuiz({}), false, 'повреждённые данные отклоняются');
assert.equal(core.validateQuiz({ ...quiz, next_quiz: 'next-quiz' }), true, 'slug следующей викторины валиден');
assert.equal(core.validateQuiz({ ...quiz, next_quiz: 'Некорректный slug' }), false, 'некорректная связь следующей викторины отклоняется');

let state = core.freshState(quiz, '2026-01-01T00:00:00.000Z');
const correct = core.answerQuestion(state, quiz, 'a-01');
assert.equal(correct.accepted, true); assert.equal(correct.correct, true); assert.equal(correct.state.correct_count, 1, '4: первый правильный ответ');
const repeated = core.answerQuestion(correct.state, quiz, 'a-02');
assert.equal(repeated.accepted, false); assert.equal(repeated.state.correct_count, 1, '6: повторный выбор заблокирован');
assert.equal(core.autoAdvanceDelay(true), 800, '7: правильный ответ переходит через 800 мс');
assert.equal(core.autoAdvanceDelay(false), null, '8: неправильный ответ не переходит автоматически');
assert.equal(quiz.questions[0].explanation, 'Пояснение 1', '9: пояснение доступно для неправильного ответа');

state = core.freshState(quiz);
const wrong = core.answerQuestion(state, quiz, 'a-02');
assert.equal(wrong.accepted, true); assert.equal(wrong.correct, false); assert.equal(wrong.state.correct_count, 0, '5: первый неправильный ответ');
const moved = core.advance(wrong.state, quiz);
assert.equal(moved.advanced, true); assert.equal(moved.state.current_index, 1, '9: кнопка переводит дальше');
const notDouble = core.advance(moved.state, quiz);
assert.equal(notDouble.advanced, false); assert.equal(notDouble.state.current_index, 1, '20: двойной переход невозможен');
const last = answerAndAdvance(moved.state, quiz, 'a-02');
assert.equal(last.advanced.state.completed, true); assert.equal(last.advanced.state.current_index, 2, '10: последний вопрос завершает попытку');
assert.equal(last.advanced.state.correct_count, 1, '11: правильные ответы подсчитаны');
assert.equal(core.resultPercent(34, 40), 85, '12: процент округляется');
assert.match(core.resultRecommendation(49), /^Что ж, некоторые вопросы/);
assert.match(core.resultRecommendation(50), /^Неплохой результат!/);
assert.match(core.resultRecommendation(74), /^Неплохой результат!/);
assert.match(core.resultRecommendation(75), /^Хороший результат!/);
assert.match(core.resultRecommendation(99), /^Хороший результат!/);
assert.equal(core.resultRecommendation(100), 'Вы правильно ответили на все вопросы и прекрасно разбираетесь в данной теме. Вас не так-то просто запутать! А в сборнике статей о лошадках наверняка найдется еще много интересного.');
assert.equal(core.resultMessage(90), 'Отличный результат!');
assert.equal(core.resultMessage(89), '');
assert.equal(core.resultMessage(74), '');
assert.equal(core.resultMessage(49), '', '13: удаленные вступительные фразы отсутствуют');
[
  [100, 'Отличный результат!'],
  [95, 'Отличный результат!'],
  [80, ''],
  [60, ''],
  [40, ''],
].forEach(([percent, introduction]) => {
  assert.equal(core.resultMessage(percent), introduction);
  assert.equal(typeof core.resultRecommendation(percent), 'string');
});

const saved = JSON.stringify(moved.state);
const restored = core.restoreState(saved, quiz);
assert.equal(restored.current_index, 1); assert.equal(restored.answers['question-01'].answer_id, 'a-02', '14: сохранение восстановлено');
const restarted = core.freshState(quiz);
assert.equal(restarted.current_index, 0); assert.equal(Object.keys(restarted.answers).length, 0, '15: начало заново');
const changedQuiz = makeQuiz(); changedQuiz.questions[0].answers.push({ id: 'a-03', text: 'Может быть' });
const incompatible = core.restoreState(saved, changedQuiz);
assert.equal(incompatible.current_index, 0); assert.equal(Object.keys(incompatible.answers).length, 0, '16: несовместимое сохранение сброшено');
for (const mutate of [
  (value) => { value.questions[0].question = 'Изменённый вопрос?'; },
  (value) => { value.questions[0].explanation = 'Новое объяснение'; },
  (value) => { value.questions[0].answers[0].text = 'Изменённый ответ'; },
  (value) => { value.questions.reverse(); },
  (value) => { value.questions.push({ id: 'question-03', question: 'Третий?', image: 'img/quiz/demo/03.webp', explanation: 'Пояснение 3', correct_answer_id: 'a-01', answers: [{ id: 'a-01', text: 'Да' }, { id: 'a-02', text: 'Нет' }] }); }
]) {
  const changed = makeQuiz(); mutate(changed);
  assert.equal(core.restoreState(saved, changed).current_index, 0, 'изменение содержимого сбрасывает прогресс');
}
assert.equal(core.versionedUrl('data/quizzes/horse-colors.json', 'abc123'), 'data/quizzes/horse-colors.json?v=abc123');
assert.equal(core.versionedUrl('img/quiz/horse-colors/01.webp', 'abc123'), 'img/quiz/horse-colors/01.webp?v=abc123');

const horseColorsUrl = 'https://tssrkt.github.io/quiz/quiz.html?quiz=horse-colors';
const rareColorsUrl = 'https://tssrkt.github.io/quiz/quiz.html?quiz=rare-horse-colors';
assert.equal(core.shareText({ title: 'Масти лошадей' }, 34, 40, horseColorsUrl), `Мой результат — 34 из 40 (85%) в викторине «Масти лошадей». А какой у вас? Проверьте: ${horseColorsUrl}`, '17: неполный результат публикации');
const perfectShare = core.shareText({ title: 'Редкие масти' }, 5, 5, rareColorsUrl);
assert.equal(perfectShare, `Мой результат — 5 из 5 (100%) в викторине «Редкие масти». А какой у вас? Проверьте: ${rareColorsUrl}`, '100%, название и ссылка текущей викторины');
assert.equal(perfectShare.includes('\n'), false, 'текст публикации занимает одну строку');
assert.equal(/\s{2,}/.test(perfectShare), false, 'в тексте публикации нет двойных пробелов');
assert.equal(core.shareText({ title: 'Редкие  масти' }, 4, 5, rareColorsUrl).includes('«Редкие масти»'), true, 'пробелы в названии нормализуются');
assert.equal(core.directQuizUrl('https://example.test/quiz/quiz.html?quiz=x&preview=1', 'horse-colors'), 'https://example.test/quiz/quiz.html?quiz=horse-colors');
assert.equal(core.shareQuizUrl('horse-colors'), 'https://tssrkt.github.io/quiz/v/horse-colors/');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/quiz.html?quiz=anatomy'), 'anatomy', 'старый URL определяет slug из query');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/v/anatomy/'), 'anatomy', 'новый URL определяет slug из пути');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/v/anatomy/index.html'), 'anatomy', 'index.html нового URL поддерживается');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/quizzes/anatomy/'), '', 'соседний путь не считается страницей викторины');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/v/ANATOMY/'), '', 'некорректный slug пути отклоняется');
assert.equal(core.slugFromUrl('https://tssrkt.github.io/quiz/v/anatomy/?quiz=bad!'), '', 'явный некорректный query не заменяется значением пути');
assert.equal(core.siteRootUrl('https://tssrkt.github.io/quiz/v/anatomy/'), 'https://tssrkt.github.io/quiz/');
assert.equal(core.siteRootUrl('http://localhost:8000/v/anatomy/'), 'http://localhost:8000/');
assert.equal(core.siteUrl('data/catalog.json', 'https://tssrkt.github.io/quiz/v/anatomy/'), 'https://tssrkt.github.io/quiz/data/catalog.json');
assert.equal(core.quizPath('anatomy', 'https://tssrkt.github.io/quiz/quiz.html?quiz=anatomy'), '/quiz/v/anatomy/');
assert.equal(core.coverAlt({ title: 'Породы лошадей' }), 'Обложка викторины «Породы лошадей»');
assert.equal(core.questionImageAlt({ questionImagesAlt: ' Фотография лошади для определения породы ' }), 'Фотография лошади для определения породы');
assert.equal(core.questionImageAlt({}), 'Фотография лошади к вопросу');
assert.equal(core.questionImageAlt({ questionImagesAlt: '' }), 'Фотография лошади к вопросу');
assert.equal(core.questionImageAlt({ questionImagesAlt: 'Общий alt', questions: [{ image_alt: 'Старый alt' }] }), 'Общий alt');
assert.equal(core.shareMethod(false), 'copy', '18: fallback без Web Share');
assert.equal(core.shareMethod(true), 'share');
assert.equal(core.prefersReducedMotion(() => ({ matches: true })), true);
assert.equal(core.shouldConfetti(true, true), false); assert.equal(core.shouldConfetti(true, false), true, '19: reduced motion отключает конфетти');

function runScenario(answerIds, closeAfterFirst = false) {
  let attempt = core.freshState(quiz);
  answerIds.forEach((answerId, index) => {
    const step = answerAndAdvance(attempt, quiz, answerId); attempt = step.advanced.state;
    if (closeAfterFirst && index === 0) attempt = core.restoreState(JSON.stringify(attempt), quiz);
  });
  return attempt;
}
assert.equal(runScenario(['a-01', 'a-02']).correct_count, 2, 'сценарий: все правильные');
assert.equal(runScenario(['a-02', 'a-01']).correct_count, 0, 'сценарий: все неправильные');
const mixed = runScenario(['a-01', 'a-01'], true);
assert.equal(mixed.correct_count, 1); assert.equal(mixed.completed, true, 'сценарий: смешанный с восстановлением');

console.log('quiz.test.js: 20 требований и 3 сценария пройдены');
