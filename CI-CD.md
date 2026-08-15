# CI/CD cho ThinkCode OJ

> Thiết kế CD tự động: khi code được merge vào nhánh `deploy`, GitHub Actions build Docker image, push lên GHCR, SSH vào server và tự động thay thế dịch vụ đang chạy sau khi verify judge worker kết nối lại thành công.
>
> Xem `docker-compose.production.yml`, `Dockerfile`, `deploy/deploy.sh`, `deploy/ssh-deploy-wrapper.sh`, `.github/workflows/deploy.yml`, `nginx/vnoj.conf.docker`, `dmoj/local_settings.docker.py.example` trong repo này.

---

## 1. Kiến trúc tổng quan

```
git push (merge vào nhánh `deploy`)
        │
        ▼
GitHub Actions: build.yml (lint/unit test/style) -- phải pass mới đi tiếp
        │
        ▼
GitHub Actions: build Docker image (Dockerfile) trên runner
        │
        ▼
push image lên ghcr.io/hiulaptop/thinkcode-oj:sha-<7 ký tự đầu commit>
        │
        ▼
SSH (deploy key giới hạn, forced command) vào server 14.225.254.134
        │
        ▼
ssh-deploy-wrapper.sh nhận lệnh, xác thực GHCR, gọi deploy.sh <image>
        │
        ▼
deploy.sh trên server:
  1. docker pull image mới
  2. migrate (container tạm, DB thật, TRƯỚC khi đụng service đang chạy)
  3. sync static assets ra /var/www/thinkcodeoj (nginx đọc trực tiếp)
  4. docker compose up -d (cutover site/bridged/celery/wsevent)
  5. verify: site HTTP 200 + judge worker online=True (poll tối đa 60s)
  6a. verify OK -> ghi lại image hiện tại, deploy thành công
  6b. verify FAIL -> tự động rollback về image cũ, verify lại, báo lỗi
```

**Chỉ có 4 process được container hoá**: `site`, `bridged`, `celery`, `wsevent`. MariaDB, Redis, nginx **vẫn chạy native** như hiện tại — không đổi gì, không rủi ro dữ liệu. Container mới dùng `network_mode: host` để kết nối `127.0.0.1:3306`/`127.0.0.1:6379` y hệt cách process native đang làm.

---

## 2. Giới hạn kỹ thuật quan trọng: không có zero-downtime thật

**Không thể** làm blue-green deploy đúng nghĩa (chạy song song bản mới và bản cũ, test xong mới chuyển traffic) cho phần judge, vì:

- Judge worker thật (`thinkcode-judge-1`, container Docker riêng ngoài phạm vi CD này) chỉ duy trì **một kết nối TCP cố định** tới **một địa chỉ:port** ghi cứng trong `judge.yml` của nó (`localhost:9999`).
- DMOJ judge protocol không hỗ trợ "thử kết nối tới 2 bridge cùng lúc rồi chọn 1".
- Server chỉ có **1 judge worker** — không có worker thứ 2 để test độc lập.

Vì vậy quy trình thực tế là **cutover rồi verify ngay, tự động rollback nếu hỏng**:

1. `docker compose up -d` thay thế container `bridged` cũ bằng bản mới → có khoảng trống vài giây khi port 9999 được giải phóng và bind lại → judge worker phát hiện mất kết nối, tự động thử kết nối lại (đây là hành vi mặc định của DMOJ judge, không cần can thiệp gì thêm).
2. `deploy.sh` poll tối đa 90 giây, kiểm tra 2 điều kiện: site trả HTTP 200, và có ít nhất 1 row `Judge.online=True` trong DB. (Ban đầu để 60s, nhưng deploy thật đầu tiên cho thấy đôi khi không đủ -- `docker compose up -d` recreate cả 4 container cùng lúc vì chúng dùng chung 1 image, nên judge cần thêm ~10-20s để phát hiện mất kết nối và reconnect/xác thực lại; đã tăng lên 90s sau khi quan sát 2 lần deploy thật liên tiếp đều timeout ở ranh giới 60s dù judge trên thực tế vẫn reconnect thành công ngay sau đó.)
3. Nếu cả 2 đạt trong 90 giây → deploy thành công.
4. Nếu không → tự động `docker compose up -d` lại với **image cũ** (ghi lại trước đó trong `current_image.txt`), verify lại, rồi báo lỗi cho GitHub Actions (job fail) dù rollback có thành công hay không — để luôn có người biết và kiểm tra.

**Downtime thực tế ước tính**: vài giây tới ~10-15 giây cho phần chấm bài (bridged restart + judge reconnect), site có thể có 1-2 request lỗi trong lúc container `site` restart (uwsgi worker cần vài giây khởi động lại). Đây là đánh đổi hợp lý cho một single-judge-worker setup — nếu cần zero-downtime thật cho judge, xem mục 7 (hướng mở rộng).

**Health check hiện tại chỉ ở mức kết nối** (`Judge.online == True`), **không** chấm thử 1 bài test thật qua judge — theo lựa chọn đã thống nhất, ưu tiên tốc độ deploy hơn độ chắc chắn tuyệt đối. Nếu muốn nâng cấp lên chấm thử thật, xem mục 7.

---

## 3. Setup cần làm 1 lần (đã thực hiện, ghi lại để tham khảo/tái tạo)

### 3.1. Trên server

```bash
# Thêm user opencode vào group docker (để chạy docker/docker compose không cần sudo)
sudo usermod -aG docker opencode

# Thư mục deploy riêng, TÁCH BIỆT khỏi git checkout (source code giờ chỉ tồn
# tại bên trong Docker image, không cần checkout riêng trên server nữa)
mkdir -p /home/opencode/thinkcode-deploy
```

Các file đã đặt tại `/home/opencode/thinkcode-deploy/`:

| File | Nguồn | Ghi chú |
|---|---|---|
| `deploy.sh` | `deploy/deploy.sh` trong repo | Copy thủ công lúc setup, sau đó **không đổi qua CD** -- chỉ cập nhật thủ công khi logic deploy thay đổi |
| `ssh-deploy-wrapper.sh` | `deploy/ssh-deploy-wrapper.sh` trong repo | Forced command cho SSH deploy key (xem mục 4) |
| `docker-compose.production.yml` | `docker-compose.production.yml` trong repo | Topology container, hiếm khi đổi |
| `.env` | Điền thủ công từ `thinkcode/.env.production` | **Chứa secret thật** -- `chmod 600`, KHÔNG có trong git |
| `local_settings.py` | Copy từ `dmoj/local_settings.docker.py.example`, không sửa gì (chỉ đọc `os.environ`) | **Chứa secret gián tiếp qua `.env`** -- `chmod 600` |
| `current_image.txt` | Tự tạo bởi `deploy.sh` sau lần deploy thành công đầu tiên | Dùng để rollback |

### 3.2. SSH deploy key (giới hạn tối đa)

Đã tạo cặp key `ed25519` riêng cho CI/CD, **không** dùng chung với key cá nhân. Public key được cài vào `/home/opencode/.ssh/authorized_keys` với `command=` ép buộc:

```
command="/home/opencode/thinkcode-deploy/ssh-deploy-wrapper.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... github-actions-deploy@thinkcode-oj
```

Nghĩa là **kể cả nếu private key bị lộ**, kẻ tấn công dùng nó chỉ có thể chạy đúng `ssh-deploy-wrapper.sh` — không có shell tương tác, không port forwarding, không chạy được lệnh tuỳ ý nào khác. Đã test xác nhận: mọi lệnh SSH khác (`rm -rf`, `whoami`, shell tương tác...) đều bị từ chối với thông báo lỗi, chỉ format `deploy <image-ref>` (token GHCR truyền qua stdin, không qua argument để tránh lộ trong `ps aux`) được chấp nhận.

Private key được lưu làm GitHub Actions secret `DEPLOY_SSH_KEY` (xem mục 5).

### 3.3. Chuyển nginx sang trỏ TCP thay vì unix socket

**Chưa thực hiện tự động** — đây là bước cutover thủ công 1 lần, cần làm cẩn thận vì ảnh hưởng trực tiếp site đang chạy:

```bash
# Trên server, backup config cũ trước
sudo cp /etc/nginx/conf.d/vnoj.conf /etc/nginx/conf.d/vnoj.conf.native.bak

# Copy config mới (từ nginx/vnoj.conf.docker trong repo này) đè lên
sudo cp nginx/vnoj.conf.docker /etc/nginx/conf.d/vnoj.conf

# Tạo thư mục passthrough cho 502.html/robots.txt (deploy.sh sẽ tự sync file vào đây mỗi lần deploy)
sudo mkdir -p /var/www/thinkcodeoj/static-passthrough /var/www/thinkcodeoj/icons
sudo chmod 777 /var/www/thinkcodeoj/static-passthrough /var/www/thinkcodeoj/icons

# Test config trước khi reload
sudo nginx -t && sudo systemctl reload nginx
```

**Chỉ thực hiện bước này SAU KHI** đã chạy thành công deploy đầu tiên qua CD (để `/var/www/thinkcodeoj/static` đã có static assets mới từ image, tránh nginx trỏ vào file rỗng/thiếu).

---

## 3.4. Static assets + django-compressor: vì sao `/site/static` phải bind-mount, không chỉ copy-1-lần

Bug thật gặp phải ngày 15/08/2026: sau khi cutover, site load được nhưng **mất toàn bộ CSS** (404 trên mọi `/static/cache/css/output.<hash>.css`).

**Nguyên nhân**: `django-compressor` mặc định chạy ở chế độ **online** (`COMPRESS_OFFLINE` không set = `False`). Nghĩa là mỗi khi 1 trang có block `{% compress css %}` được render lần đầu trong 1 container, compressor tự tính hash (dựa trên mtime file nguồn) rồi **ghi file CSS đã minify vào `STATIC_ROOT/cache/css/` ngay lúc đó** -- không phải cố định sẵn từ lúc build image.

`deploy.sh` (bước 3) chỉ `docker cp` static assets ra host **một lần, trước cutover** -- coi `STATIC_ROOT` như dữ liệu tĩnh bất biến. Nhưng compressor online-mode không tĩnh: khi container `site` khởi động và xử lý request đầu tiên, nó tính ra một hash CSS khác (mtime các file trong image lệch theo thời điểm build), ghi vào bản `/site/static` **riêng của chính nó**. HTML trả về tham chiếu hash đó, nhưng file thật lại chỉ nằm trong container, không có trên host -- nginx (đọc thẳng từ đĩa) trả 404.

**Đã cân nhắc và loại bỏ**: bật `COMPRESS_OFFLINE = True` + chạy `manage.py compress` lúc build image (giống style cách CI hiện dùng để build CSS). Bị revert vì block `{% compress css %}` trong `templates/base.html` chọn CSS sáng/dark **tuỳ theo user** (`request.profile.site_theme` / cookie `site_theme`) -- nội dung block phụ thuộc request, không cố định, nên `manage.py compress` (chạy 1 lần, không có request thật) không đủ context để render đúng, hoặc phải enumerate thủ công mọi tổ hợp theme -- phức tạp và dễ vỡ khi thêm theme mới.

**Giải pháp đã áp dụng**: bind-mount thẳng `/var/www/thinkcodeoj/static` (thư mục host mà nginx `location /static` đọc trực tiếp) vào `/site/static` bên trong container `site` (xem `docker-compose.production.yml`). Đây chính là cách bản native cũ (site + nginx cùng máy, cùng ổ đĩa) và `thinkcode-docker` (named volume `assets:` mount chung cả site lẫn nginx container) vẫn luôn hoạt động đúng -- nguyên tắc chung: **compressor phải ghi runtime cache vào đúng chỗ mà web server đọc, không phải một bản sao riêng**. `deploy.sh` bước 3 (`docker cp` static ra host trước cutover) vẫn giữ nguyên -- nó vẫn cần thiết để đưa các asset KHÔNG qua compressor (JS lib, ảnh, icon, font, admin static) từ image mới ra host trước khi container mới lên; chỉ riêng phần compressor tự sinh (`cache/css/`, `cache/js/`) giờ không còn phụ thuộc bước copy đó nữa.

**Bug thứ hai gặp phải khi test fix trên** (cùng ngày): sau khi thêm bind-mount, request đầu tiên vẫn 500 với `PermissionError: [Errno 13] Permission denied: '/site/static/cache/css/output.<hash>.css'`. Nguyên nhân: `docker cp` (chạy dưới quyền root qua docker daemon) **không kế thừa permission `777` của thư mục cha** khi tạo thư mục con mới -- `cache/` và `cache/css/` từng được tạo thủ công lúc debug trước đó với quyền `755`, còn container `site` chạy dưới uid 1000 (`dmoj`, không phải root) nên không ghi được. Đã sửa bằng 2 việc:
1. `deploy.sh` bước 3 giờ chạy `chmod -R 777 "$STATIC_ROOT_HOST"` sau mỗi lần sync, để bất kỳ thư mục con mới nào (compressor tự tạo, hoặc app mới thêm static dir ở upstream) đều luôn world-writable, không phụ thuộc umask của `docker cp`.
2. Vì `deploy.sh` chạy dưới user `opencode` (không có NOPASSWD sudo, và cũng không nên có để giảm attack surface của deploy key), toàn bộ cây `/var/www/thinkcodeoj/static` phải **thuộc sở hữu `opencode`** để lệnh `chmod` ở bước 1 tự chạy được mà không cần `sudo`. Một số thư mục con còn sót lại quyền sở hữu `dmoj-uwsgi` (uid 998, từ thời native) đã được `sudo chown -R opencode:opencode /var/www/thinkcodeoj/static` một lần thủ công để dọn sạch -- **bước này cần lặp lại thủ công (1 lần) khi setup server mới** nếu thư mục `static/` được tạo trước đó bởi user/process khác `opencode` (ví dụ site native cũ đã từng chạy ở đó).

---

## 4. GitHub Actions secrets cần cấu hình

Vào repo `thinkcode-oj` trên GitHub → **Settings → Secrets and variables → Actions**, thêm:

| Secret | Giá trị |
|---|---|
| `DEPLOY_SSH_KEY` | Nội dung **private key** `thinkcode_deploy` (toàn bộ, gồm `-----BEGIN OPENSSH PRIVATE KEY-----`...) |
| `DEPLOY_HOST` | `14.225.254.134` |
| `DEPLOY_USER` | `opencode` |

`GITHUB_TOKEN` không cần tạo thủ công -- GitHub tự cấp cho mỗi workflow run, có đủ quyền `packages: write` để push GHCR (đã khai báo trong `deploy.yml`) và cũng được dùng làm token đăng nhập GHCR trên server (đủ quyền `read:packages` cho cùng repo).

### Khuyến nghị thêm (chưa bắt buộc)

- Vào **Settings → Environments**, tạo environment `production` với **required reviewers** -- deploy sẽ dừng chờ 1 người approve thủ công trước khi chạy job `deploy` (job `build-and-push` vẫn chạy tự động). Hữu ích để tránh merge nhầm vào `deploy` gây deploy ngay lập tức ngoài ý muốn.
- Bật **branch protection** cho nhánh `deploy`: require `build.yml` pass trước khi merge được phép.

---

## 5. Quy trình sử dụng hằng ngày

```bash
# Làm việc bình thường trên nhánh feature/master
git checkout master
git pull
# ... code, commit ...
git push origin master

# Khi sẵn sàng lên production: merge master vào deploy
git checkout deploy
git merge master
git push origin deploy
# -> trigger CD tự động, xem tiến trình tại GitHub Actions tab
```

Hoặc dùng Pull Request `master` → `deploy` trên GitHub UI để có review trước khi merge (khuyến nghị).

---

## 6. Rollback thủ công (nếu auto-rollback cũng thất bại)

```bash
ssh opencode@14.225.254.134
cd /home/opencode/thinkcode-deploy

# Xem trạng thái hiện tại
docker compose -f docker-compose.production.yml --env-file .env ps
docker compose -f docker-compose.production.yml --env-file .env logs --tail=100

# Xem image nào đang chạy trước lần deploy lỗi
cat current_image.txt

# Rollback thủ công về 1 image cụ thể (ví dụ image trước đó theo git log trên GitHub)
IMAGE_TAG=ghcr.io/hiulaptop/thinkcode-oj:sha-<commit-cu> \
  docker compose -f docker-compose.production.yml --env-file .env up -d --remove-orphans

# Kiểm tra judge worker reconnect
docker compose -f docker-compose.production.yml --env-file .env exec site \
  python3 manage.py shell -c "from judge.models import Judge; print(list(Judge.objects.values('name', 'online')))"
```

**Không còn phương án rollback native tức thời.** Trước 15/08/2026, `/home/opencode/vnojsite/` (source code + venv Python 3.8 native) và 4 file config supervisor (`bridged.conf`, `celery.conf`, `site.conf`, `wsevent.conf`) vẫn còn nguyên trên server, cho phép `sudo supervisorctl start site bridged celery wsevent` khôi phục ngay trong vài giây nếu Docker gặp sự cố không cứu được. Theo yêu cầu "server không giữ source code gì cả, chỉ pull image về chạy", toàn bộ đã bị xoá (config supervisor backup tại `/root/supervisor-native-backup/` trên server chỉ để tham khảo, KHÔNG dùng để chạy lại trực tiếp -- venv/node_modules đã mất).

Nếu Docker hoàn toàn không cứu được (lỗi hạ tầng nghiêm trọng, không phải lỗi image/code -- những trường hợp đó dùng rollback qua `deploy.sh`/`current_image.txt` ở trên), phương án duy nhất còn lại là cài native từ đầu bằng `vnoi_setup.sh`/`dmoj_judge_setup.sh` -- 2 script này **không nằm trong repo `thinkcode-oj`** (chưa từng được commit vào git nào), chỉ tồn tại local tại `/home/hlt/Documents/Projects/` trên máy phát triển; cần lấy lại từ đó trước khi chạy trên server. Toàn bộ quá trình mất khoảng 15-30 phút thay vì vài giây. `vnoj.conf.native.bak` (config nginx trỏ unix socket, không phải TCP) vẫn còn trên server tại `/etc/nginx/conf.d/`, có thể dùng lại sau khi site native được cài đặt lại.

---

## 7. Hướng mở rộng (chưa làm, ghi lại để tham khảo)

- **Chấm thử 1 bài test thật** thay vì chỉ check `online=True`: sau bước 5 trong `deploy.sh`, submit 1 submission mẫu qua `manage.py shell`/management command riêng, poll `Submission.status` tới khi có kết quả AC, mới coi là verify thành công. Cần chuẩn bị sẵn 1 problem test cố định trong DB (không lẫn với problem thật của contest).
- **True zero-downtime cho judge**: cần ít nhất 2 judge worker (worker thứ 2 trỏ về 1 bridge port khác, hoặc scale ngang qua hàng đợi trung gian) để có thể drain traffic dần dần thay vì cutover cả 1 lúc.
- **Container hoá DB/Redis**: nếu muốn đồng bộ hoàn toàn với `thinkcode-docker` (fork của `vnoj-docker`), cần kế hoạch di chuyển dữ liệu MariaDB hiện có vào Docker volume + thiết lập backup mới, rủi ro cao hơn nên cố tình để ngoài phạm vi CD lần này.
- **Approval gate trong GitHub Environments** (mục 4) nếu muốn kiểm soát chặt hơn thời điểm deploy thực tế chạy.
