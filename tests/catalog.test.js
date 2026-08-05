'use strict';

const assert = require('node:assert/strict');
const {
  PAGE_SIZE,
  DIFFICULTY_LABELS,
  validateQuiz,
  validDateValue,
  sortQuizzes,
  arrangeQuizzes,
  sectionQuizzes,
  sortTooltip,
  countTags,
  orderTagsByCount,
  paginationItems,
  getStateFromUrl,
  buildUrl,
  vocabularyWord,
  volumeLabel,
  quizPath
} = require('../js/quizzes.js');

function quiz(index, overrides = {}) {
  return {
    slug: `quiz-${index}`,
    title: `Викторина ${String(index).padStart(3, '0')}`,
    publication_date: `2026-01-${String((index % 28) + 1).padStart(2, '0')}`,
    difficulty: 'low',
    short_description: 'Описание',
    intro: 'Вступление',
    tags: index % 2 ? ['horses'] : ['biology', 'horses'],
    ...overrides
  };
}

function pagesFor(count) {
  return Math.max(1, Math.ceil(Array.from({ length: count }, (_, index) => quiz(index)).length / PAGE_SIZE));
}

assert.equal(PAGE_SIZE, 10);
const vocabularyForms = new Map([
  [0, 'слов'], [1, 'слово'], [2, 'слова'], [4, 'слова'], [5, 'слов'], [11, 'слов'], [12, 'слов'], [14, 'слов'],
  [21, 'слово'], [22, 'слова'], [24, 'слова'], [25, 'слов'], [82, 'слова'], [87, 'слов'],
  [111, 'слов'], [112, 'слов'], [121, 'слово'], [122, 'слова']
]);
for (const [count, form] of vocabularyForms) {
  assert.equal(vocabularyWord(count), form, `${count} ${form}`);
  assert.equal(volumeLabel({ type: 'vocabulary', question_count: count }), `${count} ${form}`);
}
assert.deepEqual(DIFFICULTY_LABELS, { low: 'низкая', medium: 'средняя', high: 'высокая' });
assert.equal(pagesFor(0), 1);
assert.equal(pagesFor(1), 1);
assert.equal(pagesFor(10), 1);
assert.equal(pagesFor(11), 2);
assert.equal(pagesFor(20), 2);
assert.equal(pagesFor(21), 3);
assert.equal(Array.from({ length: 11 }).slice(PAGE_SIZE).length, 1);
assert.equal(Array.from({ length: 21 }).slice(PAGE_SIZE * 2).length, 1);

const grouped = arrangeQuizzes([
  quiz(1, { slug: 'other-new', title: 'Яблоко', publication_date: '2026-04-01', tags: ['biology'] }),
  quiz(2, { slug: 'match-old', title: 'Бета', publication_date: '2025-01-01', tags: ['horses'] }),
  quiz(3, { slug: 'match-new', title: 'Альфа', publication_date: '2026-03-01', tags: ['horses', 'biology'] }),
  quiz(4, { slug: 'other-old', title: 'Гамма', publication_date: '2024-01-01', tags: ['biology'] })
], 'horses', 'date', 'down');
assert.deepEqual(grouped.map((item) => item.slug), ['match-new', 'match-old']);
assert.equal(new Set(grouped.map((item) => item.slug)).size, grouped.length);
const counts = countTags(grouped, [{ slug: 'horses' }, { slug: 'biology' }]);
assert.equal(counts.get('horses'), 2);
assert.equal(counts.get('biology'), 1);
assert.equal(counts.has('hidden'), false);

const tagDefinitions = [
  { slug: 'zero', name: 'Яблоки' },
  { slug: 'horses', name: 'Масти' },
  { slug: 'biology', name: 'Биология' },
  { slug: 'history', name: 'Археология' }
];
const tagQuizzes = [
  quiz(1, { tags: ['horses', 'biology'] }),
  quiz(2, { tags: ['horses', 'history'] }),
  quiz(3, { tags: ['horses', 'biology'] })
];
assert.deepEqual(
  orderTagsByCount(tagQuizzes, tagDefinitions).map(({ slug, count }) => [slug, count]),
  [['horses', 3], ['biology', 2], ['history', 1]]
);
assert.deepEqual(
  orderTagsByCount(tagQuizzes.slice(1), tagDefinitions).map(({ slug, count }) => [slug, count]),
  [['horses', 2], ['history', 1], ['biology', 1]]
);
assert.deepEqual(
  orderTagsByCount([...tagQuizzes, quiz(4, { tags: ['history'] })], tagDefinitions).map(({ slug, count }) => [slug, count]),
  [['horses', 3], ['history', 2], ['biology', 2]]
);

const sectioned = [quiz(1), quiz(2), quiz(3, { type: 'vocabulary' }), quiz(4, { type: 'vocabulary' }), quiz(5, { type: 'english' })];
assert.deepEqual(sectionQuizzes(sectioned, 'quizzes').map((item) => item.slug), ['quiz-1', 'quiz-2']);
assert.deepEqual(sectionQuizzes(sectioned, 'english').map((item) => item.slug), ['quiz-3', 'quiz-4', 'quiz-5']);
assert.deepEqual(orderTagsByCount(sectionQuizzes(sectioned, 'english'), [{ slug: 'biology', name: 'Биология' }, { slug: 'missing', name: 'Нет' }]).map(({ slug, count }) => [slug, count]), [['biology', 1]]);

const dated = [
  quiz(1, { title: 'Бета', publication_date: '2026-02-01' }),
  quiz(2, { title: 'Альфа', publication_date: '2026-02-01' }),
  quiz(3, { title: 'Ошибка даты', publication_date: '2026-99-99' }),
  quiz(4, { title: 'Старая', publication_date: '2025-01-01' })
];
assert.deepEqual(sortQuizzes(dated, 'date', 'down').map((item) => item.title), ['Альфа', 'Бета', 'Старая', 'Ошибка даты']);
assert.deepEqual(sortQuizzes(dated, 'date', 'up').map((item) => item.title), ['Старая', 'Альфа', 'Бета', 'Ошибка даты']);
assert.deepEqual(sortQuizzes(dated, 'title', 'down').map((item) => item.title), ['Альфа', 'Бета', 'Ошибка даты', 'Старая']);
assert.deepEqual(sortQuizzes(dated, 'title', 'up').map((item) => item.title), ['Старая', 'Ошибка даты', 'Бета', 'Альфа']);

const timed = [
  quiz(1, { title: 'Викторина A', publication_date: '2026-07-22T10:00:00+03:00' }),
  quiz(2, { title: 'Викторина B', publication_date: '2026-07-22T15:00:00+03:00' }),
  quiz(3, { title: 'Викторина C', publication_date: '2026-07-21T18:00:00+03:00' }),
  quiz(4, { title: 'Я — совпадение', publication_date: '2026-07-22T15:00:00+03:00' }),
  quiz(5, { title: 'А — совпадение', publication_date: '2026-07-22T15:00:00+03:00' }),
  quiz(6, { title: 'Старая запись без времени', publication_date: '2026-07-20' })
];
assert.deepEqual(sortQuizzes(timed.slice(0, 3), 'date', 'down').map((item) => item.title), ['Викторина B', 'Викторина A', 'Викторина C']);
assert.deepEqual(sortQuizzes(timed.slice(0, 3), 'date', 'up').map((item) => item.title), ['Викторина C', 'Викторина A', 'Викторина B']);
assert.deepEqual(sortQuizzes(timed, 'date', 'down').map((item) => item.title), ['А — совпадение', 'Викторина B', 'Я — совпадение', 'Викторина A', 'Викторина C', 'Старая запись без времени']);
assert.deepEqual(sortQuizzes(timed, 'date', 'up').map((item) => item.title), ['Старая запись без времени', 'Викторина C', 'Викторина A', 'А — совпадение', 'Викторина B', 'Я — совпадение']);
assert.equal(validDateValue('2026-07-22'), Date.parse('2026-07-22T00:00:00Z'));
assert.equal(validDateValue('2026-07-22T15:00:00+03:00'), Date.parse('2026-07-22T15:00:00+03:00'));
assert.equal(validDateValue('2026-07-22T15:00:00'), null);
assert.equal(validDateValue('2026-07-22T15:00+03:00'), null);
assert.equal(validDateValue('2026-02-30T15:00:00+03:00'), null);

const difficulties = [
  quiz(1, { title: 'Средняя старая', difficulty: 'medium', publication_date: '2025-01-01' }),
  quiz(2, { title: 'Высокая', difficulty: 'high', publication_date: '2026-01-01' }),
  quiz(3, { title: 'Низкая', difficulty: 'low', publication_date: '2024-01-01' }),
  quiz(4, { title: 'Средняя новая', difficulty: 'medium', publication_date: '2026-02-01' })
];
assert.deepEqual(sortQuizzes(difficulties, 'difficulty', 'down').map((item) => item.difficulty), ['low', 'medium', 'medium', 'high']);
assert.deepEqual(sortQuizzes(difficulties, 'difficulty', 'up').map((item) => item.difficulty), ['high', 'medium', 'medium', 'low']);
assert.deepEqual(sortQuizzes(difficulties, 'difficulty', 'down').filter((item) => item.difficulty === 'medium').map((item) => item.title), ['Средняя новая', 'Средняя старая']);
assert.equal(sortTooltip('date', 'down'), 'Сначала новые');
assert.equal(sortTooltip('date', 'up'), 'Сначала старые');
assert.equal(sortTooltip('difficulty', 'down'), 'Сначала лёгкие');
assert.equal(sortTooltip('difficulty', 'up'), 'Сначала сложные');
assert.equal(sortTooltip('title', 'down'), 'От А до Я');
assert.equal(sortTooltip('title', 'up'), 'От Я до А');

assert.deepEqual(paginationItems(1, 1), []);
assert.deepEqual(paginationItems(1, 12), [1, 2, 'ellipsis', 12]);
assert.deepEqual(paginationItems(6, 12), [1, 'ellipsis', 5, 6, 7, 'ellipsis', 12]);
assert.deepEqual(paginationItems(12, 12), [1, 'ellipsis', 11, 12]);

const visible = new Set(['horses', 'biology']);
assert.deepEqual(getStateFromUrl('?tag=horses&sort=difficulty&direction=up&page=2', visible, 3), { section: 'quizzes', tag: 'horses', sort: 'difficulty', direction: 'up', page: 2 });
assert.deepEqual(getStateFromUrl('?section=english&tag=hidden&sort=popular&direction=sideways&page=999', visible, 3), { section: 'english', tag: 'all', sort: 'date', direction: 'down', page: 3 });
assert.deepEqual(getStateFromUrl('?section=unknown&page=-4', visible, 3), { section: 'quizzes', tag: 'all', sort: 'date', direction: 'down', page: 1 });
const url = buildUrl('https://example.test/quiz/quizzes.html?source=email&tag=horses', { section: 'quizzes', tag: 'all', sort: 'title', direction: 'up', page: 1 });
assert.equal(url, '/quiz/quizzes.html?source=email&sort=title&direction=up&page=1');

const paged = Array.from({ length: 30 }, (_, index) => quiz(index, { title: `Название ${String(29 - index).padStart(2, '0')}`, tags: index < 27 ? ['horses'] : ['biology'] }));
const filteredSorted = arrangeQuizzes(paged, 'horses', 'title', 'down');
assert.equal(filteredSorted.length, 27);
assert.equal(Math.ceil(filteredSorted.length / PAGE_SIZE), 3);
assert.deepEqual(filteredSorted.slice(0, PAGE_SIZE), sortQuizzes(filteredSorted, 'title', 'down').slice(0, PAGE_SIZE));
assert.deepEqual(filteredSorted.slice(PAGE_SIZE, PAGE_SIZE * 2), sortQuizzes(filteredSorted, 'title', 'down').slice(PAGE_SIZE, PAGE_SIZE * 2));
const filteredPageUrl = buildUrl('https://example.test/quizzes.html', { section: 'english', tag: 'horses', sort: 'title', direction: 'down', page: 2 });
assert.equal(filteredPageUrl, '/quizzes.html?section=english&tag=horses&sort=title&direction=down&page=2');
assert.deepEqual(getStateFromUrl('?section=english&tag=horses&sort=title&direction=down&page=2', visible, 3), { section: 'english', tag: 'horses', sort: 'title', direction: 'down', page: 2 });
assert.equal(quizPath('anatomy', 'https://tssrkt.github.io/quiz/quizzes.html'), '/quiz/v/anatomy/');
assert.equal(quizPath('anatomy', 'http://localhost:8000/quizzes.html'), '/v/anatomy/');
assert.equal(quizPath('horse-colors', 'https://tssrkt.github.io/quiz/quizzes.html?tag=horses&page=2'), '/quiz/v/horse-colors/');
assert.throws(() => quizPath('../anatomy', 'http://localhost:8000/quizzes.html'), TypeError);

console.log('catalog.test.js: все проверки пройдены');
