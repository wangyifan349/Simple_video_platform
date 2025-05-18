"""
开发中，未完成
"""
import os
import sqlite3
import markdown
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    flash, send_from_directory, abort
)
from werkzeug.utils import secure_filename
# --------------------- 配置参数 ---------------------
# 上传文件保存目录
UPLOAD_FOLDER = 'uploads'
# 允许上传的视频格式
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov'}

# 初始化Flask应用
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 用于闪现（flash）消息安全密钥，请在生产环境换成随机字符串
app.secret_key = 'your_secret_key'

# 确保上传目录存在，如果不存在则创建
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
# --------------------- 数据库初始化 ---------------------
def init_db():
    """
    初始化SQLite数据库
    创建 videos 和 notes 两张表，分别存放视频信息和文本笔记
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        # 创建视频表：id主键，用户名，视频文件名
        c.execute('''CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            filename TEXT NOT NULL
        )''')
        # 创建笔记表：id主键，用户名，笔记文本
        c.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT NOT NULL
        )''')
        conn.commit()
# --------------------- 工具函数 ---------------------
def allowed_file(filename):
    """
    判断上传文件的扩展名是否被允许
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# --------------------- 首页上传接口 ---------------------

@app.route('/', methods=['GET', 'POST'])
def upload():
    """
    首页路由
    支持用户上传视频文件和Markdown格式的文本笔记
    """
    if request.method == 'POST':
        # 获取用户名和文本及上传文件
        username = request.form.get('username', '').strip()
        text_content = request.form.get('text_content', '').strip()
        file = request.files.get('file')

        # 用户名不能为空
        if not username:
            flash('用户名不能为空', 'danger')
            return redirect(request.url)

        # 上传内容不能全为空
        if not file and not text_content:
            flash('请上传视频或输入文本笔记', 'danger')
            return redirect(request.url)

        # 处理视频上传
        if file and file.filename != '':
            if allowed_file(file.filename):
                # 文件名安全处理
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                # 防止文件名重复，采用递增数字后缀
                i = 1
                base, ext = os.path.splitext(filename)
                while os.path.exists(save_path):
                    filename = f"{base}_{i}{ext}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    i += 1

                # 保存文件到本地目录
                file.save(save_path)

                # 写入数据库videos表
                with sqlite3.connect('database.db') as conn:
                    c = conn.cursor()
                    c.execute('INSERT INTO videos (username, filename) VALUES (?, ?)', (username, filename))
                    conn.commit()
                flash('视频上传成功', 'success')
            else:
                flash('视频格式不支持，仅支持 mp4, avi, mkv, mov', 'danger')
                return redirect(request.url)

        # 处理文本笔记保存
        if text_content:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO notes (username, content) VALUES (?, ?)', (username, text_content))
                conn.commit()
            flash('文本笔记保存成功', 'success')

        return redirect(url_for('upload'))

    # GET请求渲染上传页面
    return render_template_string(UPLOAD_HTML)

# --------------------- 精确用户名搜索页面 ---------------------

@app.route('/search')
def search():
    """
    接受用户名参数，显示该用户上传的所有视频和笔记列表
    """
    username = request.args.get('username', '').strip()
    videos, notes = [], []
    if username:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            # 查询用户视频
            c.execute('SELECT id, filename FROM videos WHERE username = ?', (username,))
            videos = c.fetchall()
            # 查询用户笔记
            c.execute('SELECT id, content FROM notes WHERE username = ?', (username,))
            notes = c.fetchall()
    return render_template_string(SEARCH_HTML, username=username, videos=videos, notes=notes)
# --------------------- 视频播放详情页 ---------------------
@app.route('/videos/<int:video_id>')
def video_detail(video_id):
    """
    视频播放页面，展示并在线播放视频
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, filename FROM videos WHERE id = ?', (video_id,))
        row = c.fetchone()

    if not row:
        abort(404)  # 视频不存在，404错误

    username, filename = row
    return render_template_string(VIDEO_DETAIL_HTML, username=username, filename=filename)

# --------------------- Markdown笔记详情页 ---------------------

@app.route('/notes/<int:note_id>')
def note_detail(note_id):
    """
    显示Markdown文本笔记详情，带代码高亮等丰富格式渲染
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()

    if not row:
        abort(404)  # 笔记不存在

    username, content_raw = row
    # 使用markdown库渲染，启用extra, fenced_code, codehilite扩展增强功能和代码高亮
    content_html = markdown.markdown(content_raw, extensions=['extra', 'codehilite', 'fenced_code'])
    return render_template_string(NOTE_DETAIL_HTML, username=username, content_html=content_html)

# --------------------- 新建Markdown笔记 ---------------------

@app.route('/notes/new', methods=['GET', 'POST'])
def note_new():
    """
    新建文本笔记，需要URL参数username指定用户
    """
    username = request.args.get('username', '').strip()
    if not username:
        flash('缺少用户名参数', 'danger')
        return redirect(url_for('upload'))

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('文本内容不能为空', 'danger')
            return redirect(request.url)

        # 插入笔记数据库
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('INSERT INTO notes (username, content) VALUES (?, ?)', (username, content))
            conn.commit()
        flash('笔记创建成功', 'success')
        return redirect(url_for('search', username=username))

    # GET渲染新建笔记编辑页
    return render_template_string(NOTE_EDIT_HTML, username=username, content='')

# --------------------- 编辑已有笔记 ---------------------

@app.route('/notes/edit/<int:note_id>', methods=['GET', 'POST'])
def note_edit(note_id):
    """
    编辑指定id的Markdown笔记
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()

    if not row:
        abort(404)

    username, orig_content = row

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('文本内容不能为空', 'danger')
            return redirect(request.url)
        # 更新数据库笔记内容
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('UPDATE notes SET content = ? WHERE id = ?', (content, note_id))
            conn.commit()
        flash('笔记更新成功', 'success')
        return redirect(url_for('note_detail', note_id=note_id))
    # GET渲染编辑页，页面带SimpleMDE富文本编辑器（详细见模板）
    return render_template_string(NOTE_EDIT_HTML, username=username, content=orig_content)
# --------------------- 删除笔记 ---------------------
@app.route('/notes/delete/<int:note_id>', methods=['GET', 'POST'])
def note_delete(note_id):
    """
    GET显示删除确认页面，POST执行笔记删除
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, content FROM notes WHERE id = ?', (note_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    username, content = row
    if request.method == 'POST':
        # 删除笔记
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('DELETE FROM notes WHERE id = ?', (note_id,))
            conn.commit()
        flash('笔记已删除', 'success')
        return redirect(url_for('search', username=username))
    # GET渲染确认删除页面
    return render_template_string(NOTE_DELETE_HTML, username=username, note_id=note_id, content=content)
# --------------------- 视频管理页面 ---------------------
@app.route('/videos/manage')
def videos_manage():
    """
    用户视频管理页面，显示该用户所有视频，允许删除
    """
    username = request.args.get('username', '').strip()
    if not username:
        flash('缺少用户名参数', 'danger')
        return redirect(url_for('upload'))

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        # 取出该用户所有视频id和文件名
        c.execute('SELECT id, filename FROM videos WHERE username = ?', (username,))
        videos = c.fetchall()

    return render_template_string(VIDEOS_MANAGE_HTML, username=username, videos=videos)
# --------------------- 视频删除操作 ---------------------
@app.route('/videos/delete/<int:video_id>', methods=['POST'])
def video_delete(video_id):
    """
    删除视频文件及其数据库信息
    """
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('SELECT username, filename FROM videos WHERE id = ?', (video_id,))
        row = c.fetchone()
    if not row:
        abort(404)
    username, filename = row
    # 删除文件系统中的视频文件（异常忽略）
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except Exception:
        pass
    # 删除数据库记录
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
    flash('视频已删除', 'success')
    return redirect(url_for('videos_manage', username=username))
# --------------------- 视频文件获取（静态资源） ---------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """
    提供视频文件访问，供视频播放用
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
# --------------------- 计算最长公共子序列 ---------------------
def lcs_length(s1, s2):
    """
    计算字符串s1和s2的最长公共子序列长度，用作用户名相似度匹配指标
    使用动态规划方法
    """
    m, n = len(s1), len(s2)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m):
        for j in range(n):
            if s1[i] == s2[j]:
                dp[i+1][j+1] = dp[i][j] + 1
            else:
                dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])
    return dp[m][n]
# --------------------- 用户名模糊搜索 ---------------------
@app.route('/usersearch', methods=['GET', 'POST'])
def user_search():
    """
    用户名模糊搜索页面
    POST时以输入字符串与所有用户计算LCS最长公共子序列长度，返回最接近用户名列表
    """
    query = ''
    best_score = -1
    results = []

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            flash('请输入用户名进行搜索', 'danger')
            return redirect(request.url)

        # 从两个表分别获取所有去重用户名
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('SELECT DISTINCT username FROM videos')
            users_videos = {row[0] for row in c.fetchall()}
            c.execute('SELECT DISTINCT username FROM notes')
            users_notes = {row[0] for row in c.fetchall()}
            all_users = users_videos.union(users_notes)

        # 计算LCS并找出最高得分用户名列表（可能多条同得分）
        for user in all_users:
            score = lcs_length(query, user)
            if score > best_score:
                best_score = score
                results = [user]
            elif score == best_score:
                results.append(user)

    return render_template_string(USER_SEARCH_HTML, query=query, results=results)

# --------------------- 各页面HTML模板 ---------------------

# 顶部导航栏公用HTML，Bootstrap 5 风格，加入代码中方便维护
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
    </div>
  </div>
</nav>
'''

# 以下所有HTML模版都内嵌顶部导航栏

# 首页上传视频和文本笔记模板
UPLOAD_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>上传视频和文本笔记</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
  ''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>上传视频或Markdown文本笔记</h1>

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
      <label for="username" class="form-label">用户名 <span class="text-danger">*</span></label>
      <input type="text" class="form-control" id="username" name="username" required maxlength="64" placeholder="请输入用户名">
    </div>
    <div class="mb-3">
      <label for="text_content" class="form-label">Markdown 文本笔记</label>
      <textarea class="form-control" id="text_content" name="text_content" rows="5" placeholder="可选，支持Markdown格式"></textarea>
    </div>
    <div class="mb-3">
      <label for="file" class="form-label">上传视频文件</label>
      <input class="form-control" type="file" id="file" name="file" accept="video/*">
      <div class="form-text">仅支持格式：mp4, avi, mkv, mov</div>
    </div>
    <button type="submit" class="btn btn-primary">上传</button>
  </form>

  <hr>

  <h2>搜索用户名</h2>
  <form action="{{ url_for('search') }}" method="get" class="row g-3 align-items-center mb-3">
    <div class="col-auto">
      <input type="text" class="form-control" name="username" placeholder="精确用户名搜索" maxlength="64">
    </div>
    <div class="col-auto">
      <button type="submit" class="btn btn-success">搜索</button>
    </div>
  </form>

  <h2>用户名模糊搜索</h2>
  <form action="{{ url_for('user_search') }}" method="post" class="row g-3 align-items-center">
    <div class="col-auto">
      <input type="text" class="form-control" name="query" placeholder="模糊用户名搜索" required>
    </div>
    <div class="col-auto">
      <button type="submit" class="btn btn-info">模糊搜索</button>
    </div>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# 搜索结果页面 - 显示指定用户名的视频和笔记列表
SEARCH_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>搜索结果 - {{ username }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
  ''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>用户 "{{ username }}" 的内容</h1>
  <a href="{{ url_for('upload') }}" class="btn btn-secondary mb-3">返回首页上传</a>

  <h3>视频列表
    <a href="{{ url_for('videos_manage', username=username) }}" class="btn btn-outline-danger btn-sm ms-3">管理视频</a>
  </h3>
  {% if videos %}
    <ul class="list-group mb-4">
      {% for vid, fname in videos %}
        <li class="list-group-item">
          <a href="{{ url_for('video_detail', video_id=vid) }}">{{ fname }}</a>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p><em>该用户无上传视频。</em></p>
  {% endif %}

  <h3>文本笔记列表
    <a href="{{ url_for('note_new', username=username) }}" class="btn btn-outline-primary btn-sm ms-3">新增笔记</a>
  </h3>
  {% if notes %}
    <ul class="list-group">
      {% for nid, content in notes %}
        <li class="list-group-item d-flex justify-content-between align-items-center">
          <a href="{{ url_for('note_detail', note_id=nid) }}">
            {{ content[:30] | e }}{% if content|length > 30 %}...{% endif %}
          </a>
          <span>
            <a href="{{ url_for('note_edit', note_id=nid) }}" class="btn btn-sm btn-outline-secondary me-2">编辑</a>
            <a href="{{ url_for('note_delete', note_id=nid) }}" class="btn btn-sm btn-outline-danger">删除</a>
          </span>
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

# 视频播放页面模板
VIDEO_DETAIL_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>视频详情 - {{ filename }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
  ''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>用户 "{{ username }}" 的视频</h1>
  <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary mb-3">返回用户内容</a>

  <p><strong>文件名：</strong>{{ filename }}</p>
  <video width="640" height="360" controls>
    <source src="{{ url_for('uploaded_file', filename=filename) }}" type="video/mp4">
    您的浏览器不支持视频播放。
  </video>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# Markdown笔记详情页模板，带代码高亮渲染
NOTE_DETAIL_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>文本笔记详情</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
    {{ content_html | safe }}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# Markdown笔记编辑（新建/编辑共用）页模板，集成SimpleMDE编辑器
NOTE_EDIT_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{% if content %}编辑{% else %}新建{% endif %}文本笔记 - {{ username }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <!-- 引入SimpleMDE CSS -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.css">
</head>
<body>
  ''' + TOP_NAVBAR + '''
<div class="container mt-4">
  <h1>{% if content %}编辑{% else %}新建{% endif %} Markdown 笔记</h1>
  <form method="post" class="mb-3">
    <!-- textarea由SimpleMDE转换为Markdown富文本编辑器 -->
    <textarea id="content" name="content" required>{{ content }}</textarea>
    <button type="submit" class="btn btn-primary mt-3">{% if content %}保存修改{% else %}创建笔记{% endif %}</button>
    <a href="{{ url_for('search', username=username) }}" class="btn btn-secondary ms-2 mt-3">取消</a>
  </form>
  <p class="mt-3">支持Markdown语法，保存后可查看渲染效果。</p>
</div>
<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<!-- SimpleMDE JS -->
<script src="https://cdn.jsdelivr.net/simplemde/latest/simplemde.min.js"></script>
<script>
  // 初始化SimpleMDE编辑器，提供实时高亮和预览功能
  var simplemde = new SimpleMDE({ element: document.getElementById("content") });
</script>
</body>
</html>
'''

# 删除笔记确认页面模板
NOTE_DELETE_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>删除确认 - 文本笔记</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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

# 视频管理页面模板，可删除视频
VIDEOS_MANAGE_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>视频管理 - 用户 {{ username }}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
                onsubmit="return confirm('确认删除此视频？');" style="display:inline;">
            <button type="submit" class="btn btn-danger btn-sm">删除</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
    <p><em>该用户无视频可管理。</em></p>
  {% endif %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# 用户名模糊搜索页面模板
USER_SEARCH_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>用户名模糊搜索 - 视频与笔记平台</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
  ''' + TOP_NAVBAR + '''
<div class="container my-4">
  <h1>用户名模糊搜索</h1>
  <form method="post" class="mb-4">
    <div class="input-group">
      <input type="text" name="query" class="form-control" placeholder="请输入用户名关键字" required value="{{ query }}">
      <button type="submit" class="btn btn-primary">搜索</button>
    </div>
  </form>

  {% if results %}
    <h3>最接近的用户名：</h3>
    <ul class="list-group">
      {% for user in results %}
        <li class="list-group-item">
          <a href="{{ url_for('search', username=user) }}">{{ user }}</a>
        </li>
      {% endfor %}
    </ul>
  {% elif query %}
    <p>未找到匹配用户名</p>
  {% endif %}

  <a href="{{ url_for('upload') }}" class="btn btn-secondary mt-4">返回首页上传</a>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
# --------------------- 程序入口 ---------------------
if __name__ == '__main__':
    # 启动前初始化数据库
    init_db()
    # 开启Debug模式启动Flask服务
    app.run(debug=True)
