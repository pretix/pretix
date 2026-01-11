# Báo cáo Rà soát Mã nguồn Pretix

## Tổng quan
Dự án có cấu trúc mã nguồn tốt, tuân thủ các chuẩn của Django. Logic nghiệp vụ phức tạp được tách biệt tương đối rõ ràng giữa Models và Services.

## Các vấn đề phát hiện

### 1. Lỗi Race Condition trong quy trình tạo đơn hàng (Critical)
**Vị trí:** `src/pretix/base/services/orders.py`, hàm `_check_positions` và `_perform_order`.

**Mô tả:**
Quy trình hiện tại thực hiện các bước sau:
1. Kiểm tra các ràng buộc (Constraints) như `max_items_per_order`, `voucher_usage`, `seat_availability` (phần query DB).
2. Thực hiện khóa dữ liệu (`lock_objects`).
3. Kiểm tra lại Quota.

**Rủi ro:**
Nếu hai request A và B cùng gửi đến đồng thời:
- Cả hai đều đọc dữ liệu từ DB để kiểm tra ràng buộc (ví dụ: Voucher V chỉ còn 1 lượt dùng). Cả hai đều thấy còn 1 lượt.
- Sau đó cả hai mới tiến hành Lock. Request nào lock được trước sẽ đi tiếp, nhưng request sau cũng đã vượt qua bước check voucher rồi.
- Mặc dù `Quota` và `Seat` được check lại sau khi Lock (an toàn), nhưng các giới hạn khác như `max_per_order` hoặc `voucher_usage` (nếu logic check voucher usage không nằm trong phần Quota) có thể bị vượt qua.

**Khắc phục:**
Cần di chuyển việc gọi `lock_objects` lên trước khi thực hiện các kiểm tra ràng buộc liên quan đến DB.

### 2. Vấn đề về Deadlock tiềm ẩn (Potential)
**Vị trí:** `src/pretix/base/services/orders.py`, class `OrderChangeManager`.

**Mô tả:**
Việc khóa nhiều đối tượng (Quota, Seat) cùng lúc có thể dẫn đến Deadlock nếu thứ tự khóa không nhất quán giữa các luồng xử lý khác nhau (ví dụ: tạo đơn mới vs sửa đơn cũ). Mặc dù hàm `lock_objects` đã cố gắng sắp xếp (sort) các key để tránh deadlock, nhưng việc phụ thuộc vào implementation của `lock_objects` (Advisory Lock của Postgres) cần sự cẩn trọng cao.

### 3. Vấn đề làm tròn số (Rounding Issues)
**Vị trí:** `src/pretix/base/services/orders.py`, hàm `_recalculate_rounding_total_and_payment_fee`.

**Mô tả:**
Hàm này thực hiện sửa đổi giá trị `price` và `tax_value` của các đối tượng `OrderPosition` in-place (trực tiếp trên object đang lưu trong bộ nhớ) sau đó `save()`. Nếu transaction bị rollback sau bước này, các object trong bộ nhớ vẫn giữ giá trị đã bị sửa đổi (làm tròn). Nếu các object này tiếp tục được sử dụng trong cùng một process (ví dụ trong một long-running task hoặc test case phức tạp), nó có thể dẫn đến sai lệch dữ liệu.

## Đề xuất Cải tiến

1.  **Sửa lỗi Race Condition:** Ưu tiên hàng đầu. Di chuyển `lock_objects` lên đầu hàm `_check_positions` hoặc ngay sau khi transaction bắt đầu trong `_perform_order`.
2.  **Tối ưu hóa Query:** Các hàm kiểm tra Quota đang thực hiện khá nhiều query. Có thể cân nhắc pre-fetch hoặc optimize query set.
3.  **Refactoring:** File `services/orders.py` quá lớn (>1800 dòng). Nên tách logic `OrderChangeManager` ra một file riêng `services/order_change.py` và logic tạo đơn hàng ra `services/order_creation.py`.

## Kế hoạch hành động tiếp theo
Tôi sẽ tiến hành sửa lỗi Race Condition (Mục 1) vì đây là lỗi logic ảnh hưởng trực tiếp đến tính toàn vẹn dữ liệu.
