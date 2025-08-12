import os
import re
import sqlite3
from datetime import datetime
from flask import (
    Flask, request, render_template_string, redirect, url_for,
    flash, session, send_from_directory, g, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# -------------- 配置 --------------
DATABASE = 'app.db'
VIDEO_FOLDER = 'user_videos'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
SECRET_KEY = 'your_secret_key_here_please_change_this_to_a_complex_one'
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 最大上传500MB，示范用

app = Flask(__name__)
app.config.update(
    DATABASE=DATABASE,
    SECRET_KEY=SECRET_KEY,
    UPLOAD_FOLDER=VIDEO_FOLDER,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
)
os.makedirs(VIDEO_FOLDER, exist_ok=True)

# -------------- 模板字符串 --------------
# base.html 模板
base_template = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{% block title %}视频管理系统{% endblock %}</title>
  <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
      rel="stylesheet"
  />
  <style>
    body {
      padding-top: 4rem;
      max-width: 960px;
      margin: auto;
    }
    .text-truncate {
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('home') }}">视频管理系统</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarMain">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarMain">
          <ul class="navbar-nav ms-auto">
            <li class="nav-item">
              <a class="nav-link {% if request.endpoint == 'home' %}active{% endif %}" href="{{ url_for('home') }}">首页</a>
            </li>
            {% if session.get('username') %}
            <li class="nav-item">
              <a class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}" href="{{ url_for('dashboard') }}">我的空间 ({{ session['username'] }})</a>
            </li>
            <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">退出登录</a></li>
            {% else %}
            <li class="nav-item"><a class="nav-link {% if request.endpoint == 'login' %}active{% endif %}" href="{{ url_for('login') }}">登录</a></li>
            <li class="nav-item"><a class="nav-link {% if request.endpoint == 'register' %}active{% endif %}" href="{{ url_for('register') }}">注册</a></li>
            {% endif %}
          </ul>
        </div>
      </div>
  </nav>
  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="mt-3">
          {% for category, msg in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ msg }}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
          </div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
'''

# home.html
home_template = '''
{% extends base %}
{% block title %}首页 - 视频管理系统{% endblock %}
{% block content %}
<h1>搜索用户</h1>
<form method="get" action="{{ url_for('home') }}" class="mb-4" autocomplete="off">
  <div class="input-group">
    <input type="text"
           name="search"
           class="form-control"
           placeholder="输入用户名搜索"
           value="{{ query }}"
           autofocus
    />
    <button class="btn btn-primary" type="submit">搜索</button>
  </div>
</form>

{% if query %}
  {% if users %}
    <h3>搜索结果 (共 {{ total }} 个匹配):</h3>
    <ul class="list-group mb-3" role="list">
      {% for u in users %}
        <li class="list-group-item" role="listitem">
          <a href="{{ url_for('user_videos', username=u) }}">{{ u }}</a>
        </li>
      {% endfor %}
    </ul>

    {% if total > per_page %}
    <nav aria-label="分页导航">
      <ul class="pagination">
        {% set page_count = (total // per_page) + (1 if total % per_page > 0 else 0) %}
        {% for p in range(1, page_count + 1) %}
          <li class="page-item {% if p == page %}active{% endif %}">
            <a class="page-link" href="{{ url_for('home', search=query, page=p) }}">{{ p }}</a>
          </li>
        {% endfor %}
      </ul>
    </nav>
    {% endif %}
  {% else %}
    <p>没有找到匹配的用户。</p>
  {% endif %}
{% endif %}

{% endblock %}
'''

# register.html
register_template = '''
{% extends base %}
{% block title %}注册 - 视频管理系统{% endblock %}
{% block content %}
<h1>注册</h1>
<form method="post" novalidate>
  <div class="mb-3">
    <label for="username" class="form-label">用户名（中英文、数字、下划线，1-20字符）</label>
    <input type="text" class="form-control" id="username" name="username" pattern="[\u4e00-\u9fa5A-Za-z0-9_]{1,20}" maxlength="20" required />
  </div>
  <div class="mb-3">
    <label for="password" class="form-label">密码（至少3字符）</label>
    <input type="password" class="form-control" id="password" name="password" minlength="3" required />
  </div>
  <button type="submit" class="btn btn-success">注册</button>
  <a href="{{ url_for('home') }}" class="btn btn-link">返回首页</a>
</form>
{% endblock %}
'''

# login.html
login_template = '''
{% extends base %}
{% block title %}登录 - 视频管理系统{% endblock %}
{% block content %}
<h1>登录</h1>
<form method="post" novalidate>
  <div class="mb-3">
    <label for="username" class="form-label">用户名</label>
    <input type="text" class="form-control" id="username" name="username" required />
  </div>
  <div class="mb-3">
    <label for="password" class="form-label">密码</label>
    <input type="password" class="form-control" id="password" name="password" required />
  </div>
  <button type="submit" class="btn btn-primary">登录</button>
  <a href="{{ url_for('home') }}" class="btn btn-link">返回首页</a>
</form>
{% endblock %}
'''

# dashboard.html
dashboard_template = '''
{% extends base %}
{% block title %}个人空间 - {{ username }}{% endblock %}
{% block content %}
<h1>欢迎，{{ username }}</h1>

<div class="card mb-4 shadow-sm">
  <div class="card-header bg-primary text-white">上传新视频</div>
  <div class="card-body">
    <form method="post" enctype="multipart/form-data" class="row g-3 align-items-center">
      <div class="col-auto">
        <input type="file" name="video" accept="video/mp4,video/x-m4v,video/*" class="form-control" required />
      </div>
      <div class="col-auto">
        <button type="submit" class="btn btn-success">上传</button>
      </div>
    </form>
  </div>
</div>

<h2 class="mb-3">我的视频</h2>
{% if videos %}
<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
  {% for vid in videos %}
  <div class="col">
    <div class="card shadow-sm h-100">
      <video class="card-img-top" controls preload="metadata" style="max-height: 200px;">
        <source src="{{ url_for('serve_video', username=username, filename=vid['filename']) }}" type="video/mp4" />
        您的浏览器不支持视频播放。
      </video>
      <div class="card-body d-flex flex-column">
        <h5 class="card-title text-truncate" title="{{ vid['filename'] }}">{{ vid['filename'] }}</h5>
        <small class="text-muted">上传时间：{{ vid['created_at'] }}</small>
        <div class="mt-auto d-flex justify-content-between pt-3">
          <a href="{{ url_for('download_video', username=username, filename=vid['filename']) }}" class="btn btn-sm btn-outline-primary" download>下载</a>
          <form action="{{ url_for('delete_video', video_id=vid['id']) }}" method="post" onsubmit="return confirm('确定删除视频 {{ vid.filename }} 吗？');">
            <button class="btn btn-sm btn-outline-danger" type="submit">删除</button>
          </form>
        </div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<p>您还没有上传任何视频。</p>
{% endif %}
{% endblock %}
'''

# user_videos.html
user_videos_template = '''
{% extends base %}
{% block title %}{{ username }} 的视频列表{% endblock %}
{% block content %}
<h1>{{ username }} 的视频列表</h1>
{% if videos %}
<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
  {% for vid in videos %}
  <div class="col">
    <div class="card shadow-sm h-100">
      <video class="card-img-top" controls preload="metadata" style="max-height: 200px;">
        <source src="{{ url_for('serve_video', username=username, filename=vid['filename']) }}" type="video/mp4" />
        您的浏览器不支持视频播放。
      </video>
      <div class="card-body d-flex flex-column">
        <h5 class="card-title text-truncate" title="{{ vid['filename'] }}">{{ vid['filename'] }}</h5>
        <small class="text-muted">上传时间：{{ vid['created_at'] }}</small>
        <a href="{{ url_for('download_video', username=username, filename=vid['filename']) }}" class="btn btn-sm btn-outline-primary mt-auto" download>下载</a>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<p>该用户暂无视频。</p>
{% endif %}
{% endblock %}
'''

# -------------- 工具和DB相关 --------------

def get_db():
    """打开数据库连接"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """关闭数据库连接"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库，创建表"""
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    ''')
    db.commit()

def valid_username(username: str) -> bool:
    """使用正则判断用户名合法，中英文数字下划线1-20字符"""
    return re.fullmatch(r'[\u4e00-\u9fa5A-Za-z0-9_]{1,20}', username) is not None

def allowed_file(filename: str) -> bool:
    """判断文件后缀是否合法"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    """登录保护装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def current_user_dir():
    """获取当前已登录用户的视频目录，自动创建"""
    username = session.get('username')
    if not username or not valid_username(username):
        abort(403)
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def lcs_length(s1, s2):
    """计算两个字符串最长公共子序列长度（搜索时用）"""
    n, m = len(s1), len(s2)
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n):
        for j in range(m):
            if s1[i] == s2[j]:
                dp[i+1][j+1] = dp[i][j] + 1
            else:
                dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])
    return dp[n][m]

def search_username_lcs(db, query, limit=5):
    """根据LCS算法搜索用户名"""
    query = query.strip()
    if not query:
        return []
    cur = db.execute("SELECT username FROM users")
    users = [row['username'] for row in cur.fetchall()]
    scored = []
    for user in users:
        score = lcs_length(query, user)
        scored.append((score, user))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in scored[:limit]]

# -------------- 路由 --------------

@app.route('/')
def home():
    query = request.args.get('search', '').strip()
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    per_page = 5  # 每页显示数
    users = []
    total = 0
    db = get_db()

    if query:
        all_users = search_username_lcs(db, query, limit=100)
        total = len(all_users)
        start = (page - 1) * per_page
        end = start + per_page
        users = all_users[start:end]

    return render_template_string(home_template, base=base_template, query=query,
                                  users=users, page=page, per_page=per_page, total=total)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        if not valid_username(username):
            flash('用户名只能是中英文、数字、下划线，1-20字符', 'danger')
            return redirect(url_for('register'))
        if len(password) < 3:
            flash('密码不能少于3个字符', 'danger')
            return redirect(url_for('register'))
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        password_hash = generate_password_hash(password)
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password_hash))
        db.commit()
        user_id = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']
        session['user_id'] = user_id
        session['username'] = username
        flash('注册成功，欢迎！', 'success')
        return redirect(url_for('dashboard'))

    return render_template_string(register_template, base=base_template)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or not check_password_hash(user['password'], password):
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = user['id']
        session['username'] = user['username']
        flash('登录成功！', 'success')
        return redirect(url_for('dashboard'))

    return render_template_string(login_template, base=base_template)


@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'info')
    return redirect(url_for('home'))


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    db = get_db()
    user_id = session['user_id']
    username = session['username']
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('未上传文件', 'danger')
            return redirect(url_for('dashboard'))

        file = request.files['video']
        if file.filename == '':
            flash('文件名为空', 'danger')
            return redirect(url_for('dashboard'))

        if not allowed_file(file.filename):
            flash('上传格式不支持，只支持 mp4、avi、mov、mkv 等视频文件', 'danger')
            return redirect(url_for('dashboard'))

        filename = secure_filename(file.filename)
        user_dir = current_user_dir()
        filepath = os.path.join(user_dir, filename)
        counter = 1
        base, ext = os.path.splitext(filename)
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{ext}"
            filepath = os.path.join(user_dir, filename)
            counter += 1

        try:
            file.save(filepath)
        except Exception as e:
            flash(f'保存文件失败: {e}', 'danger')
            return redirect(url_for('dashboard'))

        db.execute('INSERT INTO videos (user_id, filename) VALUES (?, ?)', (user_id, filename))
        db.commit()
        flash(f'视频“{filename}”上传成功', 'success')
        return redirect(url_for('dashboard'))

    videos = db.execute(
        'SELECT id, filename, created_at FROM videos WHERE user_id = ? ORDER BY created_at DESC', (user_id,)
    ).fetchall()

    return render_template_string(dashboard_template, base=base_template,
                                  username=username, videos=videos)


@app.route('/dashboard/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    db = get_db()
    user_id = session['user_id']
    video = db.execute('SELECT * FROM videos WHERE id = ? AND user_id = ?', (video_id, user_id)).fetchone()
    if not video:
        flash('视频不存在或无权限删除', 'danger')
        return redirect(url_for('dashboard'))
    filepath = os.path.join(current_user_dir(), video['filename'])
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        flash(f'删除文件失败: {e}', 'danger')
        return redirect(url_for('dashboard'))
    db.execute('DELETE FROM videos WHERE id = ?', (video_id,))
    db.commit()
    flash(f'视频“{video["filename"]}”已删除', 'success')
    return redirect(url_for('dashboard'))


@app.route('/user/<username>')
def user_videos(username):
    if not valid_username(username):
        flash('用户名格式不正确', 'danger')
        return redirect(url_for('home'))
    db = get_db()
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    videos = db.execute(
        'SELECT id, filename, created_at FROM videos WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)
    ).fetchall()
    return render_template_string(user_videos_template, base=base_template,
                                  username=username, videos=videos)


@app.route('/videos/<username>/<filename>')
def serve_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename)


@app.route('/download/<username>/<filename>')
def download_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename, as_attachment=True)


# -------------- 命令行初始化数据库 --------------
@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('数据库初始化完成！')


# -------------- 主程序 --------------
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print('数据库文件不存在，自动初始化数据库...')
        with app.app_context():
            init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
