# VNOJ

As a fork of [DMOJ](https://github.com/DMOJ/online-judge), VNOJ serves as the official online judge and programming contests of [VNOI](https://vnoi.info/). 

See it live at [oj.vnoi.info](oj.vnoi.info)!

## Features

Checkout the features listed [here](https://github.com/DMOJ/online-judge#features).

## Installation

Check out the install documentation at [docs.dmoj.ca](https://docs.dmoj.ca/#/site/installation). 

### Notes for installation:
- To support cpp checker, you have to use a python wrapper. By default, the cpp checker will have 512 MB ram, 3 seconds running time limit, 10 seconds compile time limit. You should change its settings in [wrapper_checker_template/template.py](wrapper_checker_template/template.py) 
- To support `testlib.h`, you need to copy the [testlib.h](wrapper_checker_template/testlib.h) to g++ include path in judge server. To speed up compiler time, you may create the precompiled header.
- The admin page (/admin) will redirect to `localhost:8081` if you use `python3 manage.py demo`, there is 2 ways to fix it: 
    1. You can change that in [demo.json](judge/fixtures/demo.json)
    2. You can go to the admin page, scoll down to file the `Sites` settings.

## Useful scripts:

Run these only in venv.

### Fix database
```
mysql -uroot -p
```
Delete old database: `drop database dmoj`

Create new database:  
```
CREATE DATABASE dmoj DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON dmoj.* to 'dmoj'@'localhost' IDENTIFIED BY '<password>';
exit
```

### Migrations
Make migrations: `python3 manage.py makemigrations`

Make data to load: `python3 manage.py dumpdata`

Migrate: `python3 manage.py migrate`

Loaddata (if needed): `python3 manage.py loaddata navbar language_small demo`. Please consider to split this into 3 command 

Create super user: `python3 manage.py createsuperuser` if needed

### Update static site
```
./make_style.sh
python3 manage.py collectstatic
python3 manage.py compilemessages
python3 manage.py compilejsi18n 
```

### Debug at localhost:
```
python3 manage.py check
python3 manage.py runserver localhost:8081
```

### Run with nginx
```
sudo supervisorctl restart site bridged celery
sudo service nginx reload
```
Nếu 2 thằng bridged và celery mà chạy lỗi do permission thì xóa file log của bridged đi rồi chạy

### Run judger
```
cd tới thư mục chứa judge.yml xong chạy: 
dmoj -c judge.yml localhost
```

## Một số ghi chú trong quá trình test
- Khi edit test trên web, nếu không setting DMOJ_PROBLEM_DATA_ROOT vào local_setting thì sẽ không click vào view yaml được -> còn nếu cố định DMOJ_PROBLEM_DATA_ROOT thì làm sao chạy nhiều máy được?

- Có thể edit 2 table `judge_problem` và `judge_problem_allowed_languages` để thêm problem vào (import 1k bài), hoac la fix file demo

- Có nên allow hết 75 ngôn ngữ không, hay chỉ 15 cái thôi? (languages_small & languages_all)