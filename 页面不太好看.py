"""
这是一个基于 Flask 和 SQLite 的简易视频分享平台，支持用户注册登录、上传和管理个人视频文件。
用户可以搜索其他用户及其视频，观看视频并进行重命名或删除操作。
内置丰富功能并集成安全的密码哈希和用户认证，适合学习和小型项目使用。

pip install flask flask-login werkzeug pillow
"""
import os
import re
import random
import string
import sqlite3
from io import BytesIO
from flask import (
    Flask, request, redirect, url_for, flash,
    g, send_from_directory, render_template,
    session, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from jinja2 import DictLoader
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 配置
UPLOAD_ROOT = 'static/uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'

# Flask-Login 初始化
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# -------- 数据库辅助函数 --------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('videos.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

# -------- 用户模型 --------
class User(UserMixin):
    def __init__(self, id_, username, password_hash):
        self.id = id_
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            return None
        return User(row['id'], row['username'], row['password_hash'])

    @staticmethod
    def get_by_username(username):
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not row:
            return None
        return User(row['id'], row['username'], row['password_hash'])

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)



def random_captcha_text(length=4):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

import matplotlib.font_manager as fm
import os
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def find_system_font(font_list=None):
    # 常见中英文字体，Windows和Linux通用优先顺序
    if not font_list:
        font_list = [
            "Arial.ttf",
            "Arial",
            "LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
            "NotoSansCJK-Regular.ttc",
            "PingFang.ttc",          # macOS字体，可以保留无妨
            "SimHei.ttf",            # Windows 黑体
            "Microsoft YaHei.ttf",   # Windows 微软雅黑
            "STHeiti Medium.ttc"     # macOS 字体
        ]
    for font_name in font_list:
        try:
            # findfont可能返回默认字体路径，如果不想fallback可设置fallback_to_default=False
            font_path = fm.findfont(font_name, fallback_to_default=False)
            if os.path.exists(font_path):
                return font_path
        except Exception:
            # continue trying other fonts
            continue
    return None

def create_captcha_image(text):
    width, height = 200, 80  # 较大尺寸
    image = Image.new('RGB', (width, height), (255, 255, 255))
    font_path = find_system_font()
    try:
        if font_path:
            font = ImageFont.truetype(font_path, 48)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)
    # 画多条干扰线
    for _ in range(10):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        color = (random.randint(100, 150), random.randint(100, 150), random.randint(100, 150))
        draw.line([start, end], fill=color, width=2)
    # 绘制每个字符，随机上下微调，稍微错开x坐标
    char_width = width // len(text)
    for i, c in enumerate(text):
        y_offset = random.randint(0, height - 50)
        x = i * char_width + random.randint(5, 15)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        draw.text((x, y_offset), c, font=font, fill=color)
    image = image.filter(ImageFilter.EDGE_ENHANCE_MORE)
    return image




@app.route('/captcha')
def captcha():
    text = random_captcha_text()
    session['captcha_text'] = text.lower()
    image = create_captcha_image(text)
    buffer = BytesIO()
    image.save(buffer, 'PNG')
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'image/png'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response




# -------- 工具函数 --------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def lcs_length(a, b):
    a = a.lower()
    b = b.lower()
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(1,m+1):
        for j in range(1,n+1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1]+1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]

def user_folder(user_id):
    folder = os.path.join(UPLOAD_ROOT, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def secure_filename_keep_chinese(filename):
    filename = filename.strip()
    filename = filename.split('/')[-1].split('\\')[-1]
    allowed_pattern = r'[^A-Za-z0-9\u4e00-\u9fff._\-]'
    filename = re.sub(allowed_pattern, '', filename)
    if filename == '':
        filename = 'file'
    return filename

# -------- 模板字符串 --------
base_template = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <title>{% block title %}视频平台{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet" />
    <style>
        /* 页面主体淡绿色背景 */
        body {
            background-color: #e6f2e6;
            padding-bottom: 60px;
        }

        /* 导航栏淡绿色背景强化 */
        nav.navbar {
            background-color: #c0e6c0 !important;
        }

        /* 链接文字采用更深绿 */
        .nav-link, .navbar-brand {
            color: #2f6627 !important;
            font-weight: 600;
        }

        .nav-link:hover {
            color: #1e3d12 !important;
        }

        /* 表格 hover 背景色调 */
        .table-hover tbody tr:hover {
            background-color: #d4efdb;
        }

        /* 按钮默认绿色主题 */
        .btn-primary {
            background-color: #3c763d;
            border-color: #3c763d;
        }

        .btn-primary:hover {
            background-color: #2a4d21;
            border-color: #2a4d21;
        }

        /* 成功类按钮更鲜艳 */
        .btn-success {
            background-color: #4cae4c;
            border-color: #4cae4c;
        }

        .btn-success:hover {
            background-color: #329932;
            border-color: #329932;
        }

        /* 表单控件边框圆角和绿色边框 */
        input.form-control, select.form-control, textarea.form-control {
            border-radius: 0.35rem;
            border: 1.5px solid #7fc97f;
        }

        input.form-control:focus, select.form-control:focus, textarea.form-control:focus {
            border-color: #4cae4c;
            box-shadow: 0 0 5px #4cae4c;
        }

        /* 表单卡片样式，美观柔和 */
        form {
            background-color: #f7fbf7;
            border: 1px solid #a6d8a6;
            border-radius: 0.5rem;
            padding: 30px;
            box-shadow: 0 4px 10px rgba(70, 140, 70, 0.15);
        }

        /* 页脚淡绿色背景 */
        footer.footer {
            background-color: #c0e6c0 !important;
            color: #2f6627 !important;
            font-weight: 500;
        }

        /* 模态框标题色调 */
        .modal-header {
            background-color: #d7efd7;
            color: #246824;
            font-weight: 600;
        }

        /* 上传选择文件按钮风格微调 */
        input[type=file] {
            cursor: pointer;
        }

        /* 按钮最小宽度 */
        .btn-sm {
            min-width: 60px;
        }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-light sticky-top shadow-sm">
    <div class="container">
        <a class="navbar-brand" href="{{ url_for('index') }}"><i class="fa-solid fa-video"></i> 视频平台</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarSupportedContent"
                aria-controls="navbarSupportedContent" aria-expanded="false" aria-label="切换导航">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarSupportedContent">
            <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
                {% if current_user.is_authenticated %}
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('user_videos', user_id=current_user.id) }}">
                            <i class="fa-solid fa-folder"></i> 我的视频
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('upload') }}">
                            <i class="fa-solid fa-upload"></i> 上传视频
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link text-danger" href="{{ url_for('logout') }}">
                            <i class="fa-solid fa-right-from-bracket"></i> 登出
                        </a>
                    </li>
                {% else %}
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('login') }}">
                            <i class="fa-solid fa-right-to-bracket"></i> 登录
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('register') }}">
                            <i class="fa-solid fa-user-plus"></i> 注册
                        </a>
                    </li>
                {% endif %}
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for('search_users') }}">
                        <i class="fa-solid fa-magnifying-glass"></i> 搜索用户
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for('change_password') }}">
                        <i class="fa-solid fa-key"></i> 修改密码
                    </a>
                </li>
            </ul>
        </div>
    </div>
</nav>

<div class="container mt-4">
    {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="alert alert-success alert-dismissible fade show" role="alert" style="border-radius:0.4rem;">
                {% for message in messages %}
                    {{ message }}<br/>
                {% endfor %}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
            </div>
        {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</div>

<footer class="footer mt-auto py-3 fixed-bottom border-top text-center small">
    <div class="container">
        &copy; 2024 视频平台 &nbsp;|&nbsp; Powered by Flask &amp; Bootstrap 5
    </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
'''

index_template = '''
{% extends 'base.html' %}
{% block title %}首页{% endblock %}
{% block content %}
<div class="jumbotron p-4 p-md-5 text-bg-light rounded-3">
    <div class="container-fluid py-5">
        <h1 class="display-4 fw-bold">欢迎访问视频平台</h1>
        <p class="col-md-8 fs-5">注册上传你的视频，或者搜索用户查看他们的视频集。</p>
        <a class="btn btn-primary btn-lg" href="{{ url_for('search_users') }}" role="button"><i class="fa-solid fa-magnifying-glass"></i> 搜索用户</a>
    </div>
</div>
{% endblock %}
'''

register_template = '''
{% extends 'base.html' %}
{% block title %}注册{% endblock %}
{% block content %}
<h2>注册</h2>
<form method="post" style="max-width: 400px; margin: 0 auto;">
    <div class="mb-3">
        <label for="username" class="form-label">用户名</label>
        <input type="text" name="username" class="form-control" id="username" required autofocus />
    </div>
    <div class="mb-3">
        <label for="password" class="form-label">密码</label>
        <input type="password" name="password" class="form-control" id="password" required />
    </div>

    <!-- 验证码部分开始 -->
    <div class="mb-3">
        <label for="captcha" class="form-label">验证码</label>
        <div class="d-flex align-items-center">
            <input type="text" name="captcha" id="captcha" class="form-control me-3" placeholder="请输入验证码" required autocomplete="off"/>
            <img src="{{ url_for('captcha') }}" alt="验证码" id="captcha_img" style="cursor:pointer; height:40px;" title="点击刷新验证码"/>
        </div>
    </div>
    <!-- 验证码部分结束 -->

    <button class="btn btn-success w-100" type="submit"><i class="fa-solid fa-user-plus"></i> 注册</button>
</form>
{% block scripts %}
<script>
document.getElementById('captcha_img').onclick = function () {
    this.src = "{{ url_for('captcha') }}" + "?t=" + Date.now();
};
</script>
{% endblock %}
{% endblock %}
'''

login_template = '''
{% extends 'base.html' %}
{% block title %}登录{% endblock %}
{% block content %}
<h2>登录</h2>
<form method="post" style="max-width: 400px; margin: 0 auto;">
    <div class="mb-3">
        <label for="username" class="form-label">用户名</label>
        <input type="text" name="username" id="username" class="form-control" required autofocus />
    </div>
    <div class="mb-3">
        <label for="password" class="form-label">密码</label>
        <input type="password" name="password" id="password" class="form-control" required />
    </div>

    <!-- 验证码部分开始 -->
    <div class="mb-3">
        <label for="captcha" class="form-label">验证码</label>
        <div class="d-flex align-items-center">
            <input type="text" name="captcha" id="captcha" class="form-control me-3" placeholder="请输入验证码" required autocomplete="off" />
            <img src="{{ url_for('captcha') }}" alt="验证码" id="captcha_img" style="cursor:pointer; height:40px;" title="点击刷新验证码"/>
        </div>
    </div>
    <!-- 验证码部分结束 -->

    <button type="submit" class="btn btn-success w-100"><i class="fa-solid fa-right-to-bracket"></i> 登录</button>
</form>
{% block scripts %}
<script>
document.getElementById('captcha_img').onclick = function () {
    this.src = "{{ url_for('captcha') }}" + "?t=" + Date.now();
};
</script>
{% endblock %}
{% endblock %}
'''

upload_template = '''
{% extends 'base.html' %}
{% block title %}上传视频{% endblock %}
{% block content %}
<h2>上传视频</h2>
<form method="post" enctype="multipart/form-data" style="max-width: 500px; margin: 0 auto;">
    <div class="mb-3">
        <label for="video" class="form-label">选择视频文件 (支持 mp4, avi, mov, mkv)</label>
        <input type="file" name="video" id="video" accept="video/*" class="form-control" required />
    </div>
    <button class="btn btn-success w-100" type="submit"><i class="fa-solid fa-cloud-arrow-up"></i> 上传</button>
</form>
{% endblock %}
'''

search_users_template = '''
{% extends 'base.html' %}
{% block title %}搜索用户{% endblock %}
{% block content %}
<h2>搜索用户</h2>
<form method="post" class="d-flex mb-3" style="max-width: 400px;">
    <input type="text" name="keyword" class="form-control me-2" placeholder="输入用户名关键词" value="{{ keyword }}" required />
    <button type="submit" class="btn btn-primary"><i class="fa-solid fa-magnifying-glass"></i> 搜索</button>
</form>

{% if users %}
<table class="table table-bordered table-hover align-middle">
    <thead class="table-light">
        <tr>
            <th>用户名</th>
            <th style="width: 150px;">操作</th>
        </tr>
    </thead>
    <tbody>
    {% for u in users %}
        <tr>
            <td><i class="fa-solid fa-user text-primary me-2"></i> {{ u['username'] }}</td>
            <td>
                <a href="{{ url_for('user_videos', user_id=u['id']) }}" class="btn btn-sm btn-success"><i class="fa-solid fa-folder-open"></i> 视频</a>
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% elif keyword %}
<div class="alert alert-warning">未找到相关用户。</div>
{% endif %}
{% endblock %}
'''

user_videos_template = '''
{% extends 'base.html' %}
{% block title %}用户 {{ user.username }} 的视频{% endblock %}
{% block content %}
<h2>用户 <strong>{{ user.username }}</strong> 的视频</h2>

<form method="post" class="d-flex mb-3" style="max-width: 800px;">
    <input type="search" name="keyword" class="form-control form-control-sm me-2" placeholder="搜索视频文件名" value="{{ keyword }}" aria-label="搜索视频文件名" />
    <button type="submit" class="btn btn-primary btn-sm"><i class="fa-solid fa-magnifying-glass"></i> 搜索视频</button>
    {% if keyword %}
    <a href="{{ url_for('user_videos', user_id=user.id) }}" class="btn btn-outline-secondary btn-sm ms-2">清除搜索</a>
    {% endif %}
</form>

{% if videos %}
<div class="table-responsive">
<table class="table table-hover align-middle">
    <thead class="table-light">
        <tr>
            <th>文件名</th>
            {% if current_user.is_authenticated and current_user.id == user.id %}
            <th style="width:260px;">操作</th>
            {% else %}
            <th>操作</th>
            {% endif %}
        </tr>
    </thead>
    <tbody>
    {% for v in videos %}
        <tr>
            <td><i class="fa-solid fa-file-video me-2 text-primary"></i>{{ v }}</td>
            <td>
                <a href="{{ url_for('video_player', user_id=user.id, filename=v) }}" target="_blank" class="btn btn-sm btn-success me-1" title="播放">
                    <i class="fa-solid fa-play"></i>
                </a>

                {% if current_user.is_authenticated and current_user.id == user.id %}
                <form method="post" action="{{ url_for('delete_video', filename=v) }}" class="d-inline"
                      onsubmit="return confirm('确认删除此视频吗？');" style="display:inline-block;">
                    <button type="submit" class="btn btn-sm btn-danger me-1" title="删除">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </form>

                <button type="button" class="btn btn-sm btn-warning" title="重命名" data-bs-toggle="modal" data-bs-target="#renameModal{{ loop.index }}">
                    <i class="fa-solid fa-pen"></i>
                </button>

                <!-- 重命名模态框 -->
                <div class="modal fade" id="renameModal{{ loop.index }}" tabindex="-1" aria-labelledby="renameModalLabel{{ loop.index }}" aria-hidden="true">
                  <div class="modal-dialog">
                    <form method="post" action="{{ url_for('rename_video', filename=v) }}">
                      <div class="modal-content">
                        <div class="modal-header">
                          <h5 class="modal-title" id="renameModalLabel{{ loop.index }}">重命名视频</h5>
                          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                        </div>
                        <div class="modal-body">
                          <input name="new_name" type="text" class="form-control" value="{{ v }}" required autofocus />
                        </div>
                        <div class="modal-footer">
                          <button type="submit" class="btn btn-primary">保存</button>
                          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        </div>
                      </div>
                    </form>
                  </div>
                </div>
                {% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% else %}
<div class="alert alert-warning">暂无视频。</div>
{% endif %}
{% endblock %}
'''

video_player_template = '''
{% extends 'base.html' %}
{% block title %}播放视频：{{ filename }}{% endblock %}
{% block content %}
<h2 class="mb-3">播放：{{ filename }}</h2>
<p>上传用户：<strong>{{ user.username }}</strong></p>

<div class="ratio ratio-16x9 mb-3">
    <video id="videoPlayer" width="100%" controls preload="metadata">
        <source src="{{ url_for('uploaded_file', user_id=user.id, filename=filename) }}" type="video/mp4" />
        你的浏览器不支持视频。
    </video>
</div>

<div>
    <span id="currentTime">0:00</span> / <span id="duration">0:00</span>
</div>

{% block scripts %}
<script>
    const video = document.getElementById('videoPlayer');
    const currentTimeElem = document.getElementById('currentTime');
    const durationElem = document.getElementById('duration');

    function formatTime(seconds){
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return m + ':' + (s < 10 ? '0' + s : s);
    }

    video.onloadedmetadata = () => {
        durationElem.textContent = formatTime(video.duration);
    };
    video.ontimeupdate = () => {
        currentTimeElem.textContent = formatTime(video.currentTime);
    };
</script>
{% endblock %}
{% endblock %}
'''

change_password_template = '''
{% extends 'base.html' %}
{% block title %}修改密码{% endblock %}
{% block content %}
<h2>修改密码</h2>
<form method="post" style="max-width: 400px; margin: 0 auto;">
    <div class="mb-3">
        <label for="old_password" class="form-label">旧密码</label>
        <input type="password" name="old_password" id="old_password" class="form-control" required autofocus />
    </div>
    <div class="mb-3">
        <label for="new_password" class="form-label">新密码</label>
        <input type="password" name="new_password" id="new_password" class="form-control" required />
    </div>
    <div class="mb-3">
        <label for="confirm_password" class="form-label">确认新密码</label>
        <input type="password" name="confirm_password" id="confirm_password" class="form-control" required />
    </div>
    <button type="submit" class="btn btn-success w-100"><i class="fa-solid fa-key"></i> 修改密码</button>
</form>
{% endblock %}
'''

# 将模板集中到字典
templates = {
    'base.html': base_template,
    'index.html': index_template,
    'register.html': register_template,
    'login.html': login_template,
    'upload.html': upload_template,
    'search_users.html': search_users_template,
    'user_videos.html': user_videos_template,
    'video_player.html': video_player_template,
    'change_password.html': change_password_template,
}

# 设置Jinja2模板加载器为DictLoader
app.jinja_loader = DictLoader(templates)

# --------- 路由 ---------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        captcha_input = request.form.get('captcha','').strip().lower()
        captcha_session = session.get('captcha_text', '')
        if not captcha_input or captcha_input != captcha_session:
            flash('验证码错误')
            return redirect(request.url)

        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('用户名和密码不能为空')
            return redirect(url_for('register'))
        db = get_db()
        if db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone():
            flash('用户名已存在')
            return redirect(url_for('register'))
        pw_hash = generate_password_hash(password, method='pbkdf2:sha512', salt_length=16)
        db.execute('INSERT INTO users (username,password_hash) VALUES (?, ?)', (username,pw_hash))
        db.commit()
        flash('注册成功，请登录')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        captcha_input = request.form.get('captcha','').strip().lower()
        captcha_session = session.get('captcha_text', '')
        if not captcha_input or captcha_input != captcha_session:
            flash('验证码错误')
            return redirect(request.url)

        username = request.form['username'].strip()
        password = request.form['password']
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('登录成功')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET','POST'])
@login_required
def upload():
    if request.method=='POST':
        if 'video' not in request.files:
            flash('请选择视频文件')
            return redirect(request.url)
        file = request.files['video']
        if file.filename == '':
            flash('未选择文件')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename_keep_chinese(file.filename)
            folder = user_folder(current_user.id)
            base, ext = os.path.splitext(filename)
            i = 1
            unique_name = filename
            while os.path.exists(os.path.join(folder, unique_name)):
                unique_name = f"{base}_{i}{ext}"
                i += 1
            save_path = os.path.join(folder, unique_name)
            file.save(save_path)
            flash('上传成功')
            return redirect(url_for('user_videos', user_id=current_user.id))
        else:
            flash('不支持的文件格式')
            return redirect(request.url)
    return render_template('upload.html')

@app.route('/search', methods=['GET','POST'])
def search_users():
    users = []
    keyword = ''
    if request.method == 'POST':
        keyword = request.form.get('keyword','').strip()
        if keyword:
            db = get_db()
            all_users = db.execute('SELECT * FROM users').fetchall()
            scored = []
            for user_item in all_users:
                score = lcs_length(user_item['username'], keyword)
                if score > 0:
                    scored.append((score, user_item))
            scored.sort(key=lambda item: item[0], reverse=True)
            users = []
            for score, user_item in scored[:20]:
                users.append(user_item)
        else:
            flash('请输入搜索关键词')
            return redirect(url_for('search_users'))
    return render_template('search_users.html', users=users, keyword=keyword)

@app.route('/user/<int:user_id>', methods=['GET','POST'])
def user_videos(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        flash('用户不存在')
        return redirect(url_for('index'))

    folder = user_folder(user_id)
    if not os.path.exists(folder):
        files = []
    else:
        files = []
        for file_name in os.listdir(folder):
            if allowed_file(file_name):
                files.append(file_name)

    keyword = ''
    filtered = []

    if request.method == 'POST':
        keyword = request.form.get('keyword','').strip()
        if keyword:
            scored = []
            for file_name in files:
                score = lcs_length(file_name, keyword)
                if score > 0:
                    scored.append((score, file_name))
            scored.sort(key=lambda item: item[0], reverse=True)
            filtered = []
            for score, file_name in scored[:20]:
                filtered.append(file_name)
        else:
            filtered = files
    else:
        filtered = files

    return render_template('user_videos.html', user=user, videos=filtered, keyword=keyword)

@app.route('/video/<int:user_id>/<filename>')
def video_player(user_id, filename):
    folder = user_folder(user_id)
    safe_fn = secure_filename_keep_chinese(filename)
    path = os.path.join(folder, safe_fn)
    if not os.path.exists(path):
        flash('视频不存在')
        return redirect(url_for('index'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return render_template('video_player.html', user=user, filename=safe_fn)

@app.route('/uploads/<int:user_id>/<filename>')
def uploaded_file(user_id, filename):
    folder = user_folder(user_id)
    safe_fn = secure_filename_keep_chinese(filename)
    return send_from_directory(folder, safe_fn)

@app.route('/delete_video/<filename>', methods=['POST'])
@login_required
def delete_video(filename):
    safe_fn = secure_filename_keep_chinese(filename)
    folder = user_folder(current_user.id)
    path = os.path.join(folder, safe_fn)
    if os.path.exists(path):
        os.remove(path)
        flash('删除成功')
    else:
        flash('文件不存在')
    return redirect(url_for('user_videos', user_id=current_user.id))

@app.route('/rename_video/<filename>', methods=['POST'])
@login_required
def rename_video(filename):
    new_name = request.form.get('new_name','').strip()
    if not new_name:
        flash('新文件名不能为空')
        return redirect(url_for('user_videos', user_id=current_user.id))
    if not allowed_file(new_name):
        flash(f'文件扩展名必须是：{ALLOWED_EXTENSIONS}')
        return redirect(url_for('user_videos', user_id=current_user.id))

    safe_fn = secure_filename_keep_chinese(filename)
    safe_new = secure_filename_keep_chinese(new_name)
    folder = user_folder(current_user.id)
    old_path = os.path.join(folder, safe_fn)
    new_path = os.path.join(folder, safe_new)

    if not os.path.exists(old_path):
        flash('原文件不存在')
        return redirect(url_for('user_videos', user_id=current_user.id))
    if os.path.exists(new_path):
        flash('新文件名已存在')
        return redirect(url_for('user_videos', user_id=current_user.id))

    os.rename(old_path, new_path)
    flash('重命名成功')
    return redirect(url_for('user_videos', user_id=current_user.id))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password','').strip()
        new_password = request.form.get('new_password','').strip()
        confirm_password = request.form.get('confirm_password','').strip()
        if not old_password or not new_password or not confirm_password:
            flash('所有字段均为必填')
            return redirect(url_for('change_password'))
        if new_password != confirm_password:
            flash('新密码与确认密码不匹配')
            return redirect(url_for('change_password'))
        # 验证旧密码
        user = User.get(current_user.id)
        if not user or not check_password_hash(user.password_hash, old_password):
            flash('旧密码错误')
            return redirect(url_for('change_password'))
        # 更新密码哈希
        new_pw_hash = generate_password_hash(new_password, method='pbkdf2:sha512', salt_length=16)
        db = get_db()
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (new_pw_hash, current_user.id))
        db.commit()
        flash('密码修改成功，请使用新密码登录')
        return redirect(url_for('index'))

    return render_template('change_password.html')

# -------- 初始化DB --------
def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        ''')
        db.commit()

if __name__ == '__main__':
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    init_db()
    #app.run(debug=True)
#"""
    app.run(port=9000,debug=False,
            host="0.0.0.0",
            ssl_context=('fullchain.pem', 'privkey.pem'))
            #如果你有证书换成这个启动

#"""
