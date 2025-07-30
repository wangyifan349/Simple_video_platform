import sqlite3
from flask import Flask, g, request, session, redirect, url_for, flash, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'please_change_to_your_own_secret_key'     # 应用密钥
app.config['DATABASE_PATH'] = 'microblog.db'                          # SQLite 数据库文件路径

def get_database_connection():                                        # 获取数据库连接
    if 'database_connection' not in g:
        connection = sqlite3.connect(app.config['DATABASE_PATH'])
        connection.row_factory = sqlite3.Row                          # 使查询结果可通过列名访问
        g.database_connection = connection
    return g.database_connection

@app.teardown_appcontext
def close_database_connection(exception):                             # 关闭数据库连接
    connection = g.pop('database_connection', None)
    if connection:
        connection.close()

def initialize_database():                                            # 初始化数据库表
    connection = get_database_connection()
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS user (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS post (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES user(id)
    );
    """)                                                           # 创建用户表和帖子表
    connection.commit()

def login_required(view_function):                                   # 登录保护装饰器
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view_function(*args, **kwargs)
    return wrapped_view

def longest_common_subsequence_length(a, b):                         # 计算 LCS 长度
    length_a, length_b = len(a), len(b)
    dp = [[0] * (length_b + 1) for _ in range(length_a + 1)]
    for i in range(length_a - 1, -1, -1):
        for j in range(length_b - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    return dp[0][0]

TPL_BASE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{{ title or "MicroBlog" }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
        rel="stylesheet" crossorigin="anonymous">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">MicroBlog</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="{{ url_for('search') }}">搜索用户</a></li>
      </ul>
      <ul class="navbar-nav">
        {% if session.username %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('profile', user_id=session.user_id) }}">{{ session.username }}</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">登出</a></li>
        {% else %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>
<div class="container">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-warning">
        {% for message in messages %}<div>{{ message }}</div>{% endfor %}
      </div>
    {% endif %}
  {% endwith %}
  {% block body %}{% endblock %}
</div>
</body>
</html>
"""

TPL_INDEX = """
{% extends none %}
""" + TPL_BASE + """
{% block body %}
  {% if session.user_id %}
  <div class="card mb-4">
    <div class="card-body">
      <form method="post" action="{{ url_for('create_post') }}">
        <div class="mb-3">
          <textarea name="content" class="form-control" rows="3" placeholder="有什么新鲜事？"></textarea>
        </div>
        <button class="btn btn-primary">发布</button>
      </form>
    </div>
  </div>
  {% endif %}
  {% for post in posts %}
  <div class="card mb-3">
    <div class="card-header">
      <a href="{{ url_for('profile', user_id=post.user_id) }}">{{ post.username }}</a>
      <small class="text-muted">{{ post.created_at }}</small>
      {% if session.user_id == post.user_id %}
        <form method="post" action="{{ url_for('delete_post', post_id=post.id) }}" class="d-inline float-end">
          <button class="btn btn-sm btn-danger">删除</button>
        </form>
      {% endif %}
    </div>
    <div class="card-body">
      <p class="card-text">{{ post.content }}</p>
    </div>
  </div>
  {% else %}
  <p class="text-center text-muted">暂无说说。</p>
  {% endfor %}
{% endblock %}
"""

TPL_REGISTER = """
{% extends none %}
""" + TPL_BASE + """
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h3>注册</h3>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">用户名</label>
        <input name="username" class="form-control">
      </div>
      <div class="mb-3">
        <label class="form-label">密码</label>
        <input name="password" type="password" class="form-control">
      </div>
      <button class="btn btn-success">注册</button>
    </form>
  </div>
</div>
{% endblock %}
"""

TPL_LOGIN = """
{% extends none %}
""" + TPL_BASE + """
{% block body %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h3>登录</h3>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">用户名</label>
        <input name="username" class="form-control">
      </div>
      <div class="mb-3">
        <label class="form-label">密码</label>
        <input name="password" type="password" class="form-control">
      </div>
      <button class="btn btn-primary">登录</button>
    </form>
  </div>
</div>
{% endblock %}
"""

TPL_PROFILE = """
{% extends none %}
""" + TPL_BASE + """
{% block body %}
<h3>{{ user.username }} 的主页</h3>
{% for post in posts %}
<div class="card mb-2">
  <div class="card-body">
    <p>{{ post.content }}</p>
    <small class="text-muted">{{ post.created_at }}</small>
    {% if session.user_id == user.id %}
      <form method="post" action="{{ url_for('delete_post', post_id=post.id) }}" class="d-inline float-end">
        <button class="btn btn-sm btn-danger">删除</button>
      </form>
    {% endif %}
  </div>
</div>
{% else %}
<p class="text-muted">还没有说说。</p>
{% endfor %}
{% endblock %}
"""

TPL_SEARCH = """
{% extends none %}
""" + TPL_BASE + """
{% block body %}
<h3>按用户名搜索</h3>
<form method="post" class="input-group mb-3">
  <input name="search_query" value="{{ search_query }}" class="form-control" placeholder="输入用户名片段">
  <button class="btn btn-outline-secondary">搜索</button>
</form>
<ul class="list-group">
  {% for user_item in results %}
    <li class="list-group-item">
      <a href="{{ url_for('profile', user_id=user_item.id) }}">{{ user_item.username }}</a>
    </li>
  {% else %}
    {% if search_query %}<li class="list-group-item text-muted">没有匹配用户</li>{% endif %}
  {% endfor %}
</ul>
{% endblock %}
"""

@app.route('/')
def index():                                                      # 首页路由
    connection = get_database_connection()
    posts = connection.execute(
        "SELECT p.id, p.content, p.created_at, u.username, u.id AS user_id "
        "FROM post p JOIN user u ON p.user_id = u.id "
        "ORDER BY p.created_at DESC"                               # 按时间倒序查询所有说说
    ).fetchall()
    return render_template_string(TPL_INDEX, posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():                                                   # 注册路由
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        connection = get_database_connection()
        error_message = None
        if not username or not password:
            error_message = '用户名和密码不能为空'
        elif connection.execute(
            "SELECT 1 FROM user WHERE username = ?", (username,)   # 检查用户名是否已存在
        ).fetchone():
            error_message = '用户名已存在'
        if error_message:
            flash(error_message)
        else:
            connection.execute(
                "INSERT INTO user(username, password_hash) VALUES(?, ?)",  # 插入新用户
                (username, generate_password_hash(password))
            )
            connection.commit()
            flash('注册成功，请登录')
            return redirect(url_for('login'))
    return render_template_string(TPL_REGISTER)

@app.route('/login', methods=['GET', 'POST'])
def login():                                                      # 登录路由
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        connection = get_database_connection()
        user_record = connection.execute(
            "SELECT * FROM user WHERE username = ?", (username,)   # 查询用户名
        ).fetchone()
        error_message = None
        if user_record is None or not check_password_hash(user_record['password_hash'], password):
            error_message = '用户名或密码错误'
        if error_message:
            flash(error_message)
        else:
            session.clear()
            session['user_id'] = user_record['id']
            session['username'] = user_record['username']
            return redirect(url_for('index'))
    return render_template_string(TPL_LOGIN)

@app.route('/logout')
def logout():                                                     # 登出路由
    session.clear()
    return redirect(url_for('index'))

@app.route('/create_post', methods=['POST'])
@login_required
def create_post():                                                # 发布说说路由
    content = request.form['content'].strip()
    if content:
        connection = get_database_connection()
        connection.execute(
            "INSERT INTO post(user_id, content, created_at) VALUES(?, ?, ?)",  # 插入新说说
            (session['user_id'], content, datetime.now().isoformat(sep=' ', timespec='seconds'))
        )
        connection.commit()
    return redirect(url_for('index'))

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):                                         # 删除说说路由
    connection = get_database_connection()
    connection.execute(
        "DELETE FROM post WHERE id = ? AND user_id = ?",         # 仅删除属于当前用户的说说
        (post_id, session['user_id'])
    )
    connection.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/profile/<int:user_id>')
def profile(user_id):                                             # 用户个人主页路由
    connection = get_database_connection()
    user_record = connection.execute(
        "SELECT id, username FROM user WHERE id = ?", (user_id,)  # 查询用户信息
    ).fetchone()
    if user_record is None:
        flash('用户不存在')
        return redirect(url_for('index'))
    posts = connection.execute(
        "SELECT id, content, created_at FROM post WHERE user_id = ? ORDER BY created_at DESC",  # 查询该用户说说
        (user_id,)
    ).fetchall()
    return render_template_string(TPL_PROFILE, user=user_record, posts=posts)

@app.route('/search', methods=['GET', 'POST'])
def search():                                                     # 用户搜索路由
    results = []
    search_query = ''
    if request.method == 'POST':
        search_query = request.form['search_query'].strip()
        connection = get_database_connection()
        users = connection.execute("SELECT id, username FROM user").fetchall()  # 获取所有用户
        scored_list = []
        for user_item in users:
            score = longest_common_subsequence_length(search_query.lower(), user_item['username'].lower())
            if score > 0:
                scored_list.append((score, user_item))
        scored_list.sort(key=lambda x: x[0], reverse=True)         # 按 LCS 长度降序排序
        results = [item for _, item in scored_list]
    return render_template_string(TPL_SEARCH, results=results, search_query=search_query)

if __name__ == '__main__':
    with app.app_context():
        initialize_database()                                    # 启动时初始化数据库
    app.run(debug=True)
