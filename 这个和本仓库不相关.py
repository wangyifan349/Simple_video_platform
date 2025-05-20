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
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db
def init_db():
    db = get_db()
    db.executescript('''
    -- 用户表，储存每个用户的账号和密码
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,    -- 用户ID，自增主键，唯一标识用户
        username TEXT UNIQUE NOT NULL,            -- 用户名，唯一且不能为空
        password TEXT NOT NULL                     -- 密码（演示明文存储，正式请加密）
    );
    -- 视频表，储存用户上传的视频信息
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,    -- 视频ID，自增主键，唯一标识视频
        user_id INTEGER NOT NULL,                 -- 所属用户的ID，外键关联users表id
        filename TEXT NOT NULL,                   -- 视频文件名
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 上传时间，默认当前时间
        FOREIGN KEY(user_id) REFERENCES users(id)        -- 外键约束，确保用户存在
    );
    ''')
    db.commit()



@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ----------------------------------------
# 工具函数

def valid_username(username):
    return re.fullmatch(r'[\u4e00-\u9fa5A-Za-z0-9_]{1,20}', username) is not None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    filename = filename.strip()
    parts = filename.rsplit('.',1)
    if len(parts) == 2:
        name, ext = parts
        ext = ext.lower()
    else:
        name, ext = filename, ''
    name = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9_\-]', '_', name)
    if ext:
        ext = re.sub(r'[^\w]', '', ext)
        return f"{name}.{ext}"
    else:
        return name

def lcs_length(s1,s2):
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
    res = []
    for i in range(min(limit, len(scored))):
        res.append(scored[i][1])
    return res

def login_required(f):
    @wraps(f)
    def decor(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decor

def current_user_dir():
    username = session.get('username')
    if not username:
        abort(403)
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# ----------------------------------------
# 验证码处理

def random_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_letters,k=length))

@app.route('/captcha')
def captcha():
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
# 导航栏HTML字符串（Bootstrap 5响应式）

NAVBAR_HTML = '''
<nav class="navbar navbar-expand-lg navbar-dark bg-primary">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">视频管理系统</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" 
      data-bs-target="#navbarContent" aria-controls="navbarContent"
      aria-expanded="false" aria-label="切换导航">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarContent">
      <form class="d-flex ms-auto me-3" method="get" action="/" >
        <input class="form-control me-2" type="search" placeholder="搜索用户" aria-label="搜索"
          name="search" value="{{ search_query|default('') }}">
        <button class="btn btn-light" type="submit">🔍 搜索</button>
      </form>
      <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
        {% if session.get('user_id') %}
          <li class="nav-item"><a href="/dashboard" class="nav-link">📂 管理视频</a></li>
          <li class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" id="userMenu" role="button" data-bs-toggle="dropdown" aria-expanded="false">{{ session.get('username') }}</a>
            <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userMenu">
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
# 首页：搜索用户，显示搜索结果

@app.route('/')
def home():
    search_query = request.args.get('search', '').strip()
    db = get_db()
    users = []
    if search_query:
        users = search_username_lcs(db, search_query)

    # 构造HTML
    html = '''
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <title>首页 - 视频管理系统</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
      <style>body{padding-top:4rem;}</style>
    </head>
    <body>
    '''
    # 渲染导航栏
    html += render_template_string(NAVBAR_HTML, search_query=search_query)

    html += '''
    <div class="container mt-4">
      <h1>搜索用户</h1>
    '''
    if search_query:
        if users:
            html += '<div class="list-group">'
            for u in users:
                html += f'<a href="/user/{u}" class="list-group-item list-group-item-action">{u}</a>'
            html += '</div>'
        else:
            html += '<p class="text-muted">未找到匹配用户</p>'
    else:
        html += '<p class="text-muted">请输入用户名进行搜索</p>'
    html += '''
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body></html>
    '''
    return html

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
        # 检查用户名
        if db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        db.commit()
        user_id = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']
        session['user_id'] = user_id
        session['username'] = username
        flash('注册成功，欢迎！', 'success')
        return redirect(url_for('dashboard'))

    html = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>注册 - 视频管理系统</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body{padding-top:4rem;max-width:400px;margin:auto;}</style>
</head>
<body>
''' + NAVBAR_HTML + '''
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
    return html

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
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or user['password'] != password:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = user['id']
        session['username'] = user['username']
        flash('登录成功！', 'success')
        return redirect(url_for('dashboard'))

    html = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>登录 - 视频管理系统</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body{padding-top:4rem;max-width:400px;margin:auto;}</style>
</head>
<body>
''' + NAVBAR_HTML + '''
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
    return html

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
        file.save(filepath)
        db.execute('INSERT INTO videos (user_id, filename) VALUES (?, ?)', (user_id, filename))
        db.commit()
        flash(f'视频“{filename}”上传成功！', 'success')
        return redirect(url_for('dashboard'))

    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    html = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>管理视频 - ''' + username + '''</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body{padding-top:4rem;}</style>
</head>
<body>
'''
    html += render_template_string(NAVBAR_HTML, search_query='')

    html += '''
<div class="container mt-4">
  <h1>管理视频 - ''' + username + '''</h1>
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
'''

    if not videos:
        html += '<p class="text-muted">您还没有上传任何视频。</p>'
    else:
        html += '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        # 手动循环
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            delete_url = url_for('delete_video', video_id=vid['id'])
            html += '''
            <div class="col">
              <div class="card shadow-sm h-100">
                <a href="''' + url_for('play_video', username=username, filename=vid['filename']) + '''" class="stretched-link text-decoration-none">
                  <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
                    <source src="''' + video_url + '''" type="video/mp4" />
                    您的浏览器不支持视频播放。
                  </video>
                </a>
                <div class="card-body">
                  <h5 class="card-title text-truncate" title="''' + vid['filename'] + '''">''' + vid['filename'] + '''</h5>
                  <a href="''' + download_url + '''" class="btn btn-sm btn-outline-primary">下载</a>
                  <form action="''' + delete_url + '''" method="post" class="d-inline" onsubmit="return confirm('确定删除视频 ''' + vid['filename'] + ''' 吗？');">
                    <button class="btn btn-sm btn-outline-danger" type="submit">删除</button>
                  </form>
                </div>
              </div>
            </div>
            '''
        html += '</div>'

    html += '''
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
    return html

@app.route('/dashboard/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    db = get_db()
    user_id = session['user_id']
    video = db.execute('SELECT * FROM videos WHERE id = ? AND user_id = ?', (video_id, user_id)).fetchone()
    if not video:
        flash('视频不存在或无权限删除', 'danger')
        return redirect(url_for('dashboard'))
    fp = os.path.join(current_user_dir(), video['filename'])
    if os.path.exists(fp):
        os.remove(fp)
    db.execute('DELETE FROM videos WHERE id = ?', (video_id,))
    db.commit()
    flash(f'视频“{video["filename"]}”已删除', 'success')
    return redirect(url_for('dashboard'))
# ----------------------------------------
# 用户视频列表页面
@app.route('/user/<username>')
def user_videos(username):
    if not valid_username(username):
        flash('用户名格式错误', 'danger')
        return redirect(url_for('home'))
    db = get_db()
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user['id'],)).fetchall()

    html = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>''' + username + ''' 的视频列表</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body{padding-top:4rem;}</style>
</head>
<body>
'''
    html += render_template_string(NAVBAR_HTML, search_query='')

    html += f'''
<div class="container mt-4">
  <h1>{username} 的视频列表</h1>
'''

    if not videos:
        html += '<p class="text-muted">该用户暂无视频。</p>'
    else:
        html += '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            play_url = url_for('play_video', username=username, filename=vid['filename'])
            html += '''
            <div class="col">
              <div class="card shadow-sm h-100">
                <a href="''' + play_url + '''" class="stretched-link text-decoration-none">
                  <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
                    <source src="''' + video_url + '''" type="video/mp4" />
                    您的浏览器不支持视频播放。
                  </video>
                </a>
                <div class="card-body">
                  <h5 class="card-title text-truncate" title="''' + vid['filename'] + '''">''' + vid['filename'] + '''</h5>
                  <a href="''' + download_url + '''" class="btn btn-sm btn-outline-primary">下载</a>
                </div>
              </div>
            </div>
            '''
        html += '</div>'

    html += '''
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
    return html
# ----------------------------------------
# 播放页面单独视频播放

@app.route('/video/<username>/<filename>')
def play_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    db = get_db()
    user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    video_url = url_for('serve_video', username=username, filename=filename)
    download_url = url_for('download_video', username=username, filename=filename)

    html = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>播放 - ''' + filename + '''</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>body{padding-top:4rem;}</style>
</head>
<body>
'''
    html += render_template_string(NAVBAR_HTML, search_query='')

    html += f'''
<main class="container my-4">
  <h3>{filename}</h3>
  <p>上传用户：<a href="{ url_for('user_videos', username=username) }">{username}</a></p>
  <video controls preload="metadata" autoplay style="max-width: 100%; height: auto; display:block; margin-bottom:1rem;">
    <source src="{video_url}" type="video/mp4" />
    您的浏览器不支持HTML5视频播放。
  </video>
  <a href="{download_url}" class="btn btn-primary" download>下载视频</a>
  <a href="{url_for('user_videos', username=username)}" class="btn btn-outline-secondary ms-2">返回视频列表</a>
</main>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
    return html
# ----------------------------------------
# 视频文件资源与下载
@app.route('/videos/<username>/<filename>')
def serve_video(username, filename):
    if not valid_username(username):
        abort(404)
    if not allowed_file(filename):
        abort(404)
    path = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename)

@app.route('/download/<username>/<filename>')
def download_video(username, filename):
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
    init_db()
    print('数据库初始化完成！')
# ----------------------------------------
# 程序入口

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        with app.app_context():
            init_db()
    app.run(debug=True)
