import os
import re
import sqlite3
import random
import string
import io
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, flash, session,
    send_from_directory, g, abort, make_response, render_template, render_template_string
)
from flask_bootstrap import Bootstrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_change_me'
app.config['UPLOAD_FOLDER'] = 'user_videos'
app.config['DATABASE'] = 'app.db'
Bootstrap(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        # 连接SQLite数据库文件
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        # 设置行结果为字典形式，方便通过列名访问
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 用户唯一ID，自增
            username TEXT UNIQUE NOT NULL,        -- 用户名唯一且非空
            password TEXT NOT NULL                 -- 密码字段，存储明文（示例，生产环境应加密）
        );
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,   -- 视频唯一ID，自增
            user_id INTEGER NOT NULL,                -- 关联的用户ID（外键）
            filename TEXT NOT NULL,                   -- 视频文件名
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 视频上传时间，默认当前时间
            FOREIGN KEY(user_id) REFERENCES users(id)       -- 建立外键约束，保证关联完整性
        );
    ''')
    db.commit()  # 提交建表事务

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db:
        db.close()  # 关闭数据库连接，释放资源

def valid_username(username):
    # 校验用户名是否只包含中文、英文、数字或下划线，长度限制1-20
    return re.fullmatch(r'[\u4e00-\u9fa5A-Za-z0-9_]{1,20}', username)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
def allowed_file(filename):
    # 文件名必须包含扩展名，且扩展名被允许
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    filename = filename.strip()
    parts = filename.rsplit('.',1)
    if len(parts)==2:
        name, ext = parts
    else:
        name, ext = filename, ''
    # 替换文件名中除中文、英文、数字、下划线、减号外的字符为下划线
    name = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9_\-]', '_', name)
    if ext:
        # 保证扩展名只含字母数字和下划线
        ext = re.sub(r'[^\w]', '', ext)
        return f"{name}.{ext.lower()}"  # 小写扩展名
    return name

def current_user_dir():
    username = session.get('username')
    if not username:
        abort(403)  # 403禁止访问，提示未登录
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)  # 用户文件夹不存在则创建
    return user_dir

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped

def lcs_length(s1,s2):
    n,m = len(s1),len(s2)
    dp=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n):
        for j in range(m):
            if s1[i]==s2[j]:
                dp[i+1][j+1]=dp[i][j]+1
            else:
                dp[i+1][j+1]=max(dp[i][j+1],dp[i+1][j])
    return dp[n][m]

def search_username_lcs(db, query, limit=5):
    if not query:
        return []
    # 查询所有用户名
    users = [row['username'] for row in db.execute('SELECT username FROM users').fetchall()]
    # 计算每个用户名和搜索query的最长公共子序列长度
    scored = [(lcs_length(query,u), u) for u in users]
    # 以匹配度降序，用户名字母序升序排序
    scored.sort(key=lambda x:(-x[0], x[1]))
    # 返回匹配度靠前的用户名列表
    return [u for _,u in scored[:limit]]

def random_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_letters, k=length))

@app.route('/captcha')
def captcha():
    text = random_captcha_text()
    session['captcha_text'] = text  # 将验证码字符串存入Session，后续验证用
    width, height = 120, 40
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('arial.ttf', 28)  # 尝试加载系统字体
    except:
        font = ImageFont.load_default()
    for _ in range(5):  # 画5条随机干扰线
        start=(random.randint(0,width), random.randint(0,height))
        end=(random.randint(0,width), random.randint(0,height))
        draw.line([start,end], fill=(160,160,160), width=1)
    for i,c in enumerate(text):  # 逐字符绘制，位置有小随机漂移
        x=5+i*22+random.randint(-2,2)
        y=5+random.randint(-2,2)
        draw.text((x,y), c, font=font, fill=(0,0,0))
    image = image.filter(ImageFilter.GaussianBlur(1))  # 轻微模糊，防止识别
    buf=io.BytesIO()
    image.save(buf, 'png')
    buf.seek(0)
    resp=make_response(buf.read())
    resp.headers['Content-Type']='image/png'
    resp.headers['Cache-Control']='no-store,no-cache,must-revalidate,max-age=0'
    return resp
    
# --- 主页，用户搜索 ---
@app.route('/')
def home():
    search_query=request.args.get('search','').strip()
    db=get_db()
    users = search_username_lcs(db, search_query) if search_query else []
    return render_template('home.html', users=users, search_query=search_query)

# --- 注册 ---
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form['username'].strip()
        password=request.form['password']
        captcha_input=request.form['captcha'].strip()
        if captcha_input != session.get('captcha_text',''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))
        if not valid_username(username):
            flash('用户名格式不正确', 'danger')
            return redirect(url_for('register'))
        if len(password)<3:
            flash('密码太短', 'danger')
            return redirect(url_for('register'))
        db=get_db()
        if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        db.execute('INSERT INTO users (username,password) VALUES (?,?)',(username,password))
        db.commit()
        user_id=db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()['id']
        session['user_id']=user_id
        session['username']=username
        flash('注册成功，欢迎！', 'success')
        return redirect(url_for('dashboard'))
    return render_template('register.html')

# --- 登录 ---
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username=request.form['username'].strip()
        password=request.form['password']
        captcha_input=request.form['captcha'].strip()
        if captcha_input != session.get('captcha_text',''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))
        db=get_db()
        user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if not user or user['password'] != password:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))
        session['user_id']=user['id']
        session['username']=user['username']
        flash('登录成功！', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# --- 登出 ---
@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('home'))

# --- 个人空间，上传及视频管理 ---
@app.route('/dashboard', methods=['GET','POST'])
@login_required
def dashboard():
    db=get_db()
    user_id=session['user_id']
    username=session['username']
    if request.method=='POST':
        if 'video' not in request.files:
            flash('未上传文件', 'danger')
            return redirect(url_for('dashboard'))
        file=request.files['video']
        if not file.filename or not allowed_file(file.filename):
            flash('文件类型不支持或文件名为空', 'danger')
            return redirect(url_for('dashboard'))
        filename=secure_filename(file.filename)
        user_dir=current_user_dir()
        fp=os.path.join(user_dir, filename)
        counter=1
        base, ext = os.path.splitext(filename)
        while os.path.exists(fp):
            filename = f"{base}_{counter}{ext}"
            fp=os.path.join(user_dir, filename)
            counter+=1
        file.save(fp)
        db.execute('INSERT INTO videos (user_id,filename) VALUES (?,?)', (user_id, filename))
        db.commit()
        flash(f'视频“{filename}”上传成功', 'success')
        return redirect(url_for('dashboard'))
    videos=db.execute('SELECT id, filename FROM videos WHERE user_id=? ORDER BY id DESC', (user_id,)).fetchall()
    return render_template('dashboard.html', username=username, videos=videos)

# --- 删除视频 ---
@app.route('/dashboard/delete/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    db=get_db()
    user_id=session['user_id']
    video=db.execute('SELECT * FROM videos WHERE id=? AND user_id=?', (video_id, user_id)).fetchone()
    if not video:
        flash('视频不存在或无权限删除', 'danger')
        return redirect(url_for('dashboard'))
    fp=os.path.join(current_user_dir(), video['filename'])
    if os.path.exists(fp):
        os.remove(fp)
    db.execute('DELETE FROM videos WHERE id=?', (video_id,))
    db.commit()
    flash(f'视频“{video["filename"]}”已删除', 'success')
    return redirect(url_for('dashboard'))

# --- 公开用户视频列表 ---
@app.route('/user/<username>')
def user_videos(username):
    if not valid_username(username):
        flash('用户名格式错误', 'danger')
        return redirect(url_for('home'))
    db=get_db()
    user=db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    videos=db.execute('SELECT id, filename FROM videos WHERE user_id=? ORDER BY id DESC', (user['id'],)).fetchall()
    return render_template('user_videos.html', username=username, videos=videos)

# --- 播放视频 ---
@app.route('/video/<username>/<filename>')
def play_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    db=get_db()
    user=db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('home'))
    video_url=url_for('serve_video', username=username, filename=filename)
    download_url=url_for('download_video', username=username, filename=filename)
    user_url=url_for('user_videos', username=username)
    return render_template('play_video.html', navbar=render_template_string(NAVBAR_HTML, search_query=''),
                           username=username, filename=filename,
                           video_url=video_url, download_url=download_url, user_url=user_url)

# --- 视频资源和下载 ---
@app.route('/videos/<username>/<filename>')
def serve_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    path=os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename)

@app.route('/download/<username>/<filename>')
def download_video(username, filename):
    if not valid_username(username) or not allowed_file(filename):
        abort(404)
    path=os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(path, filename, as_attachment=True)

# --- 初始化数据库命令 ---
@app.cli.command('initdb')
def initdb_command():
    init_db()
    print("数据库初始化完成！")

# --- 主入口 ---
if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        with app.app_context():
            init_db()
    app.run(debug=True)











## 1. base.html

<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{% block title %}视频管理系统{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>body { padding-top: 56px; }</style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-primary fixed-top">
  <div class="container-fluid px-3">
    <a class="navbar-brand" href="{{ url_for('home') }}">视频管理系统</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse"
            data-bs-target="#navbarSupportedContent" aria-controls="navbarSupportedContent"
            aria-expanded="false" aria-label="切换导航">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse justify-content-end" id="navbarSupportedContent">
      <form class="d-flex me-3" method="get" action="{{ url_for('home') }}">
        <input class="form-control me-2" type="search" placeholder="搜索用户" aria-label="搜索用户" name="search" value="{{ search_query | default('') }}">
        <button class="btn btn-light" type="submit">🔍 搜索</button>
      </form>
      <ul class="navbar-nav mb-2 mb-lg-0">
        {% if session.get('user_id') %}
          <li class="nav-item">
            <a class="nav-link" href="{{ url_for('dashboard') }}">📂 管理视频</a>
          </li>
          <li class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
              {{ session.get('username') }}
            </a>
            <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userDropdown">
              <li><a class="dropdown-item" href="{{ url_for('logout') }}">退出登录</a></li>
            </ul>
          </li>
        {% else %}
          <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>

<div class="container mt-4">
  {% block content %}{% endblock %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>


---

## 2. home.html

{% extends "base.html" %}
{% block title %}首页 - 视频管理系统{% endblock %}
{% block content %}
<h1>搜索用户</h1>
{% if search_query %}
  {% if users %}
  <div class="list-group">
    {% for user in users %}
    <a href="{{ url_for('user_videos', username=user) }}" class="list-group-item list-group-item-action">{{ user }}</a>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-muted">未找到匹配用户</p>
  {% endif %}
{% else %}
  <p class="text-muted">请输入用户名进行搜索</p>
{% endif %}
{% endblock %}


---

## 3. register.html

{% extends "base.html" %}
{% block title %}注册 - 视频管理系统{% endblock %}
{% block content %}
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
      <img src="{{ url_for('captcha') }}" id="captcha_img" style="cursor:pointer;" title="点击刷新验证码" onclick="this.src='{{ url_for('captcha') }}?'+Math.random()">
    </div>
    <input type="text" name="captcha" required class="form-control" maxlength="5" minlength="5" pattern="[A-Za-z]{5}" placeholder="请输入验证码" autocomplete="off">
  </div>
  <button type="submit" class="btn btn-success">注册</button>
  <a href="{{ url_for('home') }}" class="btn btn-link">返回首页</a>
</form>
{% endblock %}


---

## 4. login.html

{% extends "base.html" %}
{% block title %}登录 - 视频管理系统{% endblock %}
{% block content %}
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
      <img src="{{ url_for('captcha') }}" id="captcha_img" style="cursor:pointer;" title="点击刷新验证码" onclick="this.src='{{ url_for('captcha') }}?'+Math.random()">
    </div>
    <input type="text" name="captcha" required class="form-control" maxlength="5" minlength="5" pattern="[A-Za-z]{5}" placeholder="请输入验证码" autocomplete="off">
  </div>
  <button type="submit" class="btn btn-primary">登录</button>
  <a href="{{ url_for('home') }}" class="btn btn-link">返回首页</a>
</form>
{% endblock %}

---

## 5. dashboard.html


{% extends "base.html" %}
{% block title %}管理视频 - {{ username }}{% endblock %}
{% block content %}
<h1>管理视频 - {{ username }}</h1>
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
{% if videos %}
<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
  {% for video in videos %}
  <div class="col">
    <div class="card shadow-sm h-100">
      <a href="{{ url_for('play_video', username=username, filename=video.filename) }}" class="stretched-link text-decoration-none">
        <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
          <source src="{{ url_for('serve_video', username=username, filename=video.filename) }}" type="video/mp4" />
          您的浏览器不支持视频播放。
        </video>
      </a>
      <div class="card-body">
        <h5 class="card-title text-truncate" title="{{ video.filename }}">{{ video.filename }}</h5>
        <a href="{{ url_for('download_video', username=username, filename=video.filename) }}" class="btn btn-sm btn-outline-primary">下载</a>
        <form action="{{ url_for('delete_video', video_id=video.id) }}" method="post" class="d-inline" onsubmit="return confirm('确定删除视频 {{ video.filename }} 吗？');">
          <button class="btn btn-sm btn-outline-danger" type="submit">删除</button>
        </form>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<p class="text-muted">您还没有上传任何视频。</p>
{% endif %}
{% endblock %}


---

## 6. user_videos.html

{% extends "base.html" %}
{% block title %}{{ username }} 的视频列表{% endblock %}
{% block content %}
<h1>{{ username }} 的视频列表</h1>
{% if videos %}
<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
  {% for video in videos %}
  <div class="col">
    <div class="card shadow-sm h-100">
      <a href="{{ url_for('play_video', username=username, filename=video.filename) }}" class="stretched-link text-decoration-none">
        <video class="card-img-top" preload="metadata" muted style="height:160px; object-fit:cover;">
          <source src="{{ url_for('serve_video', username=username, filename=video.filename) }}" type="video/mp4" />
          您的浏览器不支持视频播放。
        </video>
      </a>
      <div class="card-body">
        <h5 class="card-title text-truncate" title="{{ video.filename }}">{{ video.filename }}</h5>
        <a href="{{ url_for('download_video', username=username, filename=video.filename) }}" class="btn btn-sm btn-outline-primary">下载</a>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<p class="text-muted">该用户暂无视频。</p>
{% endif %}
{% endblock %}


---

## 7. play_video.html

{% extends "base.html" %}
{% block title %}播放 - {{ filename }}{% endblock %}
{% block content %}
<main class="container my-4">
  <h3>{{ filename }}</h3>
  <p>上传用户：<a href="{{ url_for('user_videos', username=username) }}">{{ username }}</a></p>
  <video controls preload="metadata" autoplay style="max-width: 100%; height: auto; display:block; margin-bottom:1rem;">
    <source src="{{ video_url }}" type="video/mp4" />
    您的浏览器不支持 HTML5 视频播放。
  </video>
  <a href="{{ download_url }}" class="btn btn-primary" download>下载视频</a>
  <a href="{{ url_for('user_videos', username=username) }}" class="btn btn-outline-secondary ms-2">返回视频列表</a>
</main>
{% endblock %}




