from . import registry

# Option B: contest tags carry no `kind`/`label` column in the DB, so the two
# visual families (series = solid pill, style = outlined pill) and the pretty
# display label are mapped here in page code, keyed by the tag slug (ContestTag.name).
# Slugs/labels mirror scripts/contest_tags/output/tags.csv. Labels are intentionally not
# wrapped for translation: they are site-owned proper nouns (mostly event names).
CONTEST_TAG_META = {
    # series
    'free-contest': ('series', 'Free Contest'),
    'bedao': ('series', 'Bedao'),
    'vnoi-cup': ('series', 'VNOI Cup'),
    'icpc': ('series', 'ICPC'),
    'ioi': ('series', 'IOI'),
    'apio': ('series', 'APIO'),
    'educational': ('series', 'Educational'),
    'olympic-sv': ('series', 'Olympic Sinh viên'),
    'olympic-april': ('series', 'Olympic 30/4'),
    'duyen-hai': ('series', 'Duyên Hải'),
    'hsg-quoc-gia': ('series', 'HSG Quoc gia'),
    'hsg-tinh': ('series', 'HSG Tinh/TP'),
    'tst': ('series', 'TST'),
    'tin-hoc-tre': ('series', 'Tin hoc tre'),
    'voi-revision': ('series', 'VOI Revision'),
    'pvhoi': ('series', 'PVHOI'),
    'vnoi-challenge': ('series', 'Tap chi VNOI'),
    'dytechlab': ('series', 'DYTECHLAB'),
    'viettel': ('series', 'Viettel'),
    'code-tour': ('series', 'Code Tour'),
    'mofk-cup': ('series', 'Mofk Cup'),
    'vnu-olympiad': ('series', 'VNU Olympiad'),
    'bach-khoa': ('series', 'Bach Khoa'),
    'vnoj-round': ('series', 'VNOJ Round'),
    'khtn': ('series', 'KHTN'),
    'chuyen-su-pham': ('series', 'Chuyen Su Pham'),
    'problem-of-week': ('series', 'Problem of the Week'),
    # style
    'oi-style': ('style', 'OI style'),
    'icpc-style': ('style', 'ICPC style'),
    'team': ('style', 'Team'),
    'beginner': ('style', 'Beginner'),
    'mirror': ('style', 'Mirror'),
    'practice': ('style', 'Practice'),
}


def tag_family(name):
    meta = CONTEST_TAG_META.get(name)
    return meta[0] if meta else 'series'


@registry.function
def contest_tag_label(name):
    meta = CONTEST_TAG_META.get(name)
    return meta[1] if meta else name.replace('-', ' ').title()


@registry.function
def contest_tag_family(name):
    return tag_family(name)


@registry.function
def contest_tag_list(tags):
    """Series tags first, each as a render-ready dict. `tags` is an iterable of ContestTag."""
    out = [{
        'name': tag.name,
        'label': contest_tag_label(tag.name),
        'family': tag_family(tag.name),
        'color': tag.color,
    } for tag in tags]
    out.sort(key=lambda t: 0 if t['family'] == 'series' else 1)
    return out


@registry.function
def hex_to_rgba(color, alpha=1.0):
    color = color.lstrip('#')
    if len(color) == 3:
        color = ''.join(c * 2 for c in color)
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return color
    return f'rgba({r}, {g}, {b}, {alpha})'
