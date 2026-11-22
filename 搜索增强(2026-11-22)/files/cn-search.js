// Chinese character-name support for the viewer search/autocomplete.
(function () {
    if (typeof CHAR === "undefined" || typeof CN_CHAR_ALIASES === "undefined") return;

    function addAliases(nameObj, values) {
        if (!nameObj || !values) return;
        if (!Array.isArray(nameObj.japAlias)) nameObj.japAlias = [];
        for (const value of values) {
            if (value && !nameObj.japAlias.includes(value)) nameObj.japAlias.push(value);
        }
    }


    // Search aliases for character form suffixes such as 新春/生命樹の祝福/パラレル学園.
    const SERIES_ALIASES = {
        "生命樹の祝福": ["生命树的祝福", "生命树祝福"],
        "新春": ["新春", "新年"],
        "パラレル学園": ["平行学园", "学园", "校园"],
        "水着": ["泳装"],
        "クリスマス": ["圣诞节"],
        "バレンタイン": ["情人节"],
        "ジューンブライド": ["六月新娘"],
        "ハロウィン": ["万圣节"],
        "浴衣": ["浴衣"],
        "メイド": ["女仆"],
        "式典の礼装": ["典礼礼服"],
        "深層目録": ["深层记录"],
        "10th Anniversary": ["十周年"],
        "ひな祭り": ["女儿节"]
    };
    const seriesTerm = (jaName) => {
        const match = String(jaName || "").match(/[（(]([^()（）]*)[）)]$/);
        return match ? match[1].trim() : "";
    };
    const seriesAliases = new Set();
    for (const values of Object.values(SERIES_ALIASES)) {
        for (const value of values) seriesAliases.add(value);
    }
    window.CN_SERIES_ALIASES = seriesAliases;

    function addSeriesAliases(nameObj, jaName) {
        if (!nameObj) return;
        const suffix = seriesTerm(jaName);
        if (!suffix) return;
        const values = [suffix].concat(SERIES_ALIASES[suffix] || []);
        addAliases(nameObj, values);
    }

    for (const key in CHAR) {
        const entry = CHAR[key];
        if (!entry || !entry.base || !entry.base.name) continue;
        const baseJa = entry.base.name.jap;
        addAliases(entry.base.name, CN_CHAR_ALIASES[baseJa] || CN_CHAR_ALIASES[baseJa.replace(/\(.*\)$/, "")] || []);
        if (entry.form) {
            for (const formKey in entry.form) {
                const form = entry.form[formKey];
                if (!form || !form.name) continue;
                const formJa = form.name.jap;
                addAliases(form.name, CN_CHAR_ALIASES[formJa] || CN_CHAR_ALIASES[baseJa] || CN_CHAR_ALIASES[baseJa.replace(/\(.*\)$/, "")] || []);
                addSeriesAliases(form.name, formJa);
            }
        }
    }

    // Normalized lookup used by search.js for exact Chinese searches.
    window.CN_NAME_LOOKUP_NORM = {};
    const normalize = (s) => String(s).toLowerCase().replace(/\s/g, "");
    for (const [key, values] of Object.entries(CN_NAME_LOOKUP)) {
        const normalized = normalize(key);
        window.CN_NAME_LOOKUP_NORM[normalized] = (window.CN_NAME_LOOKUP_NORM[normalized] || []).concat(values);
    }
})();
