import re


placeholder_string = '~~'


def extractLatexeq(text, inline_delims=['~', '~'], display_delims=[r'\$\$', r'\$\$'],
                   placeholder=placeholder_string):
    """
    Given a string, extract latex equations from it and replace them with
    placeholder string; the function returns a tuple of the form

    (new string, list of latex equations)

    Note:
        - The function is only intended for the MathJax setup of VNOJ.
        - Placeholder must not be found by regex
    """

    pattern = re.compile(
        '(' + inline_delims[0] + '.*?' + inline_delims[1] + ')' + '|' +
        '(' + display_delims[0] + '.*?' + display_delims[1] + ')',
        re.S | re.X | re.M,
    )
    latexeqs = []

    def replaceWithPlaceholder(x):
        latexeqs.append(x.group())
        return placeholder

    result = re.sub(pattern, replaceWithPlaceholder, text)
    return (result, latexeqs)


def recontructString(text, latexeqs, inline_delims=['~', '~'], display_delims=[r'\$\$', r'\$\$'],
                     placeholder=placeholder_string):
    """
    Given a string (with placeholder substrings) and a list of latex
    equations, return a new string which replaces the placeholders with
    latex equations.
    """

    cur_latex_eq = 0

    def replaceWithLatexEq(x):
        nonlocal cur_latex_eq
        cur_latex_eq += 1
        return latexeqs[cur_latex_eq - 1]

    return re.sub(placeholder_string, replaceWithLatexEq, text)
