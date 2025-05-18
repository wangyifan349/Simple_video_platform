import os
import sqlite3
import markdown
from flask import (Flask, request, redirect, url_for, render_template_string,
                   flash, send_from_directory, abort, session)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        # 新增用户表，存用户名和密码哈希
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )''')
        # 视频笔记关联username
        c.execute('''CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            filename TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT NOT NULL
        )''')
        conn.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- 用户登录状态检测装饰器 ----------
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ---------- 注册 ----------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        flash('您已登录', 'info')
        return redirect(url_for('upload'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

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
            return redirect(request.url)

    return render_template_string(REGISTER_HTML)

# ---------- 登录 ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        flash('您已登录', 'info')
        return redirect(url_for('upload'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

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
        else:
            flash('用户名或密码错误', 'danger')
            return redirect(request.url)

    return render_template_string(LOGIN_HTML)

# ---------- 登出 ----------

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('您已安全登出', 'info')
    return redirect(url_for('login'))

# ---------- 修改上传接口，需登录后才能上传 ----------

@app.route('/', methods=['GET', 'POST'])
@login_required
def upload():
    username = session['username']

    if request.method == 'POST':
        text_content = request.form.get('text_content', '').strip()
        file = request.files.get('file')

        # 起码上传视频或写笔记中的一个
        if not file and not text_content:
            flash('请上传视频或输入文本笔记', 'danger')
            return redirect(request.url)

        # 视频上传
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

        # 笔记保存
        if text_content:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO notes (username, content) VALUES (?, ?)', (username, text_content))
                conn.commit()
            flash('文本笔记保存成功', 'success')

        return redirect(url_for('upload'))

    # GET 渲染上传页，显示当前登录用户名
    return render_template_string(UPLOAD_HTML, username=username)

# ---------- 其他涉及编辑删除等路由都加登录检测，并只允许本人操作 ----------

# 举例：编辑笔记，验证session用户名本人权限
@app.route('/notes/edit/<int:note_id>', methods=['GET', 'POST'])
@login_required
def note_edit(note_id):
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    note_owner, orig_content = row
    if note_owner != session['username']:
        flash('无权限编辑他人笔记', 'danger')
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
    return render_template_string(NOTE_EDIT_HTML, username=session['username'], content=orig_content)

# 其他权限判断类似：删除笔记、删除视频、管理视频等都加验证与登录限制

# ---------- 用户搜索页面保持公开访问 ----------

# ---------- 退出登录后首页访问跳转登录 ----------

# ...【其他代码保持不变，略去重复】...

# ------------ Bootstrap风格 注册、登录页面模板 ------------

REGISTER_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>注册 - 视频笔记平台</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
</head>
<body>
<div class="container mt-5">
  <h2>用户注册</h2>
  <form method="post" class="mt-4">
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input class="form-control" id="username" name="username" type="text" maxlength="64" required />
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input class="form-control" id="password" name="password" type="password" minlength="6" required />
    </div>
    <div class="mb-3">
      <label for="password2" class="form-label">确认密码</label>
      <input class="form-control" id="password2" name="password2" type="password" minlength="6" required />
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
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
</head>
<body>
<div class="container mt-5">
  <h2>用户登录</h2>
  <form method="post" class="mt-4">
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input class="form-control" id="username" name="username" type="text" maxlength="64" required />
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input class="form-control" id="password" name="password" type="password" required />
    </div>
    <button class="btn btn-primary" type="submit">登录</button>
    <a href="{{ url_for('register') }}" class="btn btn-link">没有账号？注册</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# --- 你可将顶部导航栏模板改成根据session是否登录显示不同按钮，例如：

# 导航包含登录状态显示用户名和退出按钮，未登录显示登录注册链接（示例略）

# 启动前执行数据库初始化
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
