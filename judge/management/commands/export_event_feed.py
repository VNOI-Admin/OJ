from datetime import timedelta
import xml.etree.cElementTree as ET

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from judge.models import Contest

# Ref: https://clics.ecs.baylor.edu/index.php?title=Event_Feed_2016


def fill_info(contest: Contest, root: ET.Element):
    info = ET.SubElement(root, 'info')

    contest_id = ET.SubElement(info, 'contest-id')
    contest_id.text = contest.key  # TODO: must match regex [a-z0-9-]{1,36}

    title = ET.SubElement(info, 'title')
    title.text = contest.name

    starttime = ET.SubElement(info, 'starttime')
    starttime.text = str(contest.start_time.timestamp())

    length = ET.SubElement(info, 'length')
    length.text = str(contest.time_limit or contest.contest_window_length)

    penalty = ET.SubElement(info, 'penalty')
    penalty.text = '20'  # FIXME: get penalty from contest format

    started = ET.SubElement(info, 'started')
    started.text = 'True' if timezone.now() >= contest.start_time else 'False'

    if contest.frozen_last_minutes:
        scoreboard_freeze_length = ET.SubElement(info, 'scoreboard-freeze-length')
        scoreboard_freeze_length.text = str(timedelta(minutes=contest.frozen_last_minutes))


def fill_language(contest: Contest, root: ET.Element):
    language = ET.SubElement(root, 'language')


def fill_region(contest: Contest, root: ET.Element):
    region = ET.SubElement(root, 'region')


def fill_judgement(contest: Contest, root: ET.Element):
    judgement = ET.SubElement(root, 'judgement')


def fill_problem(contest: Contest, root: ET.Element):
    problem = ET.SubElement(root, 'problem')


def fill_team(contest: Contest, root: ET.Element):
    team = ET.SubElement(root, 'team')


def fill_run(contest: Contest, root: ET.Element):
    run = ET.SubElement(root, 'run')


def fill_finalized(contest: Contest, root: ET.Element):
    finalized = ET.SubElement(root, 'finalized')


class Command(BaseCommand):
    help = 'export CLICS XML Event Feed for use in other tools (e.g. ICPC Resolver)'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output XML file')

    def handle(self, *args, **options):
        contest_key = options['key']
        output_file = options['output']

        if not output_file.endswith('.xml'):
            raise CommandError('output file must end with .xml')

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        root = ET.Element('contest')

        # Contest information
        fill_info(contest, root)

        # Programming languages
        fill_language(contest, root)

        # Regions
        fill_region(contest, root)

        # Judgement (AC, WA, etc.)
        fill_judgement(contest, root)

        # Problems
        fill_problem(contest, root)

        # Teams
        fill_team(contest, root)

        # Runs (i.e. submissions)
        fill_run(contest, root)

        # Contest finalization information
        fill_finalized(contest, root)

        # Write to output file
        tree = ET.ElementTree(root)
        ET.indent(tree, space='', level=0)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
