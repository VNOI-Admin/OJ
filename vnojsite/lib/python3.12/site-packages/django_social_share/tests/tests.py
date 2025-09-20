from django.template import Context, Template
from django.test import TestCase, RequestFactory


class TemplateTagsTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.context = Context({
            'url': 'http://example.com',
            'text': 'example',
            'subject': 'Example Domain',
            'link_text':'',
            'link_class': 'example_class',
            'request': self.factory.get('/')
        })


    def test_twitter(self):
        template = Template("{% load social_share %} {% post_to_twitter text url %}")
        result = template.render(self.context)
        expected = ' <div class="tweet-this">\n    <a href="https://twitter.com/intent/tweet?text=example%20http%3A//example.com" class="meta-act-link meta-tweet " target="_blank">Post to Twitter</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_facebook(self):
        template = Template("{% load social_share %} {% post_to_facebook url text %}")
        result = template.render(self.context)
        expected = ' <div class="facebook-this">\n    <a href="https://www.facebook.com/sharer/sharer.php?u=http%3A//example.com" class="" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_gplus(self):
        template = Template("{% load social_share %} {% post_to_gplus url text %}")
        result = template.render(self.context)
        expected = ' <div class="gplus-this">\n    <a href="https://plus.google.com/share?url=http%3A//example.com" class="" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_mail_url(self):
        template = Template("{% load social_share %} {% send_email_url subject text url %}")
        template.render(self.context)
        expected = 'mailto:?subject=Example%20Domain&body=example%20http%3A//example.com'
        self.assertEqual(self.context['mailto_url'], expected)

    def test_mail(self):
        template = Template("{% load social_share %} {% send_email subject text url %}")
        result = template.render(self.context)
        expected = ' <div class="mail-this">\n    <a href="mailto:?subject=Example%20Domain&body=example%20http%3A//example.com" class="">Share via email</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_linkedin(self):
        template = Template("{% load social_share %} {% post_to_linkedin url %}")
        result = template.render(self.context)
        expected = ' <div class="linkedin-this ">\n  <script src="https://platform.linkedin.com/in.js" type="text/javascript">lang: en_US</script>\n  <script type="IN/Share" data-url="http://example.com"></script>\n</div>\n'
        self.assertEqual(result, expected)

    def test_reddit(self):
        template = Template("{% load social_share %} {% post_to_reddit text url text %}")
        result = template.render(self.context)
        expected = ' <div class="reddit-this">\n    <a href="https://www.reddit.com/submit?title=example&url=http%3A//example.com" class="" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_telegram(self):
        template = Template("{% load social_share %} {% post_to_telegram text url text %}")
        result = template.render(self.context)
        expected = ' <div class="telegram-this">\n    <a href="https://t.me/share/url?text=example&url=http%3A//example.com" class="" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_whatsapp(self):
        template = Template("{% load social_share %} {% post_to_whatsapp url text %}")
        result = template.render(self.context)
        expected = ' <div class="whatsapp-this">\n    <a href="https://api.whatsapp.com/send?text=http%3A//example.com" class="" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_pinterest(self):
        template = Template("{% load social_share %} {% save_to_pinterest url %}")
        result = template.render(self.context)
        expected = ' <div class="pinterest-this ">\n    <a data-pin-do="buttonPin" href="https://www.pinterest.com/pin/create/button/?url=http%3A//example.com" target="_blank"></a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_pinterest_script(self):
        template = Template("{% load social_share %} {% add_pinterest_script %}")
        result = template.render(self.context)
        expected = ' <script async defer src="https://assets.pinterest.com/js/pinit.js"></script>\n'
        self.assertEqual(result, expected)

    def test_clipboard(self):
        template = Template("{% load social_share %} {% copy_to_clipboard url %}")
        result = template.render(self.context)
        expected = ' <div class="copy-this">\n    <button data-copy-btn="buttonCopy" data-copy-url="http://example.com" class="">Copy to clipboard</button>\n</div>\n'
        self.assertEqual(result, expected)

    def test_twitter_with_class(self):
        template = Template("{% load social_share %} {% post_to_twitter text url  link_text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="tweet-this">\n    <a href="https://twitter.com/intent/tweet?text=example%20http%3A//example.com" class="meta-act-link meta-tweet example_class" target="_blank">Post to Twitter</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_facebook_with_class(self):
        template = Template("{% load social_share %} {% post_to_facebook url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="facebook-this">\n    <a href="https://www.facebook.com/sharer/sharer.php?u=http%3A//example.com" class="example_class" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_gplus_with_class(self):
        template = Template("{% load social_share %} {% post_to_gplus url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="gplus-this">\n    <a href="https://plus.google.com/share?url=http%3A//example.com" class="example_class" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_mail_with_class(self):
        template = Template("{% load social_share %} {% send_email subject text url link_text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="mail-this">\n    <a href="mailto:?subject=Example%20Domain&body=example%20http%3A//example.com" class="example_class">Share via email</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_linkedin_with_class(self):
        template = Template("{% load social_share %} {% post_to_linkedin url link_class %}")
        result = template.render(self.context)
        expected = ' <div class="linkedin-this example_class">\n  <script src="https://platform.linkedin.com/in.js" type="text/javascript">lang: en_US</script>\n  <script type="IN/Share" data-url="http://example.com"></script>\n</div>\n'
        self.assertEqual(result, expected)

    def test_reddit_with_class(self):
        template = Template("{% load social_share %} {% post_to_reddit text url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="reddit-this">\n    <a href="https://www.reddit.com/submit?title=example&url=http%3A//example.com" class="example_class" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_telegram_with_class(self):
        template = Template("{% load social_share %} {% post_to_telegram text url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="telegram-this">\n    <a href="https://t.me/share/url?text=example&url=http%3A//example.com" class="example_class" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_whatsapp_with_class(self):
        template = Template("{% load social_share %} {% post_to_whatsapp url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="whatsapp-this">\n    <a href="https://api.whatsapp.com/send?text=http%3A//example.com" class="example_class" target="_blank">example</a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_pinterest_with_class(self):
        template = Template("{% load social_share %} {% save_to_pinterest url  False link_class %}")
        result = template.render(self.context)
        expected = ' <div class="pinterest-this example_class">\n    <a data-pin-do="buttonPin" href="https://www.pinterest.com/pin/create/button/?url=http%3A//example.com" target="_blank"></a>\n</div>\n'
        self.assertEqual(result, expected)

    def test_clipboard_with_class(self):
        template = Template("{% load social_share %} {% copy_to_clipboard url text link_class %}")
        result = template.render(self.context)
        expected = ' <div class="copy-this">\n    <button data-copy-btn="buttonCopy" data-copy-url="http://example.com" class="example_class">example</button>\n</div>\n'
        self.assertEqual(result, expected)