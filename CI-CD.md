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
  5. verify: site HTTP 200 + judge worker online=True (poll tối đa 90s)
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

Nếu Docker hoàn toàn không cứu được (ví dụ lỗi hạ tầng nghiêm trọng), phương án cuối cùng là quay lại cách cài native cũ -- `vnoi_setup.sh`/service supervisor vẫn còn nguyên trên server (không bị xoá bởi việc setup Docker), có thể `sudo supervisorctl start site bridged celery wsevent` sau khi `docker compose down` và trỏ nginx `vnoj.conf.native.bak` lại.

---

## 7. Hướng mở rộng (chưa làm, ghi lại để tham khảo)

- **Chấm thử 1 bài test thật** thay vì chỉ check `online=True`: sau bước 5 trong `deploy.sh`, submit 1 submission mẫu qua `manage.py shell`/management command riêng, poll `Submission.status` tới khi có kết quả AC, mới coi là verify thành công. Cần chuẩn bị sẵn 1 problem test cố định trong DB (không lẫn với problem thật của contest).
- **True zero-downtime cho judge**: cần ít nhất 2 judge worker (worker thứ 2 trỏ về 1 bridge port khác, hoặc scale ngang qua hàng đợi trung gian) để có thể drain traffic dần dần thay vì cutover cả 1 lúc.
- **Container hoá DB/Redis**: nếu muốn đồng bộ hoàn toàn với `thinkcode-docker` (fork của `vnoj-docker`), cần kế hoạch di chuyển dữ liệu MariaDB hiện có vào Docker volume + thiết lập backup mới, rủi ro cao hơn nên cố tình để ngoài phạm vi CD lần này.
- **Approval gate trong GitHub Environments** (mục 4) nếu muốn kiểm soát chặt hơn thời điểm deploy thực tế chạy.
