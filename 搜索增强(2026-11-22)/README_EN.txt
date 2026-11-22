Flower Knight Girl Viewer - Chinese and series search enhancement
Snapshot date: 2026-11-22

This package adds:
- Chinese character-name search (canonical names and aliases)
- Chinese/Japanese form-series search:
  - 生命树的祝福 / 生命树祝福
  - 新春 / 新年
  - 平行学园 / 学园 / 校园
  - and common form series such as 泳装, 圣诞节, 情人节, 六月新娘,
    万圣节, 浴衣, 女仆, 典礼礼服, 深层记录, 十周年, 女儿节
- Search autocomplete keeps a series term selected as a group search instead
  of replacing it with one character's Japanese form name.

Requirements:
- Flower Knight Girl Viewer 1.1 package.nw layout
- Python 3.10+
- Close the viewer before installing

Install (from this directory):
  python install_cn_search.py "/path/to/package.nw"

The installer:
- backs up the original search.js, autocomplete.js and viewer HTML
- copies the bundled JS files into data/scripts/
- inserts the cn-search.js script tag after meta.js
- changes the Character placeholder to mention 系列

It does not modify scenes, images, audio, or translations.

Files:
- files/cn-names.js       generated Chinese name/alias map
- files/cn-search.js      injects Chinese names and form-series aliases
- files/search.js         Chinese lookup and Chinese series matching
- files/autocomplete.js   series-aware autocomplete selection
