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

    it = re.finditer(pattern, text)

    indices = [0]
    for match in it:
        indices.append(match.start(0))
        indices.append(match.end(0))

    strings = []
    latexeqs = []

    for i in range(0, len(indices) - 1, 2):
        strings.append(text[indices[i]:indices[i + 1]])
        latexeqs.append(text[indices[i + 1]:indices[i + 2]])
    strings.append(text[indices[-1]:])

    result = [None] * (len(strings) + len(latexeqs))
    result[::2] = strings
    result[1::2] = [placeholder] * len(latexeqs)
    result = ''.join(result)

    return (result, latexeqs)


def recontructString(text, latexeqs, inline_delims=['~', '~'], display_delims=[r'\$\$', r'\$\$'],
                     placeholder=placeholder_string):
    """
    Given a string (with placeholder substrings) and a list of latex
    equations, return a new string which replaces the placeholders with
    latex equations.
    """

    it = re.finditer(
        placeholder_string,
        text,
    )

    indices = [0]
    for match in it:
        indices.append(match.start(0))
        indices.append(match.end(0))

    strings = []

    for i in range(0, len(indices) - 1, 2):
        strings.append(text[indices[i]:indices[i + 1]])
    strings.append(text[indices[-1]:])

    result = [None] * (len(strings) + len(latexeqs))
    result[::2] = strings
    result[1::2] = latexeqs
    result = ''.join(result)

    return result
