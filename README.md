VNOJ: Viet Nam Online Judge, based on DMOJ[https://github.com/DMOJ].
=====
## Installation

Check out the install documentation at [docs.dmoj.ca](https://docs.dmoj.ca/#/site/installation). 

Check out [**DMOJ/judge-server**](https://github.com/DMOJ/judge-server) for more judging backend details.

## Some useful script:

Dưới đây là mấy cái script em hay dùng để tiện start server:

Đại đa số các script này đều cần chạy trong virtualenv, ở trong folder của repo này
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
