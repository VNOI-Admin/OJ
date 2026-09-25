// jsdom harness for ../markdown-client.js. Loads the actual shipped file plus the vendored libs
// from ../vendor (window.eval = top-level script semantics, so no npm copies are involved and
// the test cannot drift from production). Run: npm ci && npm test. Exits non-zero on failure.

const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&#34;');

// Mirrors markdown_client_configs() output (dmoj/settings.py whitelists): user tier escapes raw
// HTML and forbids inline style; staff tier passes raw HTML through and allows inline style.
const CONFIGS = {
    comment: {html: false, allowStyle: false,
        tags: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'b', 'i', 'strong', 'em', 'tt', 'del', 'kbd', 's', 'abbr', 'cite',
            'mark', 'q', 'samp', 'small', 'u', 'var', 'wbr', 'dfn', 'ruby', 'rb', 'rp', 'rt', 'rtc', 'sub', 'sup',
            'time', 'data', 'p', 'br', 'pre', 'span', 'div', 'blockquote', 'code', 'hr', 'ul', 'ol', 'li', 'dd',
            'dl', 'dt', 'address', 'section', 'details', 'summary', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th',
            'td', 'caption', 'colgroup', 'col', 'img', 'audio', 'video', 'source', 'a', 'strike', 'noscript',
            'center', 'object', 'iframe'],
        attrs: ['align', 'allow', 'alt', 'autoplay', 'class', 'colspan', 'controls', 'crossorigin', 'data',
            'data-src', 'datetime', 'height', 'href', 'id', 'loop', 'muted', 'poster', 'preload', 'rowspan', 'src',
            'srcset', 'title', 'type', 'value', 'width']},
    problem: {html: true, allowStyle: true,
        tags: null, attrs: null},
};
CONFIGS.problem.tags = CONFIGS.comment.tags;
CONFIGS.problem.attrs = CONFIGS.comment.attrs;

const results = [];
function check(name, ok, ctx) {
    results.push([!!ok, name]);
    if (!ok) console.error('FAIL ' + name + (ctx ? '\n  GOT: ' + String(ctx).slice(0, 300) : ''));
}

const blocks = [
    ['comment', '# Hello **world** [user:someone] `code`'],
    ['comment', '<img src=x onerror=alert(1)>\n\n<script>alert(2)</script>'],
    ['comment', '>! spoiler *inside*\n>! second line\n\nnormal'],
    ['comment', '| a | b |\n|---|---|\n| 1 | 2 |\n\n[link](http://x.com)'],
    ['comment', '```python\nx = 1 < 2\n```'],
    ['comment', '~a *b* c~ and $$\\begin{bmatrix} a & b \\\\ c & d\\end{bmatrix}$$ and ~~gone~~'],
    ['problem', '<div style="color:green" onclick="alert(3)">staff html</div>\n\n![pic](http://img)'],
    ['problem', '<script>alert(4)</script> ~x_{i}^2~'],
    ['nonexistent-style', '<script>alert(5)</script> **bold**'],
];
const page = '<!DOCTYPE html><html><body>' +
    '<script id="md-sanitizer-configs" type="application/json">' + JSON.stringify(CONFIGS) + '</script>' +
    blocks.map(([s, md]) => '<div class="md-content" data-md-style="' + s + '">' + esc(md) + '</div>').join('\n') +
    '</body></html>';

const {window} = new JSDOM(page, {runScripts: 'outside-only'});
for (const f of ['vendor/markdown-it.min.js', 'vendor/purify.min.js', 'vendor/highlight.min.js', 'markdown-client.js']) {
    window.eval(fs.readFileSync(path.join(__dirname, '..', f), 'utf8'));
}
let fetchCount = 0;
window.fetch = () => {
    fetchCount++;
    return Promise.resolve({ok: true, json: () => Promise.resolve({
        'user:someone': '<span class="rating"><a href="/user/someone">someone</a></span>',
    })});
};

window.eval('MarkdownClient.renderAll(document)');
setTimeout(() => {
    const d = window.document;
    const b = [...d.querySelectorAll('.md-content')];
    const html = i => b[i].innerHTML;

    check('basic render + h1->h3 demote', html(0).startsWith('<h3>Hello <strong>world</strong>'), html(0));
    check('user tier: no live img/script from XSS', !b[1].querySelector('img') && !b[1].querySelector('script'), html(1));
    check('user tier: XSS source escaped to text', html(1).includes('&lt;img src=x'), html(1));
    check('spoiler -> blockquote.spoiler, markdown inside', html(2).includes('<blockquote class="spoiler">') && html(2).includes('<em>inside</em>'), html(2));
    check('table gets class=table', html(3).includes('<table class="table">'), html(3));
    check('rel=nofollow stripped end-to-end (server parity)', !html(3).includes('rel='), html(3));
    check('fenced code highlighted, hljs spans survive purge', html(4).includes('hljs-number'), html(4));
    check('math: ~a *b* c~ not split by emphasis', html(5).includes('~a *b* c~') && !html(5).includes('<em>'), html(5));
    check('math: matrix \\\\ row separator preserved', html(5).includes('b \\\\ c'), html(5));
    check('math: span lives in a single text node (MathJax-matchable)', (() => {
        const n = b[5].querySelector('p').firstChild;
        return n.nodeType === 3 && n.nodeValue.includes('~a *b* c~') && n.nodeValue.includes('\\\\');
    })(), '');
    check('~~strikethrough~~ still works', html(5).includes('<s>gone</s>'), html(5));
    check('staff: raw div + inline style kept, onclick stripped',
        html(6).includes('<div style="color:green">staff html</div>') && !html(6).includes('onclick'), html(6));
    check('staff: img kept', !!b[6].querySelector('img[src="http://img"]'), html(6));
    check('staff: script stripped, tilde math intact', !b[7].querySelector('script') && html(7).includes('~x_{i}^2~'), html(7));
    check('unknown style -> strict fallback escapes script', !b[8].querySelector('script') && html(8).includes('&lt;script&gt;'), html(8));
    check('all blocks marked md-rendered', d.querySelectorAll('.md-content.md-rendered').length === blocks.length);
    check('images lazy-loaded (F3)', b[6].querySelector('img').getAttribute('loading') === 'lazy', html(6));
    check('exactly one batched reference fetch', fetchCount === 1, 'count=' + fetchCount);
    check('reference token replaced with server html', html(0).includes('<a href="/user/someone">someone</a>'), html(0));

    const fails = results.filter(([ok]) => !ok);
    console.log((results.length - fails.length) + '/' + results.length + ' assertions pass');
    process.exit(fails.length ? 1 : 0);
}, 50);
