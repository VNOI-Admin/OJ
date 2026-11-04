window.MathJax = {
    loader: {
        load: ['[tex]/color'],
        paths: {
            mathjax: '/static/vnoj/mathjax/4.1.3',
            fonts: '/static/vnoj/mathjax/4.1.3/fonts'
        }
    },
    tex: {
        packages: {
            '[+]': ['color']
        },
        inlineMath: [
            ['~', '~'],
            ['\\(', '\\)']
        ]
    },
    options: {
        enableMenu: false,
        menuOptions: {
            settings: {
                enrich: false
            }
        }
    }
};
