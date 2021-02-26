# VNOJ: VNOI Online Judge [![Build Status](https://github.com/VNOI-Admin/OJ/workflows/build/badge.svg)](https://github.com/VNOI-Admin/OJ/actions/)

As a fork of [DMOJ](https://github.com/DMOJ/online-judge), VNOJ serves as the official online judge and programming contests of [VNOI](https://vnoi.info/). 


See it live at [oj.vnoi.info](http://oj.vnoi.info/)!

## Features
Checkout the features listed [here](https://github.com/DMOJ/online-judge#features).

Addition features:
- Beside Python checkers [here](https://docs.dmoj.ca/#/problem_format/custom_checkers), we can write custom C++ checker using `testlib.h`. The idea of this feature came from [LQDOJ](https://github.com/LQDJudge/online-judge).

## Installation
Check out the install documentation at [docs.dmoj.ca](https://docs.dmoj.ca/#/site/installation). Almost all installation steps is the same as the docs, there is one minor change: clone this repo instead of dmoj repo.

### Additional step in installation:
- You **have to** define `DMOJ_PROBLEM_DATA_ROOT` in `local_settings.py`, this is path to your problems tests folder.
- Considering to disable Full text search, please check [this issuse](https://github.com/VNOI-Admin/OJ/issues/4) for more information.
- To sync the caching of judge server and site, change cache framework (`CACHES`) to `memcached` or `redis` instead of the default (local-memory caching).
- The "home button" the admin dashboard (/admin) will redirect to `localhost:8081` if you use `python3 manage.py loaddata demo`, there is 2 ways to fix it: 
    1. You can change that in [demo.json](judge/fixtures/demo.json)
    2. You can go to the admin page, scoll down to find the `Sites` settings and change `localhost:8081` to your domain.
- To support cpp checker, you have to use a python wrapper. By default, the cpp checker will have 512 MB ram, 3 seconds running time limit, 10 seconds compile time limit. You should change its settings in [wrapper_checker_template/template.py](wrapper_checker_template/template.py) 
- To support `testlib.h`, you need to copy the [testlib.h](wrapper_checker_template/testlib.h) to g++ include path in judge server. I modified the testlib a little bit to fit to dmoj system. (To speed up compiler time, you may create the precompiled header.)