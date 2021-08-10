import re

import requests
from django.conf import settings
from django.core.cache import cache

from judge.models import Problem


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
        problemset = cache.get('OJAPI_data_Codeforces', None)

        if problemset is None:
            api_url = "https://codeforces.com/api/problemset.problems"
            problemset_data = requests.get(api_url).json()

            if problemset_data['status'] != 'OK':
                return None

            code_template = "CF_%s_%s"  # I.e.: contestId = 1000, index = C

            problemset = {}

            for problem in problemset_data["result"]["problems"]:
                code = code_template % (problem["contestId"], problem["index"])
                if code in problemset:
                    raise ValueError("Problem code %s appeared twice in the problemset." % code)
                problemset[code] = {
                    "contestId": problem["contestId"],
                    "index": problem["index"],
                    "title": problem["name"],
                }

            cache.set('OJAPI_data_Codeforces', problemset, settings.OJAPI_CACHE_TIMEOUT)

        return problemset.get(codename, None)

    @staticmethod
    def AtcoderProblemAPI(codename):
        problemset = cache.get('OJAPI_data_Atcoder', None)

        if problemset is None:
            api_url = "https://kenkoooo.com/atcoder/resources/problems.json"
            problemset_data = requests.get(api_url).json()

            if problemset_data is None:
                return None

            code_template = "AC_%s_%s"  # I.e.: index = abc064_c

            problemset = {}

            for problem in problemset_data:
                code = code_template % (problem['contest_id'], problem["id"])
                if code in problemset:
                    raise ValueError("Problem code %s appeared twice in the problemset." % code)
                problemset[code] = {
                    "contestId": problem["contest_id"],
                    "index": problem["id"],
                    "title": problem["title"],
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
