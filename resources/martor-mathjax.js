jQuery(function ($) {
    $(document).on('martor:preview', function (e, $content) {
        function update_math() {
            MathJax.typesetPromise([$content[0]]).then(function () {
                $content.find('.tex-image').hide();
                $content.find('.tex-text').show();
            });
        }

        var $jax = $content.find('.require-mathjax-support');
        if ($jax.length) {
            if (!('MathJax' in window)) {
                $.ajax({
                    type: 'GET',
                    url: $jax.attr('data-config'),
                    dataType: 'script',
                    cache: true,
                    success: function () {
                        window.MathJax.startup = {typeset: false};
                        $.ajax({
                            type: 'GET',
                            url: '/static/vnoj/mathjax/4.1.3/tex-chtml.js',
                            dataType: 'script',
                            cache: true,
                            success: function () {
                                MathJax.startup.promise.then(update_math);
                            }
                        });
                    }
                });
            } else {
                update_math();
            }
        }
    })
});
