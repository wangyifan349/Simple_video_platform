import os
import re
import sqlite3
from flask import (
    Flask, request, render_template_string, redirect, url_for,
    flash, session, send_from_directory, g, abort
)
from functools import wraps

# =============== 配置 ===============
DATABASE = 'app.db'
VIDEO_FOLDER = 'user_videos'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
SECRET_KEY = 'your_secret_key_here'  # 生产环境请更换复杂密钥

app = Flask(__name__)
app.config['DATABASE'] = DATABASE
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = VIDEO_FOLDER
os.makedirs(VIDEO_FOLDER, exist_ok=True)

# =============== 数据库操作 ===============

def get_db():
    """
    获取数据库连接，绑定到g对象，确保一个请求内复用
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row  # 方便按列名获取数据
    return db

def init_db():
    """
    初始化数据库，创建用户表和视频表
    """
    db = get_db()
    # 这里执行建表语句，两个表：
    # users表存储用户信息，username唯一，password明文（演示用途）
    # videos表存储视频文件信息，关联user_id
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 用户ID，自增主键
        username TEXT UNIQUE NOT NULL,         -- 用户名唯一且非空
        password TEXT NOT NULL                  -- 密码明文存储，生产请加密
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, -- 视频ID，自增主键
        user_id INTEGER NOT NULL,              -- 所属用户ID，外键关联users表
        filename TEXT NOT NULL,                 -- 视频文件名
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 上传时间默认当前时间
        FOREIGN KEY(user_id) REFERENCES users(id)        -- 外键约束
    );
    ''')
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    """
    请求结束关闭数据库连接
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# =============== 辅助函数 ===============

def valid_username(username):
    """
    验证用户名合法性，允许中英文，数字，下划线，1~20字符
    """
    return re.fullmatch(r'[\u4e00-\u9fa5A-Za-z0-9_]{1,20}', username) is not None

def allowed_file(filename):
    """
    判断文件是否是允许的格式
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def secure_filename(filename):
    """
    简单清理文件名，只允许中文、英文字母、数字、下划线、减号、点
    """
    filename = filename.strip()
    parts = filename.rsplit('.', 1)
    if len(parts) == 2:
        name, ext = parts
        ext = ext.lower()
    else:
        name, ext = filename, ''
    # 替换不允许字符为下划线
    name = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9_\-]', '_', name)
    if ext:
        ext = re.sub(r'[^\w]', '', ext)
        return f"{name}.{ext}"
    else:
        return name

def lcs_length(s1, s2):
    """
    计算两个字符串的最长公共子序列长度 (LCS算法)
    """
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
    """
    使用LCS最长公共子序列算法，搜索最接近query的用户名，返回前limit条结果
    """
    query = query.strip()
    if not query:
        return []
    cur = db.execute("SELECT username FROM users")
    users = [row['username'] for row in cur.fetchall()]
    scored = []
    for user in users:
        score = lcs_length(query, user)
        scored.append((score, user))
    # 按score降序和用户名升序排序
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in scored[:limit]]

def login_required(f):
    """
    登录装饰器，未登录重定向登录页面
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def current_user_dir():
    """
    获取当前登录用户视频目录，确保目录存在
    """
    username = session.get('username')
    if not username:
        abort(403)
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# ==================== 路由视图 ====================

@app.route('/')
def home():
    query = request.args.get('search', '').strip()
    db = get_db()
    users = []
    if query:
        users = search_username_lcs(db, query)
    html = f'''
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>首页 - 视频管理系统</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>body{{padding-top:2rem;}}</style>
    </head>
    <body>
    <div class="container">

      <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
        <div class="container-fluid">
          <a class="navbar-brand" href="{url_for("home")}">视频管理系统</a>
          <div class="collapse navbar-collapse">
            <ul class="navbar-nav ms-auto">
    '''
    if session.get('username'):
        html += f'''
              <li class="nav-item"><a class="nav-link" href="{url_for('dashboard')}">我的空间 ({session['username']})</a></li>
              <li class="nav-item"><a class="nav-link" href="{url_for('logout')}">退出登录</a></li>
        '''
    else:
        html += f'''
              <li class="nav-item"><a class="nav-link" href="{url_for('login')}">登录</a></li>
              <li class="nav-item"><a class="nav-link" href="{url_for('register')}">注册</a></li>
        '''
    html += '''
            </ul>
          </div>
        </div>
      </nav>

      <h1>搜索用户</h1>
      <form method="get" action="/" class="mb-4">
        <div class="input-group">
          <input type="text" name="search" class="form-control" placeholder="输入用户名搜索" value="{query}">
          <button class="btn btn-primary" type="submit">搜索</button>
        </div>
      </form>
    '''.format(query=query)

    if query:
        if users:
            html += '<h3>搜索结果:</h3><ul class="list-group mb-3">'
            for u in users:
                html += f'<li class="list-group-item"><a href="{url_for("user_videos", username=u)}">{u}</a></li>'
            html += '</ul>'
        else:
            html += '<p>没有找到匹配的用户。</p>'

    html += '''
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    '''
    return html

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
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        db.commit()
        user_id = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()['id']
        session['user_id'] = user_id
        session['username'] = username
        flash('注册成功，欢迎！', 'success')
        return redirect(url_for('dashboard'))

    # GET 方法显示注册页面
    return '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>注册 - 视频管理系统</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>body{{padding-top:3rem;max-width:400px;margin:auto;}}</style>
</head>
<body>
<div class="container">
  <h1 class="mb-4">注册</h1>
  <form method="post">
    <div class="mb-3">
      <label>用户名（中英文、数字、下划线，1-20字符）</label>
      <input type="text" name="username" required class="form-control" pattern="[\u4e00-\u9fa5A-Za-z0-9_]{1,20}" title="中英文、数字、下划线，1-20字符" maxlength="20">
    </div>
    <div class="mb-3">
      <label>密码（至少3字符）</label>
      <input type="password" name="password" required class="form-control" minlength="3">
    </div>
    <button type="submit" class="btn btn-success">注册</button>
    <a href="/" class="btn btn-link">返回首页</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or user['password'] != password:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = user['id']
        session['username'] = user['username']
        flash('登录成功！', 'success')
        return redirect(url_for('dashboard'))

    return '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>登录 - 视频管理系统</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>body{{padding-top:3rem;max-width:400px;margin:auto;}}</style>
</head>
<body>
<div class="container">
  <h1 class="mb-4">登录</h1>
  <form method="post">
    <div class="mb-3">
      <label>用户名</label>
      <input type="text" name="username" required class="form-control" maxlength="20">
    </div>
    <div class="mb-3">
      <label>密码</label>
      <input type="password" name="password" required class="form-control" minlength="3">
    </div>
    <button type="submit" class="btn btn-primary">登录</button>
    <a href="/" class="btn btn-link">返回首页</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

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
        # 数据库插入视频信息
        db.execute('INSERT INTO videos (user_id, filename) VALUES (?, ?)', (user_id, filename))
        db.commit()
        flash(f'视频“{filename}”上传成功', 'success')
        return redirect(url_for('dashboard'))

    # 查询当前用户视频
    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    html = f'''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>个人空间 - {username}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{{padding-top:2rem;}}</style>
</head>
<body>
<div class="container">

<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{url_for('home')}">视频管理系统</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav ms-auto">
        <li class="nav-item"><a class="nav-link" href="{url_for('dashboard')}">我的空间 ({username})</a></li>
        <li class="nav-item"><a class="nav-link" href="{url_for('logout')}">退出登录</a></li>
      </ul>
    </div>
  </div>
</nav>

<h1>欢迎，{username}</h1>

<div class="card mb-4 shadow-sm">
  <div class="card-header bg-primary text-white">上传新视频</div>
  <div class="card-body">
    <form method="post" enctype="multipart/form-data" class="row g-3 align-items-center">
      <div class="col-auto">
        <input type="file" name="video" accept="video/*" class="form-control" required>
      </div>
      <div class="col-auto">
        <button type="submit" class="btn btn-success">上传</button>
      </div>
    </form>
  </div>
</div>

<h2 class="mb-3">我的视频</h2>
'''

    if videos:
        html += '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            delete_url = url_for('delete_video', video_id=vid['id'])
            html += f'''
            <div class="col">
              <div class="card shadow-sm h-100">
                <video class="card-img-top" controls preload="metadata">
                  <source src="{video_url}" type="video/mp4">
                  您的浏览器不支持视频播放。
                </video>
                <div class="card-body d-flex flex-column">
                  <h5 class="card-title text-truncate" title="{vid['filename']}">{vid['filename']}</h5>
                  <div class="mt-auto d-flex justify-content-between">
                    <a href="{download_url}" class="btn btn-sm btn-outline-primary" download>下载</a>
                    <form action="{delete_url}" method="post" onsubmit="return confirm('确定删除视频 {vid["filename"]} 吗？');">
                      <button class="btn btn-sm btn-outline-danger" type="submit">删除</button>
                    </form>
                  </div>
                </div>
              </div>
            </div>
            '''
        html += '</div>'
    else:
        html += '<p>您还没有上传任何视频。</p>'

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
    filepath = os.path.join(current_user_dir(), video['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)
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
    videos = db.execute('SELECT id, filename FROM videos WHERE user_id = ? ORDER BY id DESC', (user['id'],)).fetchall()

    html = f'''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{username} 的视频列表</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{{padding-top:2rem;}}</style>
</head>
<body>
<div class="container">

<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{url_for('home')}">视频管理系统</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav ms-auto">
    '''

    if session.get('username'):
        html += f'''
        <li class="nav-item"><a class="nav-link" href="{url_for('dashboard')}">我的空间 ({session["username"]})</a></li>
        <li class="nav-item"><a class="nav-link" href="{url_for('logout')}">退出登录</a></li>
        '''
    else:
        html += f'''
        <li class="nav-item"><a class="nav-link" href="{url_for('login')}">登录</a></li>
        <li class="nav-item"><a class="nav-link" href="{url_for('register')}">注册</a></li>
        '''

    html += f'''
      </ul>
    </div>
  </div>
</nav>

<h1>{username} 的视频列表</h1>
'''

    if videos:
        html += '<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">'
        for vid in videos:
            video_url = url_for('serve_video', username=username, filename=vid['filename'])
            download_url = url_for('download_video', username=username, filename=vid['filename'])
            html += f'''
            <div class="col">
              <div class="card shadow-sm h-100">
                <video class="card-img-top" controls preload="metadata">
                  <source src="{video_url}" type="video/mp4">
                  您的浏览器不支持视频播放。
                </video>
                <div class="card-body d-flex flex-column">
                  <h5 class="card-title text-truncate" title="{vid['filename']}">{vid['filename']}</h5>
                  <a href="{download_url}" class="btn btn-sm btn-outline-primary mt-auto" download>下载</a>
                </div>
              </div>
            </div>
            '''
        html += '</div>'
    else:
        html += '<p>用户暂无视频。</p>'

    html += '''
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
    return html

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

# =============== 初始化数据库命令 ===============

@app.cli.command('initdb')
def initdb_command():
    """
    命令行初始化数据表，执行 flask initdb
    """
    init_db()
    print('数据库初始化完成！')

# =============== 主程序入口 ===============

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print('数据库文件不存在，自动初始化数据库...')
        with app.app_context():
            init_db()
    app.run(debug=True)
