import os
import random
import string
import sqlite3
import markdown
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    flash, send_from_directory, abort, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key_here_change_it'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                filename TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                content TEXT NOT NULL
            )
        ''')
        conn.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def generate_captcha(length=5):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def captcha_html(captcha_str):
    colors = ['red', 'goldenrod', 'green']
    spans = []
    for ch in captcha_str:
        color = random.choice(colors)
        spans.append(
            f'<span style="color:{color}; font-weight:bold; font-size:1.5em; user-select:none;">{ch}</span>'
        )
    return ''.join(spans)

TOP_NAVBAR = '''
<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('upload') }}">视频笔记平台</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" 
      aria-controls="navbarNav" aria-expanded="false" aria-label="切换导航">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        <li class="nav-item"><a class="nav-link" href="{{ url_for('upload') }}">上传</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('user_search') }}">用户名模糊搜索</a></li>
      </ul>
      <ul class="navbar-nav ms-auto">
      {% if session.get('username') %}
        <li class="nav-item"><a class="nav-link disabled">欢迎，{{ session['username'] }}</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">登出</a></li>
      {% else %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
      {% endif %}
      </ul>
    </div>
  </div>
</nav>
'''

@app.route('/', methods=['GET', 'POST'])
@login_required
def upload():
    username = session['username']
    if request.method == 'POST':
        text_content = request.form.get('text_content', '').strip()
        file = request.files.get('file')
        if not file and not text_content:
            flash('请上传视频或输入文本笔记', 'danger')
            return redirect(request.url)
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                i = 1
                base, ext = os.path.splitext(filename)
                while os.path.exists(save_path):
                    filename = f"{base}_{i}{ext}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    i += 1
                file.save(save_path)
                with sqlite3.connect('database.db') as conn:
                    c = conn.cursor()
                    c.execute('INSERT INTO videos (username, filename) VALUES (?, ?)', (username, filename))
                    conn.commit()
                flash('视频上传成功', 'success')
            else:
                flash('视频格式不支持，仅支持 mp4, avi, mkv, mov', 'danger')
                return redirect(request.url)
        if text_content:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO notes (username, content) VALUES (?, ?)', (username, text_content))
                conn.commit()
            flash('文本笔记保存成功', 'success')
        return redirect(url_for('upload'))
    return render_template_string(UPLOAD_HTML, username=username)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        flash('您已登录', 'info')
        return redirect(url_for('upload'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        captcha_input = request.form.get('captcha', '').strip()
        captcha_saved = session.get('captcha_code', '')
        if not captcha_input or captcha_input.lower() != captcha_saved.lower():
            flash('验证码错误', 'danger')
            session['captcha_code'] = generate_captcha()
            return redirect(url_for('register'))
        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return redirect(request.url)
        if password != password2:
            flash('两次密码输入不一致', 'danger')
            return redirect(request.url)
        password_hash = generate_password_hash(password)
        try:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
                conn.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('用户名已存在，请换一个', 'danger')
            session['captcha_code'] = generate_captcha()
            return redirect(request.url)
    captcha_code = generate_captcha()
    session['captcha_code'] = captcha_code
    captcha_display = captcha_html(captcha_code)
    return render_template_string(REGISTER_HTML, captcha_display=captcha_display)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        flash('您已登录', 'info')
        return redirect(url_for('upload'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').strip()
        captcha_saved = session.get('captcha_code', '')
        if not captcha_input or captcha_input.lower() != captcha_saved.lower():
            flash('验证码错误', 'danger')
            session['captcha_code'] = generate_captcha()
            return redirect(url_for('login'))
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
            row = c.fetchone()
        if row and check_password_hash(row[0], password):
            session['username'] = username
            flash('登录成功', 'success')
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('upload'))
        flash('用户名或密码错误', 'danger')
        session['captcha_code'] = generate_captcha()
        return redirect(url_for('login'))
    captcha_code = generate_captcha()
    session['captcha_code'] = captcha_code
    captcha_display = captcha_html(captcha_code)
    return render_template_string(LOGIN_HTML, captcha_display=captcha_display)

@app.route('/logout')
@login_required
def logout():
    session.pop('username', None)
    flash('已登出', 'info')
    return redirect(url_for('login'))

@app.route('/videos/<int:video_id>')
def video_detail(video_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, filename FROM videos WHERE id = ?', (video_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    username, filename = row
    return render_template_string(VIDEO_DETAIL_HTML, username=username, filename=filename)

@app.route('/notes/<int:note_id>')
def note_detail(note_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    username, raw_content = row
    content_html = markdown.markdown(raw_content, extensions=['extra', 'codehilite', 'fenced_code'])
    return render_template_string(NOTE_DETAIL_HTML, username=username, content_html=content_html)

@app.route('/notes/new', methods=['GET', 'POST'])
@login_required
def note_new():
    username = session['username']
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('文本内容不能为空', 'danger')
            return redirect(request.url)
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('INSERT INTO notes (username, content) VALUES (?, ?)', (username, content))
            conn.commit()
        flash('笔记创建成功', 'success')
        return redirect(url_for('search', username=username))
    return render_template_string(NOTE_EDIT_HTML, username=username, content='')

@app.route('/notes/edit/<int:note_id>', methods=['GET', 'POST'])
@login_required
def note_edit(note_id):
    username = session['username']
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    note_owner, content_orig = row
    if note_owner != username:
        flash('无权编辑他人笔记', 'danger')
        return redirect(url_for('search', username=note_owner))
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('文本内容不能为空', 'danger')
            return redirect(request.url)
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('UPDATE notes SET content = ? WHERE id = ?', (content, note_id))
            conn.commit()
        flash('笔记更新成功', 'success')
        return redirect(url_for('note_detail', note_id=note_id))
    return render_template_string(NOTE_EDIT_HTML, username=username, content=content_orig)

@app.route('/notes/delete/<int:note_id>', methods=['GET', 'POST'])
@login_required
def note_delete(note_id):
    username = session['username']
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    note_owner, content = row
    if note_owner != username:
        flash('无权删除他人笔记', 'danger')
        return redirect(url_for('search', username=note_owner))
    if request.method == 'POST':
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('DELETE FROM notes WHERE id = ?', (note_id,))
            conn.commit()
        flash('笔记已删除', 'success')
        return redirect(url_for('search', username=username))
    return render_template_string(NOTE_DELETE_HTML, username=username, note_id=note_id, content=content)

@app.route('/videos/manage')
@login_required
def videos_manage():
    username = session['username']
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT id, filename FROM videos WHERE username = ?', (username,))
        videos = c.fetchall()
    return render_template_string(VIDEOS_MANAGE_HTML, username=username, videos=videos)

@app.route('/videos/delete/<int:video_id>', methods=['POST'])
@login_required
def video_delete(video_id):
    username = session['username']
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, filename FROM videos WHERE id = ?', (video_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    owner, filename = row
    if owner != username:
        flash('无权删除他人视频', 'danger')
        return redirect(url_for('videos_manage'))
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except Exception:
        pass
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
    flash('视频已删除', 'success')
    return redirect(url_for('videos_manage'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/search')
def search():
    username = request.args.get('username', '').strip()
    videos = []
    notes = []
    if username:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('SELECT id, filename FROM videos WHERE username = ?', (username,))
            videos = c.fetchall()
            c.execute('SELECT id, content FROM notes WHERE username = ?', (username,))
            notes = c.fetchall()
    return render_template_string(SEARCH_HTML, username=username, videos=videos, notes=notes)

def lcs_length(a, b):
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m):
        for j in range(n):
            if a[i] == b[j]:
                dp[i+1][j+1] = dp[i][j] + 1
            else:
                dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])
    return dp[m][n]

@app.route('/usersearch', methods=['GET', 'POST'])
def user_search():
    query = ''
    best_score = -1
    results = []
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('SELECT DISTINCT username FROM users')
                all_users = [row[0] for row in c.fetchall()]
            for user in all_users:
                score = lcs_length(query, user)
                if score > best_score:
                    best_score = score
                    results = [user]
                elif score == best_score:
                    results.append(user)
    return render_template_string(USER_SEARCH_HTML, query=query, results=results)

@app.route('/ajax_user_search')
def ajax_user_search():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute("SELECT username FROM users WHERE username LIKE ? LIMIT 10", (f"%{query}%",))
            res = c.fetchall()
            results = [r[0] for r in res]
    return jsonify(results=results)

UPLOAD_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>上传视频和文本笔记</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
  ''' + TOP_NAVBAR + '''
  <div class="container mt-4">
    <h1>上传视频或Markdown文本笔记</h1>
    <p>当前用户：<strong>{{ username }}</strong></p>
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
          {{ message }}
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
        </div>
      {% endfor %}
    {% endif %}
    {% endwith %}
    <form method="post" enctype="multipart/form-data" class="mb-5">
      <div class="mb-3">
        <label for="text_content" class="form-label">Markdown文本笔记（可选）</label>
        <textarea class="form-control" id="text_content" name="text_content" rows="5" placeholder="支持Markdown语法"></textarea>
      </div>
      <div class="mb-3">
        <label for="file" class="form-label">上传视频文件</label>
        <input class="form-control" type="file" id="file" name="file" accept="video/*" />
        <div class="form-text">仅支持格式：mp4, avi, mkv, mov</div>
      </div>
      <button type="submit" class="btn btn-primary">上传</button>
    </form>

    <hr/>
    <h2>搜索用户名</h2>
    <form action="{{ url_for('search') }}" method="get" class="row g-3 mb-3 align-items-center">
      <div class="col-auto">
        <input type="text" class="form-control" name="username" placeholder="精确用户名搜索" maxlength="64" />
      </div>
      <div class="col-auto">
        <button type="submit" class="btn btn-success">搜索</button>
      </div>
    </form>
    <h2>用户名模糊搜索</h2>
    <form action="{{ url_for('user_search') }}" method="post" class="position-relative" style="max-width:500px;">
      <input type="text" id="ajax-search-input" name="query" class="form-control" placeholder="请输入用户名关键字" required autocomplete="off" />
      <button type="submit" class="btn btn-info mt-2">模糊搜索</button>
      <ul id="search-result-list" class="list-group position-absolute w-100" style="z-index:1000; display:none;"></ul>
    </form>
  </div>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script>
$(function(){
  const $input = $("#ajax-search-input");
  const $resultList = $("#search-result-list");

  $input.on('input', function(){
    const val = $(this).val().trim();
    if(val.length === 0){
      $resultList.empty().hide();
      return;
    }
    $.getJSON("{{ url_for('ajax_user_search') }}", {q: val})
    .done(function(data){
      $resultList.empty();
      if(data.results && data.results.length > 0){
        data.results.forEach(function(user){
          $resultList.append(`<li class="list-group-item list-group-item-action" style="cursor:pointer;">${user}</li>`);
        });
        $resultList.show();
      }else{
        $resultList.hide();
      }
    });
  });

  $resultList.on('click', 'li', function(){
    const username = $(this).text();
    window.location.href = "{{ url_for('search') }}?username=" + encodeURIComponent(username);
  });

  $(document).on('click', function(e){
    if(!$(e.target).closest('#ajax-search-input, #search-result-list').length){
      $resultList.hide();
    }
  });
});
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

REGISTER_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>注册 - 视频笔记平台</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
<div class="container mt-5">
  <h2>用户注册</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endif %}
  {% endwith %}
  <form method="post" class="mt-4">
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input class="form-control" id="username" name="username" type="text" maxlength="64" required/>
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input class="form-control" id="password" name="password" type="password" minlength="6" required/>
    </div>
    <div class="mb-3">
      <label for="password2" class="form-label">确认密码</label>
      <input class="form-control" id="password2" name="password2" type="password" minlength="6" required/>
    </div>
    <div class="mb-3">
      <label class="form-label">请输入验证码</label><br/>
      <div style="user-select:none; margin-bottom:0.5em;">{{ captcha_display|safe }}</div>
      <input class="form-control" name="captcha" type="text" maxlength="5" required autocomplete="off"/>
    </div>
    <button class="btn btn-primary" type="submit">注册</button>
    <a href="{{ url_for('login') }}" class="btn btn-link">已有账号？登录</a>
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
<meta charset="utf-8" />
<title>登录 - 视频笔记平台</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
<div class="container mt-5">
  <h2>用户登录</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endif %}
  {% endwith %}
  <form method="post" class="mt-4">
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input class="form-control" id="username" name="username" type="text" maxlength="64" required/>
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input class="form-control" id="password" name="password" type="password" required/>
    </div>
    <div class="mb-3">
      <label class="form-label">请输入验证码</label><br/>
      <div style="user-select:none; margin-bottom:0.5em;">{{ captcha_display|safe }}</div>
      <input class="form-control" name="captcha" type="text" maxlength="5" required autocomplete="off"/>
    </div>
    <button class="btn btn-primary" type="submit">登录</button>
    <a href="{{ url_for('register') }}" class="btn btn-link">没有账号？注册</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

SEARCH_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>搜索结果 - 用户 {{ username }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>用户 "{{ username }}" 的内容</h1>
  <a href="{{ url_for('upload') }}" class="btn btn-secondary mb-3">返回首页上传</a>

  <h3>视频列表
    {% if session.get('username') == username %}
      <a href="{{ url_for('videos_manage') }}" class="btn btn-outline-danger btn-sm ms-3">管理视频</a>
    {% endif %}
  </h3>
  {% if videos %}
  <ul class="list-group mb-4">
    {% for vid, fname in videos %}
    <li class="list-group-item"><a href="{{ url_for('video_detail', video_id=vid) }}">{{ fname }}</a></li>
    {% endfor %}
  </ul>
  {% else %}
  <p><em>该用户无上传的视频。</em></p>
  {% endif %}

  <h3>文本笔记列表
    {% if session.get('username') == username %}
      <a href="{{ url_for('note_new') }}" class="btn btn-outline-primary btn-sm ms-3">新增笔记</a>
    {% endif %}
  </h3>
  {% if notes %}
  <ul class="list-group">
    {% for nid, content in notes %}
    <li class="list-group-item d-flex justify-content-between align-items-center">
      <a href="{{ url_for('note_detail', note_id=nid) }}">{{ content[:30]|e }}{% if content|length >30 %}...{% endif %}</a>
      {% if session.get('username') == username %}
      <span>
        <a href="{{ url_for('note_edit', note_id=nid) }}" class="btn btn-sm btn-outline-secondary me-2">编辑</a>
        <a href="{{ url_for('note_delete', note_id=nid) }}" class="btn btn-sm btn-outline-danger">删除</a>
      </span>
      {% endif %}
    </li>
    {% endfor %}
  </ul>
  {% else %}
    <p><em>该用户无文本笔记。</em></p>
  {% endif %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

VIDEO_DETAIL_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>视频详情 - {{ filename }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<!-- Video.js CSS -->
<link href="https://vjs.zencdn.net/8.26.1/video-js.css" rel="stylesheet" />
<style>
  .video-container {
    max-width: 900px;
    margin: auto;
  }
</style>
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4 video-container">
  <h1>用户 "{{ username }}" 的视频</h1>
  <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary mb-3">返回用户内容</a>

  <video
    id="my-video"
    class="video-js vjs-default-skin vjs-big-play-centered"
    controls
    preload="auto"
    width="800"
    height="450"
    data-setup='{}'
  >
    <source src="{{ url_for('uploaded_file', filename=filename) }}" type="video/mp4" />
    您的浏览器不支持视频播放。
  </video>
</div>

<script src="https://vjs.zencdn.net/8.26.1/video.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
  var player = videojs('my-video');
  player.ready(function() {
    player.playbackRate(1);
    player.updatePlaybackRates([0.5, 0.75, 1, 1.25, 1.5, 2]);
  });
</script>
</body>
</html>
'''

NOTE_DETAIL_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>文本笔记详情</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>
  pre, code {
    white-space: pre-wrap;
    word-break: break-word;
    background-color: #f8f9fa;
    padding: 10px;
    border-radius: 4px;
    font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
  }
  h1,h2,h3,h4 {
    margin-top: 1em;
  }
  table {
    border-collapse: collapse; 
    width: 100%; 
    margin-bottom: 1em;
  }
  table, th, td {
    border: 1px solid #ddd;
  }
  th, td {
    padding: 8px; 
    text-align: left;
  }
</style>
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>用户 "{{ username }}" 的文本笔记</h1>
  <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary mb-3">返回用户内容</a>
  <div class="card p-3">
  {{ content_html|safe }}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

NOTE_EDIT_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>{% if content %}编辑{% else %}新建{% endif %}文本笔记 - {{ username }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.css" />
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>{% if content %}编辑{% else %}新建{% endif %} Markdown 笔记</h1>
  <form method="post" class="mb-3">
    <textarea id="content" name="content" required>{{ content }}</textarea>
    <button type="submit" class="btn btn-primary mt-3">{% if content %}保存修改{% else %}创建笔记{% endif %}</button>
    <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary ms-2 mt-3">取消</a>
  </form>
  <p class="mt-3">支持Markdown语法，保存后可查看渲染效果。</p>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.js"></script>
<script>
  var simplemde = new SimpleMDE({ element: document.getElementById("content") });
</script>
</body>
</html>
'''

NOTE_DELETE_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>删除确认 - 文本笔记</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<style>
  pre {
    white-space: pre-wrap;
    word-break: break-word;
    background-color: #f8f9fa;
    padding: 10px;
    border-radius: 4px;
  }
</style>
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>确认删除文本笔记</h1>
  <p>用户: <strong>{{ username }}</strong></p>
  <p>内容预览:</p>
  <pre>{{ content }}</pre>
  <form method="post">
    <button type="submit" class="btn btn-danger">确认删除</button>
    <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary ms-2">取消</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

VIDEOS_MANAGE_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>视频管理 - 用户 {{ username }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>用户 "{{ username }}" 的视频管理</h1>
  <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary mb-3">返回用户内容</a>

  {% if videos %}
  <table class="table table-striped">
    <thead>
      <tr>
        <th>文件名</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      {% for vid, fname in videos %}
      <tr>
        <td><a href="{{ url_for('video_detail', video_id=vid) }}">{{ fname }}</a></td>
        <td>
          <form method="post" action="{{ url_for('video_delete', video_id=vid) }}"
                onsubmit="return confirm('确认删除此视频吗？');" style="display:inline;">
            <button type="submit" class="btn btn-danger btn-sm">删除</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
    <p><em>无视频可管理。</em></p>
  {% endif %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

USER_SEARCH_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>用户名模糊搜索 - 视频笔记平台</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
</head>
<body>
''' + TOP_NAVBAR + '''
<div class="container my-4">
  <h1>用户名模糊搜索</h1>
  <form method="post" class="mb-4 position-relative" style="max-width:500px;">
    <input type="text" id="ajax-search-input" name="query" class="form-control" placeholder="请输入用户名关键字" value="{{ query }}" required autocomplete="off" />
    <button type="submit" class="btn btn-primary mt-2">搜索</button>
    <ul id="search-result-list" class="list-group position-absolute w-100" style="z-index:1000; display:none;"></ul>
  </form>

  {% if results %}
    <h3>最接近的用户名：</h3>
    <ul class="list-group">
      {% for user in results %}
        <li class="list-group-item"><a href="{{ url_for('search', username=user) }}">{{ user }}</a></li>
      {% endfor %}
    </ul>
  {% elif query %}
    <p>未找到匹配用户名</p>
  {% endif %}

  <a href="{{ url_for('upload') }}" class="btn btn-secondary mt-4">返回首页上传</a>
</div>
<script>
$(function(){
  const $input = $("#ajax-search-input");
  const $resultList = $("#search-result-list");
  $input.on('input', function(){
    const val = $(this).val().trim();
    if(val.length === 0){
      $resultList.empty().hide();
      return;
    }
    $.getJSON("{{ url_for('ajax_user_search') }}", {q: val})
    .done(function(data){
      $resultList.empty();
      if(data.results && data.results.length > 0){
        data.results.forEach(function(user){
          $resultList.append(`<li class="list-group-item list-group-item-action" style="cursor:pointer;">${user}</li>`);
        });
        $resultList.show();
      }else{
        $resultList.hide();
      }
    });
  });
  $resultList.on('click', 'li', function(){
    const username = $(this).text();
    window.location.href = "{{ url_for('search') }}?username=" + encodeURIComponent(username);
  });
  $(document).on('click', function(e){
    if(!$(e.target).closest('#ajax-search-input, #search-result-list').length){
      $resultList.hide();
    }
  });
});
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
