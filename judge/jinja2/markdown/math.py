import re


placeholder_string = '38K9QWXZrNAx8qqCm1JN'


def extractLatexeq(string, inline_delims=['~', '~'], display_delims=[r'\$\$', r'\$\$'],
        placeholder=placeholder_string):
    """
    Given a string, extract latex equations from it and replace them with
    placeholder string; the function returns a tuple of the form

    (new string, list of latex equations)

    Note:
        - The function is only intended for the MathJax setup of VNOJ.
        - Placeholder must not be found by regex
    """

    it = re.finditer(
        '(' + inline_delims[0] + '.*?' + inline_delims[1] + ')' + '|' +
        '(' + display_delims[0] + '.*?' + display_delims[1] + ')',
        string,
    )

    indices = [0]
    for match in it:
        indices.append(match.start(0))
        indices.append(match.end(0))

    strings = []
    latexeqs = []

    for i in range(0, len(indices) - 1, 2):
        strings.append(string[indices[i]:indices[i + 1]])
        latexeqs.append(string[indices[i + 1]:indices[i + 2]])
    strings.append(string[indices[-1]:])

    result = [None] * (len(strings) + len(latexeqs))
    result[::2] = strings
    result[1::2] = [placeholder] * len(latexeqs)
    # for i in range(1, len(result), 2):
    #     result[i] = placeholder
    result = ''.join(result)

    return (result, latexeqs)

def recontructString(string, latexeqs, inline_delims=['~', '~'], display_delims=[r'\$\$', r'\$\$'],
        placeholder=placeholder_string):
    """
    Given a string (with placeholder substrings) and a list of latex
    equations, return a new string which replaces the placeholders with
    latex equations.
    """

    it = re.finditer(
        placeholder_string,
        string,
    )

    indices = [0]
    for match in it:
        indices.append(match.start(0))
        indices.append(match.end(0))

    strings = []

    for i in range(0, len(indices) - 1, 2):
        strings.append(string[indices[i]:indices[i + 1]])
    strings.append(string[indices[-1]:])

    result = [None] * (len(strings) + len(latexeqs))
    result[::2] = strings
    result[1::2] = latexeqs
    result = ''.join(result)

    return result
