(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.QuizUrlCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

  function siteRootUrl(currentUrl) {
    const url = new URL(currentUrl); url.search = ''; url.hash = '';
    const sharePath = url.pathname.match(/^(.*\/)v\/[a-z0-9]+(?:-[a-z0-9]+)*\/(?:index\.html)?$/);
    url.pathname = sharePath ? sharePath[1] : url.pathname.replace(/[^/]*$/, '');
    return url.href;
  }

  function siteUrl(path, currentUrl) { return new URL(path, siteRootUrl(currentUrl)).href; }

  function quizPath(slug, currentUrl) {
    if (!SLUG_PATTERN.test(slug || '')) throw new TypeError('Некорректный slug викторины');
    return new URL(`v/${encodeURIComponent(slug)}/`, siteRootUrl(currentUrl)).pathname;
  }

  return { SLUG_PATTERN, siteRootUrl, siteUrl, quizPath };
});
