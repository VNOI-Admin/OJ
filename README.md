# VNOJ: VNOI Online Judge [![Build Status](https://github.com/VNOI-Admin/OJ/workflows/build/badge.svg)](https://github.com/VNOI-Admin/OJ/actions/) [![AGPL License](https://img.shields.io/badge/license-AGPLv3.0-blue.svg)](http://www.gnu.org/licenses/agpl-3.0) [![Discord link](https://img.shields.io/discord/660930260405190688?color=%237289DA&label=Discord&logo=Discord)](https://discord.com/invite/TDyYVyd)

As a fork of [DMOJ](https://github.com/DMOJ/online-judge), VNOJ serves as the official online judge and programming contests of [VNOI](https://vnoi.info/).

See it live at [oj.vnoi.info](http://oj.vnoi.info/)!

## Features

Checkout the features listed [here](https://github.com/DMOJ/online-judge#features).

Addition features:

- Beside Python checkers [here](https://docs.dmoj.ca/#/problem_format/custom_checkers), we can write custom C++ checker using `testlib.h`.

## Installation

Check out the install documentation at [docs.dmoj.ca](https://docs.dmoj.ca/#/site/installation). Almost all installation steps is the same as the docs, there is one minor change: clone this repo instead of dmoj repo.

### Additional step in installation:

- You **have to** define `DMOJ_PROBLEM_DATA_ROOT` in `local_settings.py`, this is path to your problems tests folder.

- Considering to disable Full text search, please check [this issuse](https://github.com/VNOI-Admin/OJ/issues/4) for more information.

- To sync the caching of judge server and site, change cache framework (`CACHES`) to `memcached` or `redis` instead of the default (local-memory caching).

- The "home button" the admin dashboard (/admin) will redirect to `localhost:8081` if you use `python3 manage.py loaddata demo`, there is 2 ways to fix it:

  1. You can change that in [demo.json](judge/fixtures/demo.json)
  2. You can go to the admin page, scoll down to find the `Sites` settings and change `localhost:8081` to your domain.

- To support `testlib.h`, you need to copy the [testlib.h](https://github.com/MikeMirzayanov/testlib/blob/master/testlib.h) to g++ include path in judge server. To speed up compiler time, you may create the precompiled header to `testlib.h`.

## Contributing ![PR's Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)

Take a look at [our contribution guideline](contributing.md).

If you found any bug, please feel free to contact us via Discord [![Discord Chat](https://img.shields.io/discord/660930260405190688?color=%237289DA&label=Discord&logo=Discord)](https://discord.gg/TDyYVyd) or open an issue.

Pull requests are welcome as well. Before you submitting your PR, please check your code with [flake8](https://flake8.pycqa.org/en/latest/) and format it if needed.

Translation contributions are also welcome.
