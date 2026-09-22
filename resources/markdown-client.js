// Client-side markdown rendering for placeholders emitted by the `markdown_client`
// Jinja filter (judge/jinja2/markdown/__init__.py). Renders raw markdown with markdown-it and
// sanitizes with DOMPurify per trust tier, then replaces the placeholder content.
//
// Per-tier sanitizer configs come from the server (single source of truth): base.html emits
// `#md-sanitizer-configs` JSON via markdown_client_configs(), derived from the same Bleach settings
// the server uses, so client and server allow-lists cannot drift. If that JSON is missing/malformed,
// each block falls back to the strict user-tier config below (fail toward strict, never toward XSS).
//
// Deferred (see .review/client-side-markdown-rendering-analysis.md): anti-flash; exact per-tag
// attribute parity; per-domain nofollow exclusion. (Math-span protect for ~..~/$$..$$ IS implemented
// in applyDialectRules — it keeps LaTeX contents raw so \\, *, _ aren't mangled by markdown.)

(function () {
    'use strict';

    // Fail closed: without the sanitizer (or renderer) we must NOT render untrusted HTML.
    // Leaving the placeholder untouched keeps the raw (escaped) markdown visible as plain text.
    if (typeof window.DOMPurify === 'undefined' || typeof window.markdownit === 'undefined') {
        return;
    }

    // Syntax-highlight fenced code with highlight.js (server used Pygments; classes differ, so the
    // highlight.js theme CSS is loaded alongside). Falls back to plain escaped code when the language
    // is unknown or highlight.js isn't loaded.
    function highlight(code, lang) {
        var hljs = window.hljs;
        if (hljs && lang && hljs.getLanguage(lang)) {
            try {
                return '<pre class="hljs"><code>' +
                    hljs.highlight(code, {language: lang, ignoreIllegals: true}).value +
                    '</code></pre>';
            } catch (e) { /* fall through to default escaping */ }
        }
        return '';
    }

    // Dialect rules matching the server markdown2 fork's post-processing. Applied to every renderer.
    function applyDialectRules(md) {
        // inc_header(+2): headings are demoted by two levels (h1 -> h3), capped at h6.
        md.core.ruler.push('inc_header', function (state) {
            state.tokens.forEach(function (t) {
                if (t.type === 'heading_open' || t.type === 'heading_close') {
                    var level = parseInt(t.tag.slice(1), 10) + 2;
                    t.tag = 'h' + (level > 6 ? 6 : level);
                }
            });
        });

        // add_table_class: <table> -> <table class="table">.
        var defaultTableOpen = md.renderer.rules.table_open ||
            function (tokens, idx, options, env, self) { return self.renderToken(tokens, idx, options); };
        md.renderer.rules.table_open = function (tokens, idx, options, env, self) {
            tokens[idx].attrJoin('class', 'table');
            return defaultTableOpen(tokens, idx, options, env, self);
        };

        // nofollow: add rel="nofollow" to links. NOTE: the server excludes settings.NOFOLLOW_EXCLUDED
        // domains; here we nofollow all links (stricter) — refine later if needed.
        var defaultLinkOpen = md.renderer.rules.link_open ||
            function (tokens, idx, options, env, self) { return self.renderToken(tokens, idx, options); };
        md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
            tokens[idx].attrSet('rel', 'nofollow');
            return defaultLinkOpen(tokens, idx, options, env, self);
        };

        // spoiler: a blockquote whose lines start with `>!` becomes <blockquote class="spoiler">
        // (StackOverflow-style hidden blocks). Mirrors the markdown2 fork's `spoiler` extra.
        md.block.ruler.before('blockquote', 'spoiler', function (state, startLine, endLine, silent) {
            var pos = state.bMarks[startLine] + state.tShift[startLine];
            var max = state.eMarks[startLine];
            if (pos + 1 >= max) return false;
            if (state.src.charCodeAt(pos) !== 0x3E /* > */) return false;
            if (state.src.charCodeAt(pos + 1) !== 0x21 /* ! */) return false;
            if (silent) return true;

            var oldBMarks = [], oldTShift = [], oldSCount = [];
            var oldParentType = state.parentType, oldLineMax = state.lineMax;
            var nextLine = startLine;
            for (; nextLine < endLine; nextLine++) {
                var p = state.bMarks[nextLine] + state.tShift[nextLine];
                var m = state.eMarks[nextLine];
                if (p >= m) break;   // blank line ends the spoiler
                if (state.src.charCodeAt(p) !== 0x3E || state.src.charCodeAt(p + 1) !== 0x21) break;
                p += 2;
                if (p < m && state.src.charCodeAt(p) === 0x20) p++;   // one optional space after >!
                oldBMarks.push(state.bMarks[nextLine]);
                oldTShift.push(state.tShift[nextLine]);
                oldSCount.push(state.sCount[nextLine]);
                state.bMarks[nextLine] = p;
                state.tShift[nextLine] = 0;
                state.sCount[nextLine] = 0;
            }
            state.lineMax = nextLine;
            state.parentType = 'blockquote';
            var openToken = state.push('spoiler_open', 'blockquote', 1);
            openToken.attrSet('class', 'spoiler');
            openToken.map = [startLine, nextLine];
            state.md.block.tokenize(state, startLine, nextLine);
            state.push('spoiler_close', 'blockquote', -1);
            state.lineMax = oldLineMax;
            state.parentType = oldParentType;
            state.line = nextLine;
            for (var i = 0; i < oldBMarks.length; i++) {
                state.bMarks[startLine + i] = oldBMarks[i];
                state.tShift[startLine + i] = oldTShift[i];
                state.sCount[startLine + i] = oldSCount[i];
            }
            return true;
        });

        // Math-span protect: capture ~..~ (inline) and $$..$$ (display, incl. multiline matrices) RAW,
        // so markdown-it does NOT process their contents (\\, *, _, etc.). Mirrors the server markdown2
        // `latex` extra which hashes these spans. Re-emitted unchanged so the site's MathJax (which uses
        // the ~ and $$ delimiters) renders them. Runs before `escape` so `\\` (matrix row breaks) and
        // `\,` survive; `~~` is left to the strikethrough rule. Without this, e.g. `~a *b* c~` splits into
        // <em> and `$$..\\..$$` collapses `\\`->`\`, breaking bmatrix/cases/aligned.
        md.inline.ruler.before('escape', 'math_protect', function (state, silent) {
            var src = state.src, pos = state.pos, ch = src.charCodeAt(pos), open;
            if (ch === 0x7E /* ~ */) {
                if (src.charCodeAt(pos + 1) === 0x7E) return false;   // ~~ = strikethrough
                open = '~';
            } else if (ch === 0x24 /* $ */ && src.charCodeAt(pos + 1) === 0x24) {
                open = '$$';
            } else {
                return false;
            }
            var start = pos + open.length, end = src.indexOf(open, start);
            if (end === -1 || end === start) return false;
            if (!silent) {
                var t = state.push('math', '', 0);
                t.content = src.slice(start, end);
                t.markup = open;
            }
            state.pos = end + open.length;
            return true;
        });
        md.renderer.rules.math = function (tokens, idx) {
            return tokens[idx].markup + md.utils.escapeHtml(tokens[idx].content) + tokens[idx].markup;
        };
    }

    function createRenderer(allowHtml) {
        // html mirrors the server safe_mode: user tier (html:false) escapes raw HTML in the source;
        // staff tier (html:true) passes it through for DOMPurify to sanitize.
        // linkify/typographer off: the fork does not auto-link bare URLs or smart-quote.
        var md = window.markdownit({html: allowHtml, linkify: false, typographer: false, highlight: highlight});
        applyDialectRules(md);
        return md;
    }

    var mdUser = createRenderer(false);   // safe_mode=True styles
    var mdStaff = createRenderer(true);   // safe_mode=False styles (raw HTML passes through)

    // Strict user-tier fallback (used when the server config JSON is missing or a style is unknown).
    // Mirrors BLEACH_USER_SAFE_TAGS / BLEACH_USER_SAFE_ATTRS with styles:False.
    var FALLBACK = {
        md: mdUser,
        purify: {
            ALLOWED_TAGS: [
                'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'b', 'i', 'strong', 'em', 'tt', 'del', 'kbd', 's', 'abbr', 'cite', 'mark', 'q', 'samp', 'small',
                'u', 'var', 'wbr', 'dfn', 'ruby', 'rb', 'rp', 'rt', 'rtc', 'sub', 'sup', 'time', 'data',
                'p', 'br', 'pre', 'span', 'div', 'blockquote', 'code', 'hr',
                'ul', 'ol', 'li', 'dd', 'dl', 'dt', 'address', 'section', 'details', 'summary',
                'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
                'img', 'audio', 'video', 'source',
                'a', 'strike', 'noscript', 'center', 'object', 'iframe',
            ],
            ALLOWED_ATTR: [
                'id', 'class', 'data', 'height', 'width', 'align',
                'src', 'data-src', 'alt', 'title', 'href', 'allow',
                'datetime', 'value', 'colspan', 'rowspan',
                'autoplay', 'controls', 'crossorigin', 'muted', 'loop', 'preload', 'poster', 'srcset', 'type',
            ],
            FORBID_ATTR: ['style'],
            ALLOW_DATA_ATTR: true,
        },
    };

    // Build per-style {md, purify} from the server-emitted whitelist (single source of truth).
    function buildStyles() {
        var styles = {};
        try {
            var el = document.getElementById('md-sanitizer-configs');
            if (!el) return styles;
            var raw = JSON.parse(el.textContent);
            Object.keys(raw).forEach(function (name) {
                var c = raw[name];
                var purify = {
                    ALLOWED_TAGS: c.tags,
                    ALLOWED_ATTR: c.attrs.slice(),
                    ALLOW_DATA_ATTR: true,
                };
                if (c.allowStyle) {
                    purify.ALLOWED_ATTR.push('style');   // staff tier: inline CSS allowed (styles:True)
                } else {
                    purify.FORBID_ATTR = ['style'];      // user tier: no inline CSS
                }
                styles[name] = {md: c.html ? mdStaff : mdUser, purify: purify};
            });
        } catch (e) { /* fall back to FALLBACK for every style */ }
        return styles;
    }

    var STYLES = buildStyles();

    function styleFor(name) {
        return STYLES[name] || FALLBACK;
    }

    function renderOne(el) {
        try {
            var conf = styleFor(el.getAttribute('data-md-style') || 'comment');
            // textContent decodes the entity-escaped markdown back to its original source.
            // Sanitize BEFORE it touches the live DOM.
            el.innerHTML = window.DOMPurify.sanitize(conf.md.render(el.textContent), conf.purify);
            // Post-sanitize replacement for the old server-side lazy_load (unveil) step.
            var imgs = el.querySelectorAll('img:not([loading])');
            for (var i = 0; i < imgs.length; i++) {
                imgs[i].setAttribute('loading', 'lazy');
            }
            el.classList.add('md-rendered');
        } catch (e) {
            // Leave the raw text in place on any failure (fail closed).
            if (window.console && console.error) {
                console.error('[markdown-client] render failed', e);
            }
        }
    }

    // References: after rendering, resolve [user:x]/[ruser:x] tokens across all freshly-rendered
    // blocks in ONE batched request, then replace them together (no per-token round-trips).
    var REFERENCE_URL = '/widgets/references';
    var REFERENCE_RE = /\[(r?user):(\w+)\]/g;

    function collectReferences(elements) {
        var tokens = {};
        var nodes = [];
        for (var e = 0; e < elements.length; e++) {
            var walker = document.createTreeWalker(elements[e], NodeFilter.SHOW_TEXT, null);
            var node;
            while ((node = walker.nextNode())) {
                var text = node.nodeValue;
                if (!text || text.indexOf('[') === -1) continue;
                REFERENCE_RE.lastIndex = 0;
                var m, found = false;
                while ((m = REFERENCE_RE.exec(text))) {
                    tokens[m[1] + ':' + m[2]] = true;
                    found = true;
                }
                if (found) nodes.push(node);
            }
        }
        return {tokens: Object.keys(tokens), nodes: nodes};
    }

    function replaceReferences(nodes, htmlMap) {
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node.parentNode) continue;
            var text = node.nodeValue;
            var frag = document.createDocumentFragment();
            var last = 0, m;
            REFERENCE_RE.lastIndex = 0;
            while ((m = REFERENCE_RE.exec(text))) {
                if (m.index > last) {
                    frag.appendChild(document.createTextNode(text.slice(last, m.index)));
                }
                var html = htmlMap[m[1] + ':' + m[2]];
                if (html) {
                    var tmp = document.createElement('span');
                    tmp.innerHTML = html;   // trusted, server-generated link HTML
                    while (tmp.firstChild) frag.appendChild(tmp.firstChild);
                } else {
                    frag.appendChild(document.createTextNode(m[0]));   // leave unresolved token as-is
                }
                last = m.index + m[0].length;
            }
            if (last < text.length) {
                frag.appendChild(document.createTextNode(text.slice(last)));
            }
            node.parentNode.replaceChild(frag, node);
        }
    }

    function resolveReferences(elements) {
        var collected = collectReferences(elements);
        if (!collected.tokens.length) return;
        fetch(REFERENCE_URL + '?refs=' + encodeURIComponent(collected.tokens.join(',')), {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (map) { replaceReferences(collected.nodes, map); })
            .catch(function () { /* leave tokens in place on failure */ });
    }

    function renderAll(root) {
        var scope = root || document;
        var nodes = scope.querySelectorAll('.md-content:not(.md-rendered)');
        for (var i = 0; i < nodes.length; i++) {
            renderOne(nodes[i]);
        }
        // Typeset math AFTER our render, so MathJax sees the rendered ~..~/$$..$$ (not the raw
        // placeholder). Covers SSR'd content whose math would otherwise race MathJax's own pass.
        if (nodes.length && window.MathJax && window.MathJax.typesetPromise) {
            try { window.MathJax.typesetPromise(Array.prototype.slice.call(nodes)); } catch (e) { /* ignore */ }
        }
        resolveReferences(nodes);
    }

    // Exposed so AJAX-injected content (e.g. the lazy-loaded comment list) can be rendered
    // after insertion — the DOMContentLoaded pass only covers markup in the original page.
    window.MarkdownClient = {renderAll: renderAll, render: renderOne};

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { renderAll(); });
    } else {
        renderAll();
    }
})();
