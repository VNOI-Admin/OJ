from django.test import SimpleTestCase
from lxml import html

from . import fragment_tree_to_str, fragments_to_tree, get_cleaner, markdown, markdown_client, markdown_client_configs

MATHML_N = """\
<math xmlns="http://www.w3.org/1998/Math/MathML">
<semantics>
<mi>N</mi>
<annotation encoding="application/x-tex">N</annotation>
</semantics>
</math>
"""

MATHML_CHUDNOVSKY = r"""
<math xmlns="http://www.w3.org/1998/Math/MathML"
      alttext="{\displaystyle {\frac {1}{\pi }}=12\sum _{k=0}^{\infty }{\frac {(-1)^{k}(6k)!(545140134k+13591409)}{(3k)!(k!)^{3}\left(640320\right)^{3k+3/2}}}}">
  <semantics>
    <mrow class="MJX-TeXAtom-ORD">
      <mstyle displaystyle="true" scriptlevel="0">
        <mrow class="MJX-TeXAtom-ORD">
          <mfrac>
            <mn>1</mn>
            <mi>π<!-- π --></mi>
          </mfrac>
        </mrow>
        <mo>=</mo>
        <mn>12</mn>
        <munderover>
          <mo>∑<!-- ∑ --></mo>
          <mrow class="MJX-TeXAtom-ORD">
            <mi>k</mi>
            <mo>=</mo>
            <mn>0</mn>
          </mrow>
          <mrow class="MJX-TeXAtom-ORD">
            <mi mathvariant="normal">∞<!-- ∞ --></mi>
          </mrow>
        </munderover>
        <mrow class="MJX-TeXAtom-ORD">
          <mfrac>
            <mrow>
              <mo stretchy="false">(</mo>
              <mo>−<!-- − --></mo>
              <mn>1</mn>
              <msup>
                <mo stretchy="false">)</mo>
                <mrow class="MJX-TeXAtom-ORD">
                  <mi>k</mi>
                </mrow>
              </msup>
              <mo stretchy="false">(</mo>
              <mn>6</mn>
              <mi>k</mi>
              <mo stretchy="false">)</mo>
              <mo>!</mo>
              <mo stretchy="false">(</mo>
              <mn>545140134</mn>
              <mi>k</mi>
              <mo>+</mo>
              <mn>13591409</mn>
              <mo stretchy="false">)</mo>
            </mrow>
            <mrow>
              <mo stretchy="false">(</mo>
              <mn>3</mn>
              <mi>k</mi>
              <mo stretchy="false">)</mo>
              <mo>!</mo>
              <mo stretchy="false">(</mo>
              <mi>k</mi>
              <mo>!</mo>
              <msup>
                <mo stretchy="false">)</mo>
                <mrow class="MJX-TeXAtom-ORD">
                  <mn>3</mn>
                </mrow>
              </msup>
              <msup>
                <mrow>
                  <mo>(</mo>
                  <mn>640320</mn>
                  <mo>)</mo>
                </mrow>
                <mrow class="MJX-TeXAtom-ORD">
                  <mn>3</mn>
                  <mi>k</mi>
                  <mo>+</mo>
                  <mn>3</mn>
                  <mrow class="MJX-TeXAtom-ORD">
                    <mo>/</mo>
                  </mrow>
                  <mn>2</mn>
                </mrow>
              </msup>
            </mrow>
          </mfrac>
        </mrow>
      </mstyle>
    </mrow>
    <annotation encoding="application/x-tex">{\displaystyle {\frac {1}{\pi }}=12\sum _{k=0}^{\infty }{\frac {(-1)^{k}(6k)!(545140134k+13591409)}{(3k)!(k!)^{3}\left(640320\right)^{3k+3/2}}}}</annotation>
  </semantics>
</math>
"""  # noqa: E501


class TestMarkdown(SimpleTestCase):
    BLEACHED_STYLE = 'problem'
    UNBLEACHED_STYLE = 'problem-full'

    def test_bleach(self):
        self.assertHTMLEqual(markdown('<script>void(0)</script>', self.BLEACHED_STYLE),
                             '&lt;script&gt;void(0)&lt;/script&gt;')
        #  style is not allowed
        self.assertHTMLEqual(markdown('<img style="display: block; margin: 0 auto">', self.BLEACHED_STYLE),
                             '<p><img></p>')
        self.assertHTMLEqual(markdown('<style>a { color: red; }</style>', self.BLEACHED_STYLE),
                             '<p>&lt;style&gt;a { color: red; }&lt;/style&gt;</p>')

    def test_bleach_mathml(self):
        self.assertHTMLEqual(markdown(MATHML_N, self.BLEACHED_STYLE), MATHML_N)
        cleaner = get_cleaner(self.BLEACHED_STYLE, None)
        self.assertHTMLEqual(cleaner.clean(MATHML_CHUDNOVSKY), MATHML_CHUDNOVSKY)

    def test_no_bleach(self):
        self.assertHTMLEqual(markdown('<script>void(0)</script>', self.UNBLEACHED_STYLE),
                             '<script>void(0)</script>')

    def test_post_process(self):
        self.assertHTMLEqual(markdown('<img src="test.png">', self.UNBLEACHED_STYLE, lazy_load=True),
                             '<p><noscript><img src="test.png"></noscript>'
                             '<img src="/static/blank.gif" data-src="test.png" class="unveil"></p>')


class TestMarkdownClient(SimpleTestCase):
    BLEACHED_STYLE = 'problem'
    UNBLEACHED_STYLE = 'problem-full'

    def test_placeholder_escapes_raw_markdown(self):
        out = str(markdown_client('# Hi <script>alert(1)</script>\nline2 & "quotes"', 'comment'))
        self.assertHTMLEqual(
            out,
            '<div class="md-content" data-md-style="comment">'
            '# Hi &lt;script&gt;alert(1)&lt;/script&gt;\nline2 &amp; &quot;quotes&quot;</div>',
        )

    def test_none_input(self):
        self.assertHTMLEqual(str(markdown_client(None, 'comment')),
                             '<div class="md-content" data-md-style="comment"></div>')

    def test_unknown_style_wraps(self):
        out = str(markdown_client('**b**', 'no-such-style'))
        self.assertHTMLEqual(out, '<div class="md-content" data-md-style="no-such-style">**b**</div>')

    def test_admin_style_falls_back_to_server_render(self):
        self.assertHTMLEqual(str(markdown_client('# Title', self.UNBLEACHED_STYLE)), '<h3>Title</h3>')

    def test_configs(self):
        configs = markdown_client_configs()
        self.assertNotIn(self.UNBLEACHED_STYLE, configs)
        self.assertNotIn('flatpage', configs)
        self.assertIn('comment', configs)
        self.assertEqual(configs['comment']['html'], False)
        self.assertEqual(configs['comment']['allowStyle'], False)
        self.assertEqual(configs[self.BLEACHED_STYLE]['html'], True)
        self.assertEqual(configs[self.BLEACHED_STYLE]['allowStyle'], True)
        self.assertIn('img', configs['comment']['tags'])
        self.assertIn('href', configs['comment']['attrs'])
        self.assertEqual(configs['comment']['attrs'], sorted(configs['comment']['attrs']))

    def test_get_cleaner_does_not_mutate_styles(self):
        # Regression: get_cleaner used to mutate the shared MARKDOWN_STYLES dict, which
        # corrupted markdown_client_configs() output (allowStyle False, MathML-baked tags)
        # for any style read after a staff server-side render.
        markdown('**x**', self.BLEACHED_STYLE)
        configs = markdown_client_configs()
        self.assertEqual(configs[self.BLEACHED_STYLE]['allowStyle'], True)
        self.assertNotIn('math', configs[self.BLEACHED_STYLE]['tags'])


class TestFragmentUtils(SimpleTestCase):
    def test_simple(self):
        tree = fragments_to_tree('<p>a</p><p>b</p>')
        self.assertIsInstance(tree, html.HtmlElement)
        self.assertEqual(len(tree.getchildren()), 2)

        self.assertIsInstance(tree[0], html.HtmlElement)
        self.assertEqual(tree[0].tag, 'p')
        self.assertEqual(tree[0].text, 'a')

        self.assertIsInstance(tree[1], html.HtmlElement)
        self.assertEqual(tree[1].tag, 'p')
        self.assertEqual(tree[1].text, 'b')

        self.assertHTMLEqual(fragment_tree_to_str(tree), '<p>a</p><p>b</p>')

    def test_text_prefix(self):
        tree = fragments_to_tree('z<p>a</p><p>b</p>')
        self.assertIsInstance(tree, html.HtmlElement)
        self.assertEqual(len(tree.getchildren()), 2)
        self.assertEqual(tree.text, 'z')

        self.assertHTMLEqual(fragment_tree_to_str(tree), 'z<p>a</p><p>b</p>')
