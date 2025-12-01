window.MathJax = {
    tex: {
        packages: {
            '[+]': ['color']
        },
        inlineMath: [
            ['~', '~'],
            ['\\(', '\\)']
        ],
        tags: 'ams'
    },
    output: {
        font: 'mathjax-newcm',
        fontPath: '/static/mathjax-newcm-font',
    },
    options: {
        enableMenu: false
    }
};
