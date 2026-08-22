# Danh sách Permissions của ThinkCode OJ

> Tài liệu này liệt kê toàn bộ **permission tùy chỉnh** (không phải permission mặc định `add`/`change`/`delete`/`view` của Django) có thể gán cho user hoặc group trong trang Admin. Cấp permission ở **Admin → Users/Groups → User permissions**.
>
> Có 26 permission, chia theo 6 nhóm đối tượng: Vấn đề (Problem), Kỳ thi (Contest), Bài nộp (Submission), Blog, Tổ chức (Organization), Người dùng (Profile), Bình luận (Comment).

---

## 1. Vấn đề (Problem)

| Permission | Ý nghĩa |
|---|---|
| `see_private_problem` | Xem được vấn đề đang ẩn (chưa public). |
| `edit_own_problem` | Sửa vấn đề do chính mình tạo/là author. |
| `edit_all_problem` | Sửa **mọi** vấn đề, không cần là author. |
| `edit_public_problem` | Sửa mọi vấn đề đã public (không cần là author, nhưng không đụng được vấn đề private của người khác). |
| `see_organization_problem` | Xem vấn đề riêng của tổ chức (organization-private). |
| `create_organization_problem` | Tạo vấn đề riêng cho tổ chức. |
| `clone_problem` | Nhân bản (clone) một vấn đề có sẵn. |
| `edit_type_group_all_problem` | Sửa loại (type) và nhóm (group) của mọi vấn đề. |
| `change_public_visibility` | Bật/tắt trạng thái public của vấn đề. |
| `change_manually_managed` | Bật/tắt chế độ "quản lý thủ công" của vấn đề. |
| `problem_full_markup` | Dùng markup đầy đủ (kể cả HTML/script nâng cao) khi soạn đề bài. |
| `upload_file_statement` | Upload đề bài dạng file (thay vì gõ trực tiếp). |
| `import_polygon_package` | Import đề bài từ gói Polygon (Codeforces). |

## 2. Kỳ thi (Contest)

| Permission | Ý nghĩa |
|---|---|
| `see_private_contest` | Xem được kỳ thi đang ẩn (chưa public). |
| `edit_own_contest` | Sửa kỳ thi do chính mình tạo/là author. |
| `edit_all_contest` | Sửa **mọi** kỳ thi, không cần là author. |
| `create_private_contest` | Tạo kỳ thi ở chế độ private. |
| `change_contest_visibility` | Đổi chế độ hiển thị (public/private) của kỳ thi. |
| `clone_contest` | Nhân bản (clone) một kỳ thi có sẵn. |
| `lock_contest` | Khóa/mở khóa kỳ thi (chặn sửa đổi thêm). |
| `contest_access_code` | Đặt mã truy cập (access code) riêng cho kỳ thi. |
| `contest_problem_label` | Sửa script đặt tên nhãn bài (A, B, C...) trong kỳ thi. |
| `contest_rating` | Cho phép kỳ thi tính rating (xếp hạng) cho người tham gia. |
| `moss_contest` | Chạy kiểm tra đạo bài (MOSS) cho kỳ thi. |

## 3. Bài nộp (Submission)

| Permission | Ý nghĩa |
|---|---|
| `view_all_submission` | Xem **mọi** bài nộp của tất cả người dùng, không chỉ bài của mình. |
| `resubmit_other` | Nộp lại (resubmit) bài của người khác. |
| `abort_any_submission` | Hủy (abort) bất kỳ bài nộp nào đang chấm, kể cả không phải của mình. |
| `rejudge_submission` | Chấm lại (rejudge) một bài nộp cụ thể. |
| `rejudge_submission_lot` | Chấm lại hàng loạt nhiều bài nộp cùng lúc. |
| `lock_submission` | Khóa một bài nộp, ngăn không cho chấm lại/thay đổi thêm. |
| `spam_submission` | Nộp bài không giới hạn số lần (bỏ qua rate limit nộp bài). |

## 4. Blog

| Permission | Ý nghĩa |
|---|---|
| `edit_all_post` | Sửa **mọi** bài blog, không cần là author. |
| `edit_organization_post` | Sửa bài blog thuộc tổ chức (kèm điều kiện là admin/author của tổ chức đó). |
| `mark_global_post` | Đánh dấu một bài blog hiển thị toàn site (không giới hạn tổ chức). |
| `pin_post` | Ghim (pin) bài blog lên đầu trang. |
| `manage_magazine_post` | Quản lý các bài blog thuộc chuyên mục "Magazine". |

## 5. Tổ chức (Organization)

| Permission | Ý nghĩa |
|---|---|
| `organization_admin` | Có quyền quản trị chung đối với các tổ chức. |
| `edit_all_organization` | Sửa **mọi** tổ chức, không cần là admin của tổ chức đó. |
| `change_open_organization` | Đổi trạng thái mở/đóng (open) của tổ chức. |
| `spam_organization` | Tạo tổ chức không giới hạn số lượng (bỏ qua rate limit tạo tổ chức). |

## 6. Người dùng (Profile)

| Permission | Ý nghĩa |
|---|---|
| `ban_user` | Cấm (ban)/gỡ cấm tài khoản người dùng. |
| `test_site` | Thấy được các tính năng đang phát triển (chưa ra mắt chính thức). |
| `totp` | Sửa cài đặt xác thực 2 lớp TOTP của người dùng khác trong trang Admin. |
| `can_upload_image` | Upload ảnh trực tiếp lên server khi soạn nội dung (qua Martor editor). |
| `high_problem_timelimit` | Đặt time limit của vấn đề vượt mức giới hạn thông thường. |
| `long_contest_duration` | Đặt thời lượng kỳ thi vượt mức giới hạn thông thường. |
| `create_mass_testcases` | Tạo số lượng testcase không giới hạn cho một vấn đề. |

## 7. Bình luận (Comment)

| Permission | Ý nghĩa |
|---|---|
| `view_all_user_comment` | Xem toàn bộ bình luận của một người dùng bất kỳ (tab riêng trên trang cá nhân). |
| `override_comment_lock` | Vẫn bình luận được dù thread đang bị khóa bình luận. |

---

## Ghi chú

- Ngoài 26 permission trên, Django còn tự sinh permission mặc định cho mỗi model (`add_<model>`, `change_<model>`, `delete_<model>`, `view_<model>`) — ví dụ `judge.change_comment` (sửa/ẩn bình luận), `judge.delete_blogpost` (xóa bài blog). Các permission mặc định này **không** nằm trong danh sách trên vì đã có sẵn tự động, không cần định nghĩa riêng.
- Nên gán permission theo **group** (ví dụ nhóm "Problem Setter", "Contest Admin", "Moderator") thay vì gán lẻ từng user, để dễ quản lý và audit về sau.
- Sau khi sửa mô tả permission trong code, chạy `python3 manage.py update_permissions` để đồng bộ lại tên hiển thị trong Admin.
