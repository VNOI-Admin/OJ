from datetime import timedelta
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone, translation
from lxml import etree as ET

from judge.models import Contest, ContestSubmission, Language
from judge.models.submission import SUBMISSION_RESULT

# Ref: https://clics.ecs.baylor.edu/index.php?title=Event_Feed_2016


def fill_info(contest: Contest, root: ET.Element):
    info = ET.SubElement(root, 'info')
    info.tail = '\n'
    ET.SubElement(info, 'contest-id').text = contest.key.replace('_', '-')
    ET.SubElement(info, 'title').text = contest.name
    ET.SubElement(info, 'starttime').text = str(contest.start_time.timestamp())
    ET.SubElement(info, 'length').text = str(contest.time_limit or contest.contest_window_length)
    ET.SubElement(info, 'penalty').text = str(contest.format.config.get('penalty', 0))
    ET.SubElement(info, 'started').text = 'True' if timezone.now() >= contest.start_time else 'False'
    if contest.frozen_last_minutes:
        ET.SubElement(info, 'scoreboard-freeze-length').text = str(timedelta(minutes=contest.frozen_last_minutes))


def fill_language(contest: Contest, root: ET.Element):
    for id, key, name in Language.objects.all().values_list('id', 'key', 'name'):
        language = ET.SubElement(root, 'language')
        language.tail = '\n'
        ET.SubElement(language, 'id').text = str(id)
        ET.SubElement(language, 'key').text = key
        ET.SubElement(language, 'name').text = name


def fill_region(contest: Contest, root: ET.Element):
    region = ET.SubElement(root, 'region')
    region.tail = '\n'
    ET.SubElement(region, 'external-id').text = '1'
    ET.SubElement(region, 'name').text = 'Administrative Site'


def fill_judgement(contest: Contest, root: ET.Element):
    for acronym, name in SUBMISSION_RESULT:
        judgement = ET.SubElement(root, 'judgement')
        judgement.tail = '\n'
        ET.SubElement(judgement, 'acronym').text = acronym
        ET.SubElement(judgement, 'name').text = str(name)


def fill_problem(contest: Contest, root: ET.Element) -> Dict[int, int]:
    def get_label_for_problem(index):
        ret = ''
        while index > 0:
            ret += chr((index - 1) % 26 + 65)
            index = (index - 1) // 26
        return ret[::-1]

    contest_problems = contest.contest_problems.order_by('order').values_list('problem__id', 'problem__name')
    problem_index = {}
    for id, (external_id, name) in enumerate(contest_problems, start=1):
        problem = ET.SubElement(root, 'problem')
        problem.tail = '\n'
        ET.SubElement(problem, 'id').text = str(id)
        ET.SubElement(problem, 'label').text = get_label_for_problem(id)
        ET.SubElement(problem, 'name').text = name

        problem_index[external_id] = id

    return problem_index


def fill_team(contest: Contest, root: ET.Element) -> Dict[int, int]:
    teams = contest.users.filter(virtual=0).select_related('user', 'user__user')
    team_index = {}
    for id, participation in enumerate(teams, start=1):
        profile = participation.user
        user = profile.user
        team = ET.SubElement(root, 'team')
        team.tail = '\n'
        ET.SubElement(team, 'id').text = str(id)
        ET.SubElement(team, 'external-id').text = str(user.id)
        ET.SubElement(team, 'name').text = user.first_name or profile.display_name
        ET.SubElement(team, 'nationality').text = 'VNM'
        ET.SubElement(team, 'region').text = 'Administrative Site'
        org = profile.organization
        ET.SubElement(team, 'university').text = org.name if org else ''

        team_index[user.id] = id

    return team_index


def fill_run(contest: Contest, root: ET.Element, problem_index: Dict[int, int], team_index: Dict[int, int]):
    solved_set = set()
    for contest_sub in ContestSubmission.objects.filter(participation__contest=contest, participation__virtual=0) \
                                        .exclude(submission__result__isnull=True) \
                                        .exclude(submission__result__in=['IE', 'CE']) \
                                        .select_related('submission', 'submission__problem',
                                                        'submission__language', 'submission__user__user'):
        run = ET.SubElement(root, 'run')
        run.tail = '\n'
        sub = contest_sub.submission
        ET.SubElement(run, 'id').text = str(sub.id)
        ET.SubElement(run, 'problem').text = str(problem_index[sub.problem.id])
        ET.SubElement(run, 'language').text = sub.language.key
        ET.SubElement(run, 'team').text = str(team_index[sub.user.user.id])
        ET.SubElement(run, 'timestamp').text = str(sub.date.timestamp())
        ET.SubElement(run, 'time').text = str((sub.date - contest.start_time).total_seconds())
        ET.SubElement(run, 'judged').text = 'True'
        ET.SubElement(run, 'result').text = sub.result
        ET.SubElement(run, 'solved').text = 'True' if sub.result == 'AC' else 'False'

        hash = (sub.problem.id, sub.user.user.id)
        if sub.result == 'AC':
            solved_set.add(hash)
        ET.SubElement(run, 'penalty').text = 'False' if hash in solved_set else 'True'


def fill_finalized(contest: Contest, root: ET.Element, last_medals: List[int]):
    finalized = ET.SubElement(root, 'finalized')
    finalized.tail = '\n'
    ET.SubElement(finalized, 'last-gold').text = str(last_medals[0])
    ET.SubElement(finalized, 'last-silver').text = str(last_medals[1])
    ET.SubElement(finalized, 'last-bronze').text = str(last_medals[2])
    ET.SubElement(finalized, 'comment').text = 'Auto-finalized'
    ET.SubElement(finalized, 'timestamp').text = str(timezone.now().timestamp())


class Command(BaseCommand):
    help = 'export CLICS XML Event Feed for use in other tools (e.g. ICPC Resolver)'

    def add_arguments(self, parser):
        parser.add_argument('key', help='contest key')
        parser.add_argument('output', help='output XML file')
        parser.add_argument('--medal',
                            help='the last integer rank (position) in the contest which will be '
                            'awarded Gold, Silver, and Bronze medals respectively',
                            nargs=3,
                            default=[4, 8, 12],
                            metavar=('lastGold', 'lastSilver', 'lastBronze'))

    def handle(self, *args, **options):
        contest_key = options['key']
        output_file = options['output']
        last_medals = options['medal']

        if not output_file.endswith('.xml'):
            raise CommandError('output file must end with .xml')

        contest = Contest.objects.filter(key=contest_key).first()
        if contest is None:
            raise CommandError('contest not found')

        # Force using English
        translation.activate('en')

        # Create root element
        root = ET.Element('contest')
        root.text = '\n'

        # Contest information
        fill_info(contest, root)

        # Programming languages
        fill_language(contest, root)

        # Regions
        fill_region(contest, root)

        # Judgement (AC, WA, etc.)
        fill_judgement(contest, root)

        # Problems
        problem_index = fill_problem(contest, root)

        # Teams
        team_index = fill_team(contest, root)

        # Runs (i.e. submissions)
        fill_run(contest, root, problem_index, team_index)

        # Contest finalization information
        fill_finalized(contest, root, last_medals)

        # Write to output file
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
