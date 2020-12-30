import os, re
import subprocess

from dmoj.error import InternalError
from dmoj.judgeenv import env, get_problem_root
from dmoj.result import CheckerResult
from dmoj.utils.helper_files import compile_with_auxiliary_files, mktemp, parse_helper_file_error
from dmoj.utils.unicode import utf8text

executor = None


def get_executor(files, lang, compiler_time_limit, problem_id):
    global executor

    if executor is None:
        if not isinstance(files, list):
            files = [files]
        filenames = [os.path.join(get_problem_root(problem_id), f) for f in files]
        executor = compile_with_auxiliary_files(filenames, 
                                                compiler_time_limit=compiler_time_limit)

    return executor

class Module:
    AC = 0
    WA = 1
    PARTIAL = 2

    # regex to match a float from 0 to 1 in the first line of stderr
    repartial = re.compile(r'^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?', re.M)

    @classmethod
    def parse_return_code(cls, proc, executor, point_value, time_limit, memory_limit, feedback, name, stderr):
        if proc.returncode == cls.AC:
            return CheckerResult(True, point_value, feedback=feedback, extended_feedback=stderr)
        elif proc.returncode == cls.PARTIAL:
            match = cls.repartial.search(stderr)
            if not match:
                raise InternalError('Invalid first line of stderr partial points: %r' % stderr)
            points = float(match.group(0))
            if not 0 <= points <= 1:
                raise InternalError('Invalid partial points: %d' % points)
            
            ac = (points == 1)
            return CheckerResult(ac, points * point_value, feedback=feedback, extended_feedback=stderr)
        elif proc.returncode == cls.WA:
            return CheckerResult(False, 0, feedback=feedback, extended_feedback=stderr)
        else:
            #parse_helper_file_error(proc, executor, name, stderr.encode(), time_limit, memory_limit)
            return CheckerResult(False, 0, f"Checker exitcode {proc.returncode}", extended_feedback=stderr)


def check(process_output, judge_output, judge_input, 
          problem_id={{problemid}},
          files={{filecpp}},
          lang='CPP17',
          time_limit=3, # second
          memory_limit=1024 * 512, # 512 MB
          compiler_time_limit=10, # second
          feedback=True,
          point_value=None, **kwargs) -> CheckerResult:
    executor = get_executor(files, lang, compiler_time_limit, problem_id)

    with mktemp(judge_input) as input_file, mktemp(process_output) as output_file, mktemp(judge_output) as judge_file:
        try: 
            process = executor.launch(input_file.name, output_file.name, judge_file.name, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, memory=memory_limit, time=time_limit)
            proc_output, error = map(utf8text, process.communicate())
        except Exception as err:
            raise InternalError('Error while running checker: %r', err)

        return Module.parse_return_code(process, executor, point_value, time_limit,
                                         memory_limit,
                                         feedback=utf8text(proc_output)
                                         if feedback else None, name='checker',
                                         stderr=error)