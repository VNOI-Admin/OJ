import re

import requests
from django.conf import settings
from django.core.cache import cache

from judge.models import Problem

_TIMEOUT = settings.OJ_REQUESTS_TIMEOUT


class APIError(Exception):
    pass


class OJAPI:
    @staticmethod
    def get_problem_data(url):
        """Return codename and judge name (for choosing API)."""
        presets = settings.OJ_PROBLEM_PRESET

        for preset in presets:
            regex = re.compile(preset['regex']).match(url)
            if regex is None:
                continue
            codename = preset['codename'] % regex.groups()
            return {
                'codename': codename,
                'judge': preset['judge'],
            }

        raise APIError('This link or online judge is not currently supported.')

    @staticmethod
    def CodeforcesProblemAPI(codename):
        contestset = cache.get('OJAPI_data_Codeforces', None)
        prefix, contestid, index = codename.split('_')

        if contestset is None or contestid > max(contestset):
            api_url_contestlist = 'https://codeforces.com/api/contest.list'
            contestset_data = requests.get(api_url_contestlist, timeout=_TIMEOUT).json()

            if contestset_data['status'] != 'OK':
                return None

            contestset = []

            for contest in contestset_data['result']:
                contestset.append(str(contest['id']))
            cache.set('OJAPI_data_Codeforces', contestset, settings.OJAPI_CACHE_TIMEOUT)

        prefix, contestid, index = codename.split('_')

        if contestid not in contestset:
            return None

        api_url = 'https://codeforces.com/api/contest.standings?contestId=%s'
        problemset_data = requests.get(api_url % contestid, timeout=_TIMEOUT).json()

        if problemset_data['status'] != 'OK':
            return None

        code_template = 'CF_%s_%s'

        problemset = {}
        for problem in problemset_data['result']['problems']:
            code = code_template % (problem['contestId'], problem['index'])
            problemset[code] = {
                'contestId': problem['contestId'],
                'index': problem['index'],
                'title': problem['name'],
            }

        return problemset.get(codename, None)

    @staticmethod
    def AtcoderProblemAPI(codename):
        problemset = cache.get('OJAPI_data_Atcoder', None)

        if problemset is None:
            api_url = 'https://kenkoooo.com/atcoder/resources/problems.json'
            problemset_data = requests.get(api_url, timeout=_TIMEOUT).json()

            if problemset_data is None:
                return None

            code_template = 'AC_%s'  # I.e.: index = abc064_c

            problemset = {}

            for problem in problemset_data:
                code = code_template % (problem['id'])
                if code in problemset:
                    raise ValueError('Problem code %s appeared twice in the problemset.' % code)
                problemset[code] = {
                    'contestId': problem['contest_id'],
                    'index': problem['id'],
                    'title': problem['title'],
                }

            cache.set('OJAPI_data_Atcoder', problemset, settings.OJAPI_CACHE_TIMEOUT)

        return problemset.get(codename, None)

    @staticmethod
    def VNOJProblemAPI(codename):
        try:
            codename = codename.replace('VNOJ_', '')
            problem = Problem.objects.get(code=codename)
        except Problem.DoesNotExist:
            return None

        data = {
            'index': problem.code,
            'title': problem.name,
        }
        return data

    @staticmethod
    def KattisProblemAPI(codename):
        codename = codename.replace('KATTIS_', '')
        verification = requests.get(url='https://open.kattis.com/problems/%s' % codename, timeout=_TIMEOUT).status_code
        if verification != 200:
            return None

        title = 'Kattis - %s' % codename

        data = {
            'index': codename,
            'title': title,
        }
        return data

    @staticmethod
    def CodeforcesGymProblemAPI(codename):
        # NOTE: Storing contest list instead of problemset for cache optimization

        contestset = cache.get('OJAPI_data_CodeforcesGym', None)
        prefix, contestid, index = codename.split('_')

        if contestset is None or contestid > max(contestset):
            api_url_contestlist = 'https://codeforces.com/api/contest.list?gym=true'
            contestset_data = requests.get(api_url_contestlist, timeout=_TIMEOUT).json()

            if contestset_data['status'] != 'OK':
                return None

            contestset = []

            for contest in contestset_data['result']:
                contestset.append(str(contest['id']))
            cache.set('OJAPI_data_CodeforcesGym', contestset, settings.OJAPI_CACHE_TIMEOUT)

        prefix, contestid, index = codename.split('_')

        if contestid not in contestset:
            return None

        api_url = 'https://codeforces.com/api/contest.standings?contestId=%s'
        problemset_data = requests.get(api_url % contestid, timeout=_TIMEOUT).json()

        if problemset_data['status'] != 'OK':
            return None

        code_template = 'CFGYM_%s_%s'

        problemset = {}
        for problem in problemset_data['result']['problems']:
            code = code_template % (problem['contestId'], problem['index'])
            problemset[code] = {
                'contestId': problem['contestId'],
                'index': problem['index'],
                'title': problem['name'],
            }

        return problemset.get(codename, None)
