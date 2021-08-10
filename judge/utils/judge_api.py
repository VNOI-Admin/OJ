import re

import requests
from django.conf import settings


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

        raise APIError('Problem not found')

    @staticmethod
    def CodeforcesProblemAPI():
        api_url = "https://codeforces.com/api/problemset.problems"
        problemset_data = requests.get(api_url).json()

        if problemset_data['status'] != 'OK':
            return None

        code_template = "CF_%s_%s"  # I.e.: contestId = 1000, index = C
        problem_url_template = "https://codeforces.com/problemset/problem/%s/%s"

        problemset = {}

        for problem in problemset_data["result"]["problems"]:
            code = code_template % (problem["contestId"], problem["index"])
            if code in problemset:
                raise ValueError("Problem code %s appeared twice in the problemset." % code)
            problemset[code] = {
                "contestId": problem["contestId"],
                "index": problem["index"],
                "title": problem["name"],
                "url": problem_url_template % (problem["contestId"], problem["index"]),
            }

        return problemset

    @staticmethod
    def AtcoderProblemAPI():
        api_url = "https://kenkoooo.com/atcoder/resources/problems.json"
        problemset_data = requests.get(api_url).json()

        if problemset_data is None:
            return None

        code_template = "AC_%s_%s"  # I.e.: index = abc064_c
        problem_url_template = "https://atcoder.jp/contests/%s/tasks/%s"

        problemset = {}

        for problem in problemset_data:
            code = code_template % (problem['contest_id'], problem["id"])
            if code in problemset:
                raise ValueError("Problem code %s appeared twice in the problemset." % code)
            problemset[code] = {
                "contestId": problem["contest_id"],
                "index": problem["id"],
                "title": problem["title"],
                "url": problem_url_template % (problem["contest_id"], problem["id"]),
            }

        return problemset
