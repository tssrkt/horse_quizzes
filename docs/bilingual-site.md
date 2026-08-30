# RU / EN site architecture

Russian is the default locale and keeps its existing routes (`/`, `/quizzes.html`, `/contacts.html`, and `/v/<slug>/`). English static pages use the `/en/` prefix. The same build and GitHub Pages artifact contain both locales; assets and JavaScript are shared.

An English quiz keeps its internal JSON slug, for example `horse-breeds-en`. Its public route is derived exclusively from the explicit `source_quiz` relationship and is `/en/v/horse-breeds/`. Do not derive this relationship by removing `-en`. Publishing a valid English quiz automatically adds it to `data/catalog-en.json` and generates its public page.

`data/catalog.json` remains the complete RU-environment catalog, including the Russian “English for Equestrians” section and vocabulary quizzes. `data/catalog-en.json` contains only published `type: english` quizzes. Vocabulary quizzes and the redundant `english` tag are deliberately excluded from the EN catalog.

Static English page copy lives in `en/`. Shared dynamic UI localization lives in `js/i18n.js`; locale-aware business views remain in the common `js/quizzes.js`, `js/quiz.js`, and `js/common.js`. Add new UI strings to the shared localization layer rather than creating a second runtime.

The language switch uses explicit links only. Static pages map to their counterpart. A paired quiz maps between `/v/<source>/` and `/en/v/<source>/`; a Russian quiz without a published translation links safely to `/en/quizzes.html`. No browser-language, cookie, geolocation, or automatic redirect is used.

All URLs are built on `origin`, `base_path`, and `public_url` from `site.json` / `scripts/site_config.py`. Both `BASE_PATH=/` and repository subpaths are supported.
