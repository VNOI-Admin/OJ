# VNOJ: VNOI Online Judge [![Build Status](https://github.com/VNOI-Admin/OJ/workflows/build/badge.svg)](https://github.com/VNOI-Admin/OJ/actions/) [![AGPL License](https://img.shields.io/badge/license-AGPLv3.0-blue.svg)](http://www.gnu.org/licenses/agpl-3.0) [![Discord link](https://img.shields.io/discord/660930260405190688?color=%237289DA&label=Discord&logo=Discord)](https://discord.com/invite/TDyYVyd)

As a fork of [DMOJ](https://github.com/DMOJ/online-judge), VNOJ serves as [VNOI](https://team.vnoi.info/)'s official online judge and hosts its programming contests.

See it live at [oj.vnoi.info](https://oj.vnoi.info/)!

## Features

Check out its features [here](https://github.com/DMOJ/online-judge#features).

## Installation

Refer to the install documentation [here](https://vnoi-admin.github.io/vnoj-docs/#/site/installation). Almost all installation steps remain the same as the docs, but there are several minor differences, including cloning this repo instead of DMOJ's repo.

### Additional installation steps

- You **have to** define `DMOJ_PROBLEM_DATA_ROOT` in `local_settings.py`, which should be the path to the directory that contains your problems' tests.

- Regarding disabling full-text search, please read [this issue](https://github.com/VNOI-Admin/OJ/issues/4) for more information.

- To sync the judge server and the site's cache, change the cache framework (`CACHES`) to `memcached` or `redis` instead of the default (local-memory caching).

- If you use `python3 manage.py loaddata demo`, the home button in the admin dashboard (/admin) links you to `localhost:8081`, there are 2 ways to change that:

  1. You can change that in [demo.json](/judge/fixtures/demo.json)
  2. You can go to the admin page, scroll down to find the `Sites` setting and change `localhost:8081` to your domain.

- To support `testlib.h`, you need to copy [testlib.h](https://github.com/MikeMirzayanov/testlib/blob/master/testlib.h) to `g++`'s include path in the judge server. To speed up compile time, you can also create a precompiled header for `testlib.h`.

## Contributing ![PR's Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat)

Take a look at [our contribution guideline](contributing.md).

If you find any bug, please feel free to contact us via Discord [![Discord Chat](https://img.shields.io/discord/660930260405190688?color=%237289DA&label=Discord&logo=Discord)](https://discord.gg/TDyYVyd) or open an issue.

Pull requests are welcome as well. Before you submit your PR, please check your code with [flake8](https://flake8.pycqa.org/en/latest/) and format it if needed. There's also `prettier` if you need to format JS code (in `websocket/`).

Translation contributions are also welcome.

## SETUP TGBOJ GITFLOW (LOCAL)
### Getting started
For the first time contributing to TGB-Online-Judge, you may need to perform some of these steps before you can start coding

Now we create a folder, maybe named "TGBOJ"

> `mkdir TGBOJ`

Now setup the git things

> `git init`

The above command line will create a blank `.git` folder.

> `git remote add origin https://github.com/TGB-Dev/tgboj-v2.git`

Now we remote to our repository, preparing for the pull & push stuffs.

We then now get the latest develop version from our repo

> `git pull origin develop`

Done! we are now able to code here, and to prevent conflicting, we may need to regularly run the `git pull` command.


### Submit a new feature
To start submitting your new feature(s), you may need to do some steps

> `git checkout -b feature/<your-feature-name>`

Then we will commit like normally we would do
> `git add .`

> `git commit -am "<something>"`

After that, run:
> `git push origin feature/<your-feature-name>`

Now lets wait for the pull request to be accepted to the develop and release branch.

### Concerning
Regularly update the local develop folder to prevent conflicting.

**DO NOT** push directly to develop or release folder.

use `git fetch origin` to make sure every branch is up-to-date.

### WRITTEN BY MHP0920