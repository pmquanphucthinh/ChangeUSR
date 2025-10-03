# ChangeUSR

Ứng dụng desktop (PyQt5) giúp tự động đổi username GitHub sử dụng Playwright và GoLogin.

## Cài đặt

```bash
pip install .
```

Sau khi cài, bạn có thể chạy ứng dụng bằng lệnh:

```bash
changeusr
```

Hoặc trực tiếp từ source:

```bash
python -m changeusr
```

## Cấu hình yêu cầu

* Python 3.10 trở lên
* [GoLogin](https://gologin.com) API token hợp lệ
* Proxy SOCKS5 (định dạng `host:port:user:pass`)
* Thông tin tài khoản GitHub ở định dạng `newusername|currentusername|password|2fa_secret`

## Ghi chú

Ứng dụng chạy tự động bằng trình duyệt điều khiển bởi Playwright. Đảm bảo rằng bạn đã cài đặt các trình điều khiển Playwright cần thiết trước khi sử dụng:

```bash
playwright install
```
