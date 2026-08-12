IBILI 4K DOWNLOADER (hi_downloader)

Dự án này là một ứng dụng Desktop & Web API chuyên nghiệp dùng để tải video độ phân giải cao (lên tới 4K) và tải hàng loạt video từ trang cá nhân (Bilibili Space/Profile) của nền tảng Bilibili. 

Ứng dụng được thiết kế theo hướng **Production (chất lượng thương mại)**, có khả năng mở rộng, dễ bảo trì và dễ dàng sao chép (clone) để chạy ngay lập tức trên bất kỳ hệ điều hành nào (đặc biệt là Linux và Windows) với đầy đủ các hướng dẫn chi tiết dưới đây.

---

## 1. YÊU CẦU HỆ THỐNG

Trước khi cài đặt, hãy đảm bảo hệ thống của bạn đã cài đặt các công cụ sau:

### 1.1 Python 3.10 trở lên
Kiểm tra phiên bản Python trên máy của bạn:
```bash
python3 --version
```

### 1.2 Cài đặt FFmpeg (Bắt buộc đối với tải 4K/HD)
Bilibili phân phối video chất lượng cao theo chuẩn DASH (luồng hình ảnh và âm thanh tách biệt). Ứng dụng cần **FFmpeg** để tự động ghép (merge) 2 luồng này thành file `.mp4` hoàn chỉnh.

* **Sử dụng File Binary Tải Trực Tiếp (Dành cho Linux & Windows không muốn cài đặt hệ thống):**
  * Tải bản build tĩnh của `ffmpeg` và `ffprobe`.
  * **Di chuyển (move/copy) 2 tệp `ffmpeg` và `ffprobe` (hoặc `ffmpeg.exe` và `ffprobe.exe` trên Windows) vào thẳng gốc thư mục `hi_downloader/`**.
  * Cấp quyền thực thi nếu chạy trên Linux:
    ```bash
    chmod +x ffmpeg ffprobe
    ```

* **Cài đặt qua trình quản lý gói của Hệ điều hành:**
  * **Ubuntu / Debian:** `sudo apt update && sudo apt install -y ffmpeg`
  * **CentOS / RHEL / Rocky Linux:** `sudo dnf install epel-release -y && sudo dnf install ffmpeg -y`
  * **Arch Linux:** `sudo pacman -S ffmpeg`
  * **macOS:** `brew install ffmpeg`

---

## 2. HƯỚNG DẪN CÀI ĐẶT DỰ ÁN (SETUP)

Thực hiện các bước sau theo thứ tự để thiết lập môi trường chạy ảo (Virtual Environment) và cài đặt thư viện:

### Bước 1: Điều hướng vào thư mục dự án
```bash
cd hi_downloader
```

### Bước 2: Tạo môi trường Python ảo (venv)
Việc sử dụng môi trường ảo giúp cô lập các thư viện của dự án này, tránh xung đột với các ứng dụng khác của hệ thống.
```bash
python3 -m venv venv
```

### Bước 3: Kích hoạt môi trường ảo
* **Trên Linux / macOS:**
  ```bash
  source venv/bin/activate
  ```
* **Trên Windows (cmd):**
  ```cmd
  venv\Scripts\activate.bat
  ```
* **Trên Windows (PowerShell):**
  ```powershell
  venv\Scripts\Activate.ps1
  ```

### Bước 4: Cài đặt các thư viện Python cần thiết
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> [!NOTE]
> **Đối với Linux:** Để sử dụng được tính năng click nút **CHỌN THƯ MỤC** mở hộp thoại chọn thư mục trực quan của hệ thống, hệ điều hành Linux của bạn cần có gói `python3-tk`. Nếu khi click chọn thư mục báo lỗi thiếu thư viện, hãy cài đặt bằng lệnh:
> * **Ubuntu / Debian:** `sudo apt-get install python3-tk`
> * **Fedora / RHEL / CentOS:** `sudo dnf install python3-tkinter`
> * **Arch Linux:** `sudo pacman -S tk`
> 
> Nếu chạy trên môi trường không có giao diện đồ họa (Headless/Server), bạn hoàn toàn có thể tự điền/dán trực tiếp đường dẫn thư mục vào ô nhập liệu mà không cần thông qua hộp thoại chọn.

---

## 3. CẤU HÌNH BIẾN MÔI TRƯỜNG & PROXY

### 3.1 Thiết lập xác thực Proxy (.env)
Nếu bạn có danh sách proxy xoay vòng yêu cầu tài khoản/mật khẩu, hãy copy file `.env.example` thành `.env` và nhập tài khoản:
```bash
cp .env.example .env
```
Mở file `.env` ra và điền thông tin:
```env
PROXY_USER=tai_khoan_proxy_cua_ban
PROXY_PASS=mat_khau_proxy_cua_ban
MAX_CONCURRENT_DOWNLOADS=2
```

### 3.2 Nhập danh sách IP Proxy (proxies.txt)
Mở file `proxies.txt` và thêm danh sách các proxy của bạn dưới dạng `host:port` (mỗi dòng một proxy). Ví dụ:
```text
103.155.12.3:8080
45.112.5.42:3128
```
Mỗi khi bắt đầu một lượt tải mới, hệ thống sẽ chọn ngẫu nhiên một proxy từ danh sách này và kết hợp với thông tin xác thực từ file `.env`.

---

## 4. KHỞI CHẠY ỨNG DỤNG (RUN)

Đảm bảo môi trường ảo `venv` đang hoạt động, chạy lệnh:
```bash
python run_app.py
```

### 4.1 Kết quả hoạt động:
1. Server API (FastAPI) sẽ tự động chạy ngầm trên địa chỉ `http://127.0.0.1:8000`.
2. Trình duyệt mặc định trên máy bạn sẽ tự động được mở ra giao diện tải video.
3. Phần hiển thị trạng thái `FFMPEG` sẽ hiển thị **SẴN SÀNG** nếu hệ thống của bạn đã được cài đặt FFmpeg thành công.

### 4.2 Chạy kiểm thử liên kết API (Integration Test)
Dự án đi kèm với một script kiểm thử tự động để kiểm tra khả năng khởi chạy của API, liên kết nội bộ, và khả năng kết nối tới Bilibili:
```bash
python tests/test_app.py
```
*Kết quả:* Script sẽ tự động khởi chạy server FastAPI trên cổng test `8999`, gọi kiểm thử tự động `GET /api/system` và `POST /api/analyze` để kiểm tra toàn bộ luồng xử lý trước khi chạy thật.

### 4.3 Chạy bộ kiểm thử đơn vị (Unit Test Suite)
Để kiểm tra 100% logic nội bộ bao gồm: thuật toán làm sạch URL, nhận diện FFmpeg, cơ chế xoay vòng proxy, cơ chế tự động thử lại 3 lần, và chức năng hủy tải (cancel) giữa chừng mà không cần kết nối mạng:
```bash
python tests/run_tests.py
```
*Kết quả:* Trình chạy test `unittest` của Python sẽ thực thi toàn bộ 6 ca kiểm thử độc lập và trả về kết quả `OK` nếu mọi logic hoạt động hoàn toàn chính xác.

---

## 5. HƯỚNG DẪN ĐÓNG GÓI RA DỰ ÁN 1 FILE CHẠY DUY NHẤT (.EXE TRỌN GÓI FOR WINDOWS)

Để tạo ra đúng **1 file `.exe` duy nhất trọn gói** (đã nhúng sẵn Python, Giao diện Web, FFmpeg & FFprobe) để người dùng cuối trên Windows chỉ cần nhấp đúp là dùng ngay mà **KHÔNG CẦN CÀI BẤT KỲ CÁI GÌ KHÁC**:

1. Đặt 2 file `ffmpeg.exe` và `ffprobe.exe` vào thư mục dự án `hi_downloader/`.
2. Kích hoạt môi trường ảo `venv` và cài đặt PyInstaller:
   ```cmd
   pip install pyinstaller
   ```
3. Chạy lệnh đóng gói trọn gói 1 file duy nhất:
   ```cmd
   pyinstaller --noconfirm --onefile --name "hi_downloader" --add-data "static;static" --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." run_app.py
   ```
4. Thành quả: File **`hi_downloader.exe`** độc lập duy nhất được tạo ra tại thư mục `dist/`. Bạn chỉ cần gửi đúng **1 file `hi_downloader.exe` này** cho người dùng cuối là họ có thể sử dụng mượt mà 100%!

---

## 6. HƯỚNG DẪN SỬ DỤNG GIAO DIỆN
1. **Bước 1: Phân tích đường dẫn**
   * Dán URL video hoặc URL Space Bilibili vào ô nhập liệu.
   * Chọn trình duyệt để trích xuất Cookie đã đăng nhập nếu bạn muốn tải chất lượng cao (như Chrome, Firefox, Edge).
   * Nhấn nút **Tìm kiếm**.
2. **Bước 2: Chọn cấu hình và Tải xuống**
   * Đối với video đơn: Chọn độ phân giải muốn tải (ví dụ: `2160p (4K ULTRA HD)`, `1080p`,...).
   * Đối với Space/Profile: Nhập khoảng trang muốn tải (Ví dụ: Từ trang 1 đến trang 2).
   * Nhấn nút **Tải xuống**.
3. **Theo dõi tiến trình:**
   * Giao diện hiển thị cụ thể: Tốc độ tải, Thời gian đã tải (`elapsed_time`), Trạng thái thử lại (`[LAN THU 1/3]`) nếu xảy ra lỗi, và nút **HUY** để hủy tải bất kỳ lúc nào.

---

## 7. TÍNH NĂNG PHỤ ĐỀ WHISPER (TÙY CHỌN)

Dự án hỗ trợ sinh phụ đề tự động bằng mô hình OpenAI Whisper. Đây là tính năng tùy chọn:
* **Cài đặt thư viện phụ trợ:**
  ```bash
  ./venv/bin/pip install -r requirements-whisper.txt
  ```
* **Yêu cầu hệ thống:** Yêu cầu máy tính đã cài đặt `ffmpeg` (xem mục 1.2).
* **Cách sử dụng:** Sử dụng action `generate_whisper` thông qua API của Module hoặc Workflow Engine của hệ thống backend.
