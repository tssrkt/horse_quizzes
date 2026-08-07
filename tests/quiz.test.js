'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
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
const vocabularyFixture = require('./fixtures/vocabulary/test-vocabulary.json');
const fixtureRows = fs.readFileSync(path.join(__dirname, 'fixtures/vocabulary/test-english.csv'), 'utf8').trim().split(/\r?\n/).slice(1);
const fixtureWords = fixtureRows.map((row) => { const [english, russian, category = ''] = row.split(','); return { english: english.trim(), russian: russian.trim(), category: category.trim() }; });
const vocabulary = { ...vocabularyFixture, published: true, content_version: 'b'.repeat(64), vocabulary: [
  ...fixtureWords.slice(0, 2), ...Array.from({ length: 5 }, (_, index) => ({ english: `word ${index}`, russian: `перевод ${index}`, category: 'colors' })), ...fixtureWords.slice(2)
] };
assert.equal(core.validateQuiz(vocabulary), true);
const vocabularyAttempt = core.createAttemptQuiz(vocabulary, true, () => 0, ['en-ru', 'ru-en']);
assert.equal(vocabularyAttempt.questions.length, 18);
assert.equal(new Set(vocabularyAttempt.questions.map((question) => question.id)).size, 18);
assert.deepEqual(vocabularyAttempt.selected_modes, ['en-ru', 'ru-en']);
assert.equal(vocabularyAttempt.questions.slice(0, 9).every((question) => question.mode === 'en-ru'), true);
assert.equal(vocabularyAttempt.questions.slice(9).every((question) => question.mode === 'ru-en'), true);
const gray = vocabularyAttempt.questions.find((question) => question.question === 'gray (grey)');
assert.equal(gray.answers.length, 6);
assert.equal(gray.answers.filter((answer) => answer.id === gray.correct_answer_id).length, 1);
assert.equal(gray.answers.filter((answer) => answer.id !== gray.correct_answer_id).length, 5);
assert.equal(gray.answers.every((answer) => !['лошадь', 'кобыла'].includes(answer.text)), true);
const horse = vocabularyAttempt.questions.find((question) => question.question === 'horse');
assert.deepEqual(new Set(horse.answers.map((answer) => answer.text)), new Set(['лошадь', 'кобыла']));
const reverseGray = vocabularyAttempt.questions.find((question) => question.mode === 'ru-en' && question.correct_answer_id === gray.correct_answer_id);
assert.equal(reverseGray.question, gray.explanation);
assert.equal(reverseGray.answers.find((answer) => answer.id === reverseGray.correct_answer_id).text, 'gray (grey)');
assert.equal(reverseGray.answers.every((answer) => !['лошадь', 'кобыла'].includes(answer.text)), true);
assert.equal(core.createAttemptQuiz(vocabulary, true, () => 0, ['en-ru']).questions.length, 9);
assert.equal(core.createAttemptQuiz(vocabulary, true, () => 0, ['ru-en']).questions.every((question) => question.mode === 'ru-en'), true);
const vocabularyState = core.freshState(vocabularyAttempt);
assert.deepEqual(vocabularyState.selected_modes, ['en-ru', 'ru-en']);
assert.equal(vocabularyState.current_mode, 'en-ru');
assert.deepEqual(core.updateModeSelection(['en-ru'], 'en-ru', false), ['en-ru']);
assert.deepEqual(core.updateModeSelection(['en-ru'], 'ru-en', true), ['en-ru', 'ru-en']);
assert.deepEqual(core.updateModeSelection(['en-ru', 'ru-en'], 'en-ru', false), ['ru-en']);
const restoredVocabulary = core.restoreAttemptOrder(vocabulary, vocabularyState);
assert.deepEqual(restoredVocabulary.questions.map((question) => question.id), vocabularyAttempt.questions.map((question) => question.id));
assert.deepEqual(restoredVocabulary.questions.map((question) => question.answers.map((answer) => answer.id)), vocabularyAttempt.questions.map((question) => question.answers.map((answer) => answer.id)));
const selectedModeWithoutProgress = core.restoreAttemptOrder({ ...vocabulary, selected_modes: ['en-ru'] }, null);
assert.equal(selectedModeWithoutProgress.questions.length, vocabulary.vocabulary.length, 'новая попытка использует только выбранный режим');
assert.equal(selectedModeWithoutProgress.questions.every((question) => question.mode === 'en-ru'), true);
const twentyFourWords = { ...vocabulary, vocabulary: Array.from({ length: 24 }, (_, index) => ({ english: `word ${index}`, russian: `перевод ${index}`, category: 'part' })) };
for (const mode of core.VOCABULARY_MODES) {
  const attempt = core.restoreAttemptOrder({ ...twentyFourWords, selected_modes: [mode] }, null);
  assert.equal(attempt.questions.length, 24, `${mode}: попытка выбранной части содержит 24 вопроса`);
  const restored = core.restoreAttemptOrder({ ...twentyFourWords, selected_modes: [mode] }, core.freshState(attempt));
  assert.equal(restored.questions.length, 24, `${mode}: восстановленная попытка сохраняет 24 вопроса`);
}
let combinedState = core.freshState(vocabularyAttempt);
for (let index = 0; index < vocabularyAttempt.questions.length; index += 1) {
  const question = vocabularyAttempt.questions[index];
  combinedState = core.answerQuestion(combinedState, vocabularyAttempt, question.correct_answer_id).state;
  combinedState = core.advance(combinedState, vocabularyAttempt).state;
  if (index === 8) assert.equal(combinedState.current_mode, 'ru-en');
}
assert.equal(combinedState.completed, true);
assert.equal(combinedState.correct_count, 18);
const typingAttempt = core.createAttemptQuiz(vocabulary, true, () => 0, ['typing']);
assert.equal(typingAttempt.questions.length, 9);
assert.equal(typingAttempt.questions.every((question) => question.typing && question.mode === 'typing'), true);
assert.deepEqual(core.acceptedEnglishAnswers('gray (grey, grayish)'), ['gray (grey, grayish)', 'gray', 'grey', 'grayish']);
for (const answer of ['GRAY (GREY)', ' gray ', 'GREY', '  gray   (grey)  ']) assert.equal(core.isTypedAnswerCorrect(answer, 'gray (grey)'), true);
assert.equal(core.isTypedAnswerCorrect('grayish', 'gray (grey)'), false);
let typingState = core.freshState(typingAttempt);
assert.equal(core.answerTypingQuestion(typingState, typingAttempt, '   ').accepted, false);
const typedCorrect = core.answerTypingQuestion(typingState, typingAttempt, typingAttempt.questions[0].explanation.toUpperCase());
assert.equal(typedCorrect.accepted, true); assert.equal(typedCorrect.correct, true);
assert.equal(core.answerTypingQuestion(typedCorrect.state, typingAttempt, 'another').accepted, false);
const restoredTyped = core.restoreState(JSON.stringify(typedCorrect.state), typingAttempt);
assert.equal(restoredTyped.answers[typingAttempt.questions[0].id].input, typingAttempt.questions[0].explanation.toUpperCase());
typingState = core.freshState(typingAttempt);
const typedWrong = core.answerTypingQuestion(typingState, typingAttempt, 'wrong');
assert.equal(typedWrong.correct, false); assert.equal(typedWrong.state.answers[typingAttempt.questions[0].id].input, 'wrong');
const allModes = core.createAttemptQuiz(vocabulary, true, () => 0);
assert.equal(allModes.questions.length, 27);
assert.deepEqual([...new Set(allModes.questions.map((question) => question.mode))], ['en-ru', 'ru-en', 'typing']);
const sixWords = { ...vocabulary, vocabulary: vocabulary.vocabulary.slice(0, 6) };
assert.equal(core.createAttemptQuiz(sixWords, true, () => 0, ['en-ru']).questions.every((question) => question.answers.length === 6), true);
function groupedVocabulary(size) {
  return {
    ...vocabulary,
    vocabulary: [
      ...Array.from({ length: size }, (_, index) => ({ english: `group word ${index}`, russian: `группа ${index}`, category: 'target' })),
      { english: 'foreign one', russian: 'чужой один', category: 'other' },
      { english: 'foreign two', russian: 'чужой два', category: 'other' }
    ]
  };
}
for (const size of [2, 4, 6, 30]) {
  const grouped = groupedVocabulary(size);
  for (const mode of ['en-ru', 'ru-en']) {
    const attempt = core.createAttemptQuiz(grouped, true, () => 0.75, [mode]);
    const question = attempt.questions.find((item) => item.correct_answer_id === 'word-01');
    assert.equal(question.answers.length, Math.min(size, 6), `${mode}: категория из ${size} слов ограничена шестью вариантами`);
    assert.equal(question.answers.filter((answer) => answer.id === question.correct_answer_id).length, 1, `${mode}: правильный вариант присутствует ровно один раз`);
    assert.equal(new Set(question.answers.map((answer) => answer.text)).size, question.answers.length, `${mode}: тексты вариантов не повторяются`);
    assert.equal(question.answers.every((answer) => answer.id !== `word-${String(size + 1).padStart(2, '0')}` && answer.id !== `word-${String(size + 2).padStart(2, '0')}`), true, `${mode}: варианты другой категории исключены`);
  }
}
const thirtyWords = groupedVocabulary(30);
const directlyGenerated = core.vocabularyQuestions(thirtyWords, 'en-ru', () => 0.5, true);
assert.equal(directlyGenerated.every((question) => question.answers.length <= 6), true, 'сам генератор словарных вопросов не создаёт больше шести вариантов');
assert.equal(core.createAttemptQuiz(thirtyWords, false, () => 0, ['en-ru']).questions.every((question) => question.answers.length <= 6), true, 'лимит действует независимо от флага перемешивания');
const firstWrongSet = new Set(core.createAttemptQuiz(thirtyWords, true, () => 0, ['en-ru']).questions.find((item) => item.correct_answer_id === 'word-01').answers.filter((answer) => answer.id !== 'word-01').map((answer) => answer.id));
const secondWrongSet = new Set(core.createAttemptQuiz(thirtyWords, true, () => 0.999, ['en-ru']).questions.find((item) => item.correct_answer_id === 'word-01').answers.filter((answer) => answer.id !== 'word-01').map((answer) => answer.id));
assert.notDeepEqual(firstWrongSet, secondWrongSet, 'при новом прохождении набор неправильных вариантов может измениться');
const brokenVocabularyOrder = core.freshState(core.createAttemptQuiz(thirtyWords, true, () => 0.25, ['en-ru']));
brokenVocabularyOrder.answer_ids[brokenVocabularyOrder.question_ids[0]] = ['missing-answer'];
assert.equal(core.restoreAttemptOrder(thirtyWords, brokenVocabularyOrder).questions.every((question) => question.answers.length <= 6), true, 'повреждённое сохранение не возвращает полный список категории');
const legacyVocabularyOrder = core.freshState(core.createAttemptQuiz(thirtyWords, true, () => 0.25, ['en-ru']));
legacyVocabularyOrder.answer_ids[legacyVocabularyOrder.question_ids[0]] = Array.from({ length: 30 }, (_, index) => `word-${String(index + 1).padStart(2, '0')}`);
assert.equal(core.restoreAttemptOrder(thirtyWords, legacyVocabularyOrder).questions.every((question) => question.answers.length <= 6), true, 'старое сохранение со всей категорией заменяется набором не больше шести вариантов');
const duplicateTranslations = groupedVocabulary(7);
duplicateTranslations.vocabulary[1].russian = duplicateTranslations.vocabulary[2].russian;
const uniqueAnswers = core.createAttemptQuiz(duplicateTranslations, true, () => 0.5, ['en-ru']).questions.find((item) => item.correct_answer_id === 'word-01').answers;
assert.equal(new Set(uniqueAnswers.map((answer) => answer.text)).size, uniqueAnswers.length, 'одинаковые переводы не дублируются');
assert.equal(core.formatQuestionCount(9, 'vocabulary'), '9 слов');
for (const [count, form] of [[0, 'слов'], [1, 'слово'], [2, 'слова'], [4, 'слова'], [5, 'слов'], [11, 'слов'], [12, 'слов'], [14, 'слов'], [21, 'слово'], [22, 'слова'], [24, 'слова'], [25, 'слов'], [82, 'слова'], [87, 'слов'], [111, 'слов'], [112, 'слов'], [121, 'слово'], [122, 'слова']]) {
  assert.equal(core.formatQuestionCount(count, 'vocabulary'), `${count} ${form}`);
}
const multipartVocabulary = {
  ...vocabulary,
  word_count: 4,
  parts: [
    { id: 'head', title: '', word_count: 2, vocabulary: [{ english: 'head', russian: 'голова', category: 'same' }, { english: 'neck', russian: 'шея', category: 'same' }] },
    { id: 'tack', title: 'Амуниция', word_count: 2, vocabulary: [{ english: 'saddle', russian: 'седло', category: 'same' }, { english: 'bridle', russian: 'уздечка', category: 'same' }] }
  ]
};
assert.equal(core.validateQuiz(multipartVocabulary), true);
assert.deepEqual(core.vocabularyParts(multipartVocabulary).map((part) => [part.id, part.title, part.word_count]), [['head', 'Часть 1', 2], ['tack', 'Амуниция', 2]]);
const selectedHead = core.selectVocabularyPart(multipartVocabulary, 'head');
assert.equal(core.totalVocabularyWordCount(multipartVocabulary), 4, 'общий счётчик суммирует слова всех частей');
assert.equal(core.totalVocabularyWordCount(vocabulary), vocabulary.vocabulary.length, 'старый формат с одной частью сохраняет количество слов');
assert.equal(core.totalVocabularyWordCount({ parts: [29, 39, 43].map((count, index) => ({ id: `part-${index + 1}`, vocabulary: Array.from({ length: count }, () => ({})) })) }), 111, '29 + 39 + 43 слова дают общий объём 111 слов');
const selectedTack = core.selectVocabularyPart(multipartVocabulary, 'tack');
assert.deepEqual(selectedHead.vocabulary.map((word) => word.english), ['head', 'neck']);
assert.deepEqual(selectedTack.vocabulary.map((word) => word.english), ['saddle', 'bridle']);
assert.equal(core.selectVocabularyPart(multipartVocabulary, 'missing').selected_part_id, 'head', 'удалённая часть безопасно сбрасывается на первую');
const headAttempt = core.createAttemptQuiz(selectedHead, true, () => 0, ['en-ru']);
const tackAttempt = core.createAttemptQuiz(selectedTack, true, () => 0, ['en-ru']);
assert.equal(headAttempt.questions.every((question) => question.answers.every((answer) => !['седло', 'уздечка'].includes(answer.text))), true);
assert.equal(tackAttempt.questions.every((question) => question.answers.every((answer) => !['голова', 'шея'].includes(answer.text))), true);
assert.equal(core.freshState(headAttempt).selected_part_id, 'head');
assert.equal(core.freshState(tackAttempt).selected_part_id, 'tack');
assert.notEqual(core.structureSignature(headAttempt), core.structureSignature(tackAttempt), 'прогресс разных частей несовместим');
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
assert.equal(core.validateQuiz({ ...quiz, previous_quiz: 'previous-quiz' }), true, 'slug предыдущей викторины валиден');
assert.equal(core.validateQuiz({ ...quiz, previous_quiz: 'Некорректный slug' }), false, 'некорректная связь предыдущей викторины отклоняется');

let state = core.freshState(quiz, '2026-01-01T00:00:00.000Z');
const correct = core.answerQuestion(state, quiz, 'a-01');
assert.equal(correct.accepted, true); assert.equal(correct.correct, true); assert.equal(correct.state.correct_count, 1, '4: первый правильный ответ');
const repeated = core.answerQuestion(correct.state, quiz, 'a-02');
assert.equal(repeated.accepted, false); assert.equal(repeated.state.correct_count, 1, '6: повторный выбор заблокирован');
assert.equal(core.autoAdvanceDelay(true), 800, '7: правильный ответ переходит через 800 мс');
assert.equal(core.autoAdvanceDelay(false), null, '8: неправильный ответ не переходит автоматически');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: true }, null, false), 'submit', 'первый Enter отправляет typing-форму');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: true }, { correct: false }, false), 'advance', 'Enter после ошибки Typing переходит дальше');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: false, mode: 'en-ru' }, { correct: false }, false), 'advance', 'Enter после ошибки EN → RU переходит дальше');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: false, mode: 'ru-en' }, { correct: false }, false), 'advance', 'Enter после ошибки RU → EN переходит дальше');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: false }, null, false), null, 'Enter до ответа в режиме выбора ничего не делает');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: true }, { correct: false }, true), null, 'повторный Enter во время перехода игнорируется');
assert.equal(core.vocabularyEnterAction('vocabulary', { typing: false }, { correct: true }, true), null, 'Enter не вмешивается в автоматический переход после правильного ответа');
assert.equal(core.vocabularyEnterAction('quiz', { typing: false }, { correct: false }, false), null, 'Enter не меняет обычные викторины');
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
for (const percent of [0, 49, 50, 74, 75, 90, 99, 100]) assert.equal(typeof core.resultRecommendation(percent), 'string');
assert.doesNotMatch(core.resultRecommendation(90), /^Отличный результат! Хороший результат!/);

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

const horseColorsUrl = 'https://example.test/project/quiz.html?quiz=horse-colors';
const rareColorsUrl = 'https://example.test/project/quiz.html?quiz=rare-horse-colors';
assert.equal(core.shareText({ title: 'Масти лошадей' }, 34, 40, horseColorsUrl), `Мой результат — 34 из 40 (85%) в викторине «Масти лошадей». А какой у вас? Проверьте: ${horseColorsUrl}`, '17: неполный результат публикации');
const perfectShare = core.shareText({ title: 'Редкие масти' }, 5, 5, rareColorsUrl);
assert.equal(perfectShare, `Мой результат — 5 из 5 (100%) в викторине «Редкие масти». А какой у вас? Проверьте: ${rareColorsUrl}`, '100%, название и ссылка текущей викторины');
assert.equal(perfectShare.includes('\n'), false, 'текст публикации занимает одну строку');
assert.equal(/\s{2,}/.test(perfectShare), false, 'в тексте публикации нет двойных пробелов');
assert.equal(core.shareText({ title: 'Редкие  масти' }, 4, 5, rareColorsUrl).includes('«Редкие масти»'), true, 'пробелы в названии нормализуются');
assert.equal(core.directQuizUrl('https://example.test/quiz/quiz.html?quiz=x&preview=1', 'horse-colors'), 'https://example.test/quiz/quiz.html?quiz=horse-colors');
assert.equal(core.shareQuizUrl('horse-colors', horseColorsUrl), 'https://example.test/project/v/horse-colors/');
assert.equal(core.slugFromUrl('https://example.test/project/quiz.html?quiz=anatomy'), 'anatomy', 'старый URL определяет slug из query');
assert.equal(core.slugFromUrl('https://example.test/project/v/anatomy/'), 'anatomy', 'новый URL определяет slug из пути');
assert.equal(core.slugFromUrl('https://example.test/project/v/anatomy/index.html'), 'anatomy', 'index.html нового URL поддерживается');
assert.equal(core.slugFromUrl('https://example.test/project/quizzes/anatomy/'), '', 'соседний путь не считается страницей викторины');
assert.equal(core.slugFromUrl('https://example.test/project/v/ANATOMY/'), '', 'некорректный slug пути отклоняется');
assert.equal(core.slugFromUrl('https://example.test/project/v/anatomy/?quiz=bad!'), '', 'явный некорректный query не заменяется значением пути');
assert.equal(core.siteRootUrl('https://example.test/project/v/anatomy/'), 'https://example.test/project/');
assert.equal(core.siteRootUrl('http://localhost:8000/v/anatomy/'), 'http://localhost:8000/');
assert.equal(core.siteUrl('data/catalog.json', 'https://example.test/project/v/anatomy/'), 'https://example.test/project/data/catalog.json');
assert.equal(core.quizPath('anatomy', 'https://example.test/project/quiz.html?quiz=anatomy'), '/project/v/anatomy/');
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
