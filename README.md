VNOJ: Viet Nam Online Judge, based on DMOJ[https://github.com/DMOJ].
=====

## Developing:
- allow cpp checker
- how about interactive problem?

## Installation

Check out the install documentation at [docs.dmoj.ca](https://docs.dmoj.ca/#/site/installation). 

Check out [**DMOJ/judge-server**](https://github.com/DMOJ/judge-server) for more judging backend details.

## Some useful script:

Dưới đây là mấy cái script em hay dùng để tiện start server:

Đại đa số các script này đều cần chạy trong virtualenv, ở trong folder của repo này
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
python3 manage.py migrate
python3 manage.py loaddata navbar language_small demo //please consider to split this into 3 command 
python3 manage.py createsuperuser //if needed
```

### Fix lại static site
```
python3 manage.py collectstatic
python3 manage.py compilejsi18n 
```

### Chạy debug ở localhost:
```
python3 manage.py runserver localhost:8081
```

### Chạy với nginx
```
supervisorctl restart all
service nginx restart
```

### Chạy judger
```
cd tới thư mục chứa judge.yml xong chạy: 
dmoj -c judge.yml localhost
```

## Một số ghi chú trong quá trình test
- Khi edit test trên web, nếu không setting DMOJ_PROBLEM_DATA_ROOT vào local_setting thì sẽ không click vào view yaml được -> còn nếu cố định DMOJ_PROBLEM_DATA_ROOT thì làm sao chạy nhiều máy được?

- Có thể edit 2 table `judge_problem` và `judge_problem_allowed_languages` để thêm problem vào (import 1k bài)
