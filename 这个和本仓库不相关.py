import os
import re
import sqlite3
import random
import string
import io
from functools import wraps
from flask import (
    Flask, request, redirect, url_for,
    flash, session, send_from_directory, g, abort, make_response,
    render_template_string
)
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ----------------------------------------
# 配置项
DATABASE = 'app.db'
VIDEO_FOLDER = 'user_videos'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
SECRET_KEY = 'a_very_secret_key_change_me'  # 记得更换为安全密钥

app = Flask(__name__)
app.config['DATABASE'] = DATABASE
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = VIDEO_FOLDER
os.makedirs(VIDEO_FOLDER, exist_ok=True)

# ----------------------------------------
# 数据库工具函数

def get_db():
    """获取当前运行的数据库连接对象。"""
    db = getattr(g, '_database', None)
    if db is None:
        # 初始化数据库连接，设置SQL查询结果为dict格式
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """初始化SQLite数据库，创建必需的表。"""
    db = get_db()
    db.executescript('''
    -- 用户表：存储用户的登录信息
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, -- 用户名，必须唯一
        password TEXT NOT NULL         -- 用户密码，简单存储，实际应加密
    );
    -- 视频表：记录用户上传的视频文件信息
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,      -- 对应用户的外键
        filename TEXT NOT NULL,        -- 视频文件的名称
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 上传时间
        FOREIGN KEY(user_id) REFERENCES users(id) -- 外键约束
    );
    ''')
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    """关闭数据库连接。"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ----------------------------------------
# 工具函数

def valid_username(username):
    """验证用户名是否合法，要求必须是中文、英文字母、数字、下划线，长度1-20。"""
    return re.fullmatch(r'[\u4e00-\u9fa5A-Za-z0-9_]{1,20}', username) is not None

def allowed_file(filename):
    """检查文件类型是否支持的格式。"""
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    """清洗文件名以确保安全"""
    filename = filename.strip()
    parts = filename.rsplit('.',1)
    if len(parts) == 2:
        name, ext = parts
        ext = ext.lower()
    else:
        name, ext = filename, ''
    # 替换非允许字符为下划线
    name = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9_\-]', '_', name)
    if ext:
        ext = re.sub(r'[^\w]', '', ext)
        return f"{name}.{ext}"
    else:
        return name

def lcs_length(s1,s2):
    """计算两个字符串的最长公共子序列长度，用于模糊搜索评分。"""
    n, m = len(s1), len(s2)
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n):
        for j in range(m):
            if s1[i]==s2[j]:
                dp[i+1][j+1] = dp[i][j]+1
            else:
                dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])
    return dp[n][m]

def search_username_lcs(db, query, limit=5):
    """使用最长公共子序列算法搜索匹配用户"""
    query = query.strip()
    if not query:
        return []
    # 从数据库中获取所有用户名
    cur = db.execute("SELECT username FROM users")
    users = [row['username'] for row in cur.fetchall()]
    # 给用户名按照匹配评分排序
    scored = [(lcs_length(query, user), user) for user in users]
    scored.sort(key=lambda x: (-x[0], x[1]))
    # 返回最高分用户
    return [scored[i][1] for i in range(min(limit, len(scored)))]

def login_required(f):
    """Flask装饰器：确保用户登录状态"""
    @wraps(f)
    def decor(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decor

def current_user_dir():
    """获得当前登录用户的视频存储文件夹路径"""
    username = session.get('username')
    if not username:
        abort(403)
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# ----------------------------------------
# 验证码处理

def random_captcha_text(length=5):
    """生成随机验证码文本，由大小写字母构成"""
    return ''.join(random.choices(string.ascii_letters,k=length))

@app.route('/captcha')
def captcha():
    """生成图形验证码, 支持模糊和干扰线"""
    text = random_captcha_text()
    session['captcha_text'] = text

    width, height = 120, 40
    image = Image.new('RGB', (width, height), (255,255,255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()

    for _ in range(5):
        start = (random.randint(0,width), random.randint(0,height))
        end = (random.randint(0,width), random.randint(0,height))
        draw.line([start,end], fill=(160,160,160), width=1)

    for i, c in enumerate(text):
        x = 5 + i*22 + random.randint(-2,2)
        y = 5 + random.randint(-2,2)
        draw.text((x,y), c, font=font, fill=(0,0,0))

    image = image.filter(ImageFilter.GaussianBlur(1))
    buf = io.BytesIO()
    image.save(buf, 'png')
    buf.seek(0)

    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'no-store,no-cache,must-revalidate,max-age=0'
    return resp

# ----------------------------------------
# 导航栏HTML字符串（固定顶端，左右贴边）

NAVBAR_HTML = '''
<nav class="navbar navbar-expand-lg navbar-dark bg-primary fixed-top">
  <div class="container-fluid px-3">
    <a class="navbar-brand" href="/">视频管理系统</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse"
      data-bs-target="#navbarSupportedContent" aria-controls="navbarSupportedContent"
      aria-expanded="false" aria-label="切换导航">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse justify-content-end" id="navbarSupportedContent">
      <form class="d-flex me-3" method="get" action="/">
        <input class="form-control me-2" type="search" placeholder="搜索用户" aria-label="搜索用户" name="search" value="{{ search_query|default('') }}">
        <button class="btn btn-light" type="submit">🔍 搜索</button>
      </form>
      <ul class="navbar-nav mb-2 mb-lg-0">
        {% if session.get('user_id') %}
          <li class="nav-item">
            <a class="nav-link" href="/dashboard">📂 管理视频</a>
          </li>
          <li class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
              {{ session.get('username') }}
            </a>
            <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userDropdown">
              <li><a class="dropdown-item" href="/logout">退出登录</a></li>
            </ul>
          </li>
        {% else %}
          <li class="nav-item"><a class="nav-link" href="/login">登录</a></li>
          <li class="nav-item"><a class="nav-link" href="/register">注册</a></li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>
'''

# ----------------------------------------
# HTML页面模板

HOME_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>首页 - 视频管理系统</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>body {{ padding-top: 56px; }}</style>
</head>
<body>
{navbar}
<div class="container mt-4">
  <h1>搜索用户</h1>
  {content}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

REGISTER_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>注册 - 视频管理系统</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body {{ padding-top: 56px; max-width: 400px; margin: auto; }}</style>
</head>
<body>
{navbar}
<div class="container mt-4">
  <h1>注册</h1>
  <form method="post" novalidate>
    <div class="mb-3">
      <label>用户名（中英文、数字、下划线，1-20字符）</label>
      <input type="text" name="username" required class="form-control" pattern="[\u4e00-\u9fa5A-Za-z0-9_]{1,20}" title="中英文、数字、下划线，1-20字符" maxlength="20">
    </div>
    <div class="mb-3">
      <label>密码（至少3字符）</label>
      <input type="password" name="password" required class="form-control" minlength="3">
    </div>
    <div class="mb-3">
      <label>验证码</label>
      <div class="d-flex align-items-center mb-2">
        <img src="/captcha" id="captcha_img" style="cursor:pointer;" title="点击刷新验证码" onclick="this.src='/captcha?'+Math.random()">
      </div>
      <input type="text" name="captcha" required class="form-control" maxlength="5" minlength="5" pattern="[A-Za-z]{5}" placeholder="请输入验证码" autocomplete="off">
    </div>
    <button type="submit" class="btn btn-success">注册</button>
    <a href="/" class="btn btn-link">返回首页</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

LOGIN_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>登录 - 视频管理系统</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body {{ padding-top: 56px; max-width: 400px; margin: auto; }}</style>
</head>
<body>
{navbar}
<div class="container mt-4">
  <h1>登录</h1>
  <form method="post" novalidate>
    <div class="mb-3">
      <label>用户名</label>
      <input type="text" name="username" required class="form-control" maxlength="20">
    </div>
    <div class="mb-3">
      <label>密码</label>
      <input type="password" name="password" required class="form-control" minlength="3">
    </div>
    <div class="mb-3">
      <label>验证码</label>
      <div class="d-flex align-items-center mb-2">
        <img src="/captcha" id="captcha_img" style="cursor:pointer;" title="点击刷新验证码" onclick="this.src='/captcha?'+Math.random()">
      </div>
      <input type="text" name="captcha" required class="form-control" maxlength="5" minlength="5" pattern="[A-Za-z]{5}" placeholder="请输入验证码" autocomplete="off">
    </div>
    <button type="submit" class="btn btn-primary">登录</button>
    <a href="/" class="btn btn-link">返回首页</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>管理视频 - {username}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body {{ padding-top: 56px; }}</style>
</head>
<body>
{navbar}
<div class="container mt-4">
  <h1>管理视频 - {username}</h1>
  <div class="card mb-4 shadow-sm">
    <div class="card-header bg-primary text-white">上传新视频</div>
    <div class="card-body">
      <form method="post" enctype="multipart/form-data" class="row g-3 align-items-center">
        <div class="col-auto">
          <input type="file" name="video" accept="video/*" required class="form-control" />
        </div>
        <div class="col-auto">
          <button type="submit" class="btn btn-success">上传</button>
        </div>
      </form>
    </div>
  </div>
  <h2>我的视频</h2>
  {videos}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
'''

USER_VIDEOS_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{username} 的视频列表</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body {{ padding-top: 56px; }}</style>
</head>
<body>
{navbar}
<div class="container mt-4">
  <h1>{username} 的视频列表</h1>
  {videos}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

PLAY_VIDEO_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>播放 - {filename}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body {{ padding-top: 56px; }}</style>
</head>
<body>
{navbar}
<main class="container my-4">
  <h3>{filename}</h3>
  <p>上传用户：<a href="{user_url}">{username}</a></p>
  <video controls preload="metadata" autoplay style="max-width: 100%; height: auto; display:block; margin-bottom:1rem;">
    <source src="{video_url}" type="video/mp4" />
    您的浏览器不支持HTML5视频播放。
  </video>
  <a href="{download_url}" class="btn btn-primary" download>下载视频</a>
  <a href="{user_url}" class="btn btn-outline-secondary ms-2">返回视频列表</a>
</main>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
'''

# ----------------------------------------
# 首页：搜索用户，显示搜索结果

@app.route('/')
def home():
    search_query = request.args.get('search', '').strip()
    db = get_db()
    users = search_username_lcs(db, search_query) if search_query else []

    navbar = render_template_string(NAVBAR_HTML, search_query=search_query)

    if search_query:
        if users:
            content = '<div class="list-group">'
            content += ''.join(f'<a href="/user/{u}" class="list-group-item list-group-item-action">{u}</a>' for u in users)
            content += '</div>'
        else:
            content = '<p class="text-muted">未找到匹配用户</p>'
    else:
        content = '<p class="text-muted">请输入用户名进行搜索</p>'

    return HOME_HTML.format(navbar=navbar, content=content)

# ----------------------------------------
# 注册

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        captcha_input = request.form.get('captcha','').strip()
        if captcha_input != session.get('captcha_text',''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))
        db = get_db()
        if not valid_username(username):
            flash('用户名只能是中英文、数字、下划线，1-20字符', 'danger')
            return redirect(url_for('register'))
        if len(password) < 3:
            flash('密码不能少于3个字符', 'danger')
            return redirect(url_for('register'))
        # 检查用户名是否已存在
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        # 插入新用户记录到数据库
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        db.commit()
        # 获取新用户ID并设置session
        user_id = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']
        session['user_id'] = user_id
        session['username'] = username
        flash('注册成功，欢迎！', 'success')
        return redirect(url_for('dashboard'))

    navbar = render_template_string(NAVBAR_HTML, search_query='')
    return REGISTER_HTML.format(navbar=navbar)

# ----------------------------------------
# 登录

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        captcha_input = request.form.get('captcha','').strip()
        if captcha_input != session.get('captcha_text',''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))
        db = get_db()
        # 根据用户名查找用户记录
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or user['password'] != password:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))
        # 设置session
        session['user_id'] = user['id']
        session['username'] = user['username']
        flash('登录成功！', 'success')
        return redirect(url_for('dashboard'))

    navbar = render_template_string(NAVBAR_HTML, search_query='')
    return LOGIN_HTML.format(navbar=navbar)

# ----------------------------------------
# 登出

@app.route('/logout')
def logout():
    session.clear()
    flash('您已退出登录', 'info')
    return redirect(url_for('home'))

# ----------------------------------------
# 个人空间-管理视频（上传、展示、删除）

@app.route('/dashboard', methods=['GET','POST'])
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
            flash('上传格式不支持', 'danger')
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
        # 保存视频文件
        file.save(filepath)
        # 插入视频记录到数据库
        db.execute('INSERT INTO videos (user_id, filename) VALUES (?, ?)', (user_id, filename))
        db.commit()
        flash(f'视频“{filename}”上传成功！', 'success')
        return redirect(url_for('dashboard'))

    # 从数据库中获取用户的视频文件列表
    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    if not videos:
        videos_html = '<p class="text-muted">您还没有上传任何视频。</p>'
    else:
        videos_html = '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            delete_url = url_for('delete_video', video_id=vid['id'])
            videos_html += f'''
            <div class="col">
              <div class="card shadow-sm h-100">
                <a href="{url_for('play_video', username=username, filename=vid['filename'])}" class="stretched-link text-decoration-none">
                  <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
                    <source src="{video_url}" type="video/mp4" />
                    您的浏览器不支持视频播放。
                  </video>
                </a>
                <div class="card-body">
                  <h5 class="card-title text-truncate" title="{vid['filename']}">{vid['filename']}</h5>
                  <a href="{download_url}" class="btn btn-sm btn-outline-primary">下载</a>
                  <form action="{delete_url}" method="post" class="d-inline" onsubmit="return confirm('确定删除视频 {vid['filename']} 吗？');">
                    <button class="btn btn-sm btn-outline-danger" type="submit">删除</button>
                  </form>
                </div>
              </div>
            </div>
            '''
        videos_html += '</div>'

    navbar = render_template_string(NAVBAR_HTML, search_query='')
    return DASHBOARD_HTML.format(navbar=navbar, username=username, videos=videos_html)

@app.route('/dashboard/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    """删除当前用户的视频记录以及文件"""
    db = get_db()
    user_id = session['user_id']
    # 检查视频是否属于当前用户
    video = db.execute('SELECT * FROM videos WHERE id = ? AND user_id = ?', (video_id, user_id)).fetchone()
    if not video:
        flash('视频不存在或无权限删除', 'danger')
        return redirect(url_for('dashboard'))
    # 删除视频文件
    fp = os.path.join(current_user_dir(), video['filename'])
    if os.path.exists(fp):
        os.remove(fp)
    # 删除数据库中视频记录
    db.execute('DELETE FROM videos WHERE id = ?', (video_id,))
    db.commit()
    flash(f'视频“{video["filename"]}”已删除', 'success')
    return redirect(url_for('dashboard'))

# ----------------------------------------
# 用户视频列表页面

@app.route('/user/<username>')
def user_videos(username):
    """查看指定用户的公开视频列表"""
    if not valid_username(username):
        flash('用户名格式错误', 'danger')
        return redirect(url_for('home'))
    db = get_db()
    # 获取用户信息
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    # 获取该用户的视频列表
    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user['id'],)).fetchall()

    if not videos:
        videos_html = '<p class="text-muted">该用户暂无视频。</p>'
    else:
        videos_html = '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            play_url = url_for('play_video', username=username, filename=vid['filename'])
            videos_html += f'''
            <div class="col">
              <div class="card shadow-sm h-100">
                <a href="{play_url}" class="stretched-link text-decoration-none">
                  <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
                    <source src="{video_url}" type="video/mp4" />
                    您的浏览器不支持视频播放。
                  </video>
                </a>
                <div class="card-body">
                  <h5 class="card-title text-truncate" title="{vid['filename']}">{vid['filename']}</h5>
                  <a href="{download_url}" class="btn btn-sm btn-outline-primary">下载</a>
                </div>
              </div>
            </div>
            '''
        videos_html += '</div>'

    navbar = render_template_string(NAVBAR_HTML, search_query='')
    return USER_VIDEOS_HTML.format(navbar=navbar, username=username, videos=videos_html)

# ----------------------------------------
# 播放页面单独视频播放

@app.route('/video/<username>/<filename>')
def play_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    db = get_db()
    # 获取用户信息
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    # 视频资源URL
    video_url = url_for('serve_video', username=username, filename=filename)
    download_url = url_for('download_video', username=username, filename=filename)
    user_url = url_for('user_videos', username=username)

    navbar = render_template_string(NAVBAR_HTML, search_query='')
    return PLAY_VIDEO_HTML.format(navbar=navbar, username=username, filename=filename,
                                  video_url=video_url, download_url=download_url, user_url=user_url)

# ----------------------------------------
# 视频文件资源与下载

@app.route('/videos/<username>/<filename>')
def serve_video(username, filename):
    """提供视频文件的直接访问"""
    if not valid_username(username):
        abort(404)
    if not allowed_file(filename):
        abort(404)
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename)

@app.route('/download/<username>/<filename>')
def download_video(username, filename):
    """提供视频文件下载"""
    if not valid_username(username):
        abort(404)
    if not allowed_file(filename):
        abort(404)
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename, as_attachment=True)

# ----------------------------------------
# 初始化数据库命令（flask initdb）

@app.cli.command('initdb')
def initdb_command():
    """Flask自定义命令，用于初始化数据库"""
    init_db()
    print('数据库初始化完成！')

# ----------------------------------------
# 程序入口

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        with app.app_context():
            init_db()
    app.run(debug=True)
