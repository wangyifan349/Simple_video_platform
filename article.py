from flask import Flask, request, redirect, url_for, session, render_template_string, make_response
import sqlite3
import os
import random
import string
# ----------------------------------------
# 初始化 Flask 应用
# ----------------------------------------
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 确保存储文章的目录存在
if not os.path.exists('articles'):
    os.makedirs('articles')

# ----------------------------------------
# 初始化数据库
# ----------------------------------------
def init_db():
    """初始化数据库，创建必要的表格"""
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        filepath TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    cur.execute('''
    CREATE TABLE IF NOT EXISTS progress (
        user_id INTEGER,
        article_id INTEGER,
        page INTEGER,
        PRIMARY KEY (user_id, article_id)
    )''')

    conn.commit()
    cur.close()
    conn.close()

# ----------------------------------------
# 通用的数据库查询函数
# ----------------------------------------
def query_db(query, args=(), one=False):
    """执行数据库查询并返回结果"""
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    # 返回单个结果或多个结果
    return (rv[0] if rv else None) if one else rv

# ----------------------------------------
# 验证码生成函数
# ----------------------------------------
def generate_captcha():
    """生成一个随机的5位验证码"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=5))

# ----------------------------------------
# 最长公共子序列计算函数
# ----------------------------------------
def lcs(X, Y):
    """计算两个字符串之间的最长公共子序列"""
    m = len(X)
    n = len(Y)
    L = [[0] * (n + 1) for i in range(m + 1)]

    # 填充二维数组进行LCS计算
    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0 or j == 0:
                L[i] [j] = 0
            elif X[i-1] == Y[j-1]:
                L[i] [j] = L[i-1] [j-1] + 1
            else:
                L[i] [j] = max(L[i-1] [j], L[i] [j-1])

    return L[m] [n]

# ----------------------------------------
# 分页函数
# ----------------------------------------
def paginate_content(content, page_size):
    """将内容分页显示，每页显示一定数量的字符"""
    pages = [content[i:i + page_size] for i in range(0, len(content), page_size)]
    return pages
# ----------------------------------------
# 首页
# ----------------------------------------
@app.route('/')
def index():
    """显示主页"""
    all_articles = query_db('SELECT a.id, a.title, u.username FROM articles a JOIN users u ON a.user_id = u.id')
    username = None
    if 'user_id' in session:
        user_id = session['user_id']
        username = query_db('SELECT username FROM users WHERE id = ?', [user_id], one=True)[0]
    return render_template_string(index_html, username=username, articles=all_articles)
# ----------------------------------------
# 用户注册
# ----------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册新用户"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        captcha_input = request.form['captcha']
        
        if 'captcha' in session and captcha_input == session['captcha']:
            try:
                query_db('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                return "Username already exists."
        else:
            return "Invalid CAPTCHA."
    
    # 生成验证码并存储在会话中
    session['captcha'] = generate_captcha()
    return render_template_string(register_html, captcha=session['captcha'])
# ----------------------------------------
# 用户登录
# ----------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        captcha_input = request.form['captcha']
        
        if 'captcha' in session and captcha_input == session['captcha']:
            user = query_db('SELECT * FROM users WHERE username = ? AND password = ?', (username, password), one=True)
            if user:
                session['user_id'] = user[0]
                return redirect(url_for('index'))
            else:
                return "Invalid credentials."
        else:
            return "Invalid CAPTCHA."
    
    # 生成验证码并存储在会话中
    session['captcha'] = generate_captcha()
    return render_template_string(login_html, captcha=session['captcha'])
# ----------------------------------------
# 用户登出
# ----------------------------------------
@app.route('/logout')
def logout():
    """用户登出"""
    session.pop('user_id', None)
    return redirect(url_for('index'))
# ----------------------------------------
# 创建新文章
# ----------------------------------------
@app.route('/create', methods=['GET', 'POST'])
def create_article():
    """创建一篇新文章"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        article_id = len(os.listdir('articles'))
        filepath = f'articles/{article_id}.txt'
        with open(filepath, 'w') as f:
            f.write(title + '\n' + content)
        
        query_db('INSERT INTO articles (user_id, title, filepath) VALUES (?, ?, ?)', 
                 (session['user_id'], title, filepath))
        
        return redirect(url_for('index'))
    return render_template_string(create_article_html)
# ----------------------------------------
# 分页显示文章
# ----------------------------------------
@app.route('/article/<int:article_id>', defaults={'page': 1})
@app.route('/article/<int:article_id>/page/<int:page>')
def view_article(article_id, page):
    """查看文章详情"""
    article = query_db('SELECT title, filepath FROM articles WHERE id = ?', [article_id], one=True)
    
    if article:
        with open(article[#citation-1](citation-1), 'r') as f:
            content = f.read().split('\n', 1)
            title, body = content[0], content[#citation-1](citation-1)
            
            pages = paginate_content(body, 1000)
            num_pages = len(pages)
            
            if page > num_pages or page < 1:
                return "Page not found", 404

            return render_template_string(view_article_html, title=title, content=pages[page-1], 
                                          article_id=article_id, page=page, num_pages=num_pages)
    return "Article not found", 404
# ----------------------------------------
# 搜索文章内容
# ----------------------------------------
@app.route('/search_article/<int:article_id>')
def search_article(article_id):
    """搜索文章内容"""
    query = request.args.get('query', '')
    article = query_db('SELECT title, filepath FROM articles WHERE id = ?', [article_id], one=True)
    
    if article:
        with open(article[#citation-1](citation-1), 'r') as f:
            content = f.read()
            if query.lower() in content.lower():
                index = content.lower().index(query.lower())
                start = max(index - 30, 0)
                end = min(index + len(query) + 30, len(content))
                excerpt = content[start:end]
                return f"Result: ...{excerpt}...", 200
            else:
                return "No results found.", 200
    return "Article not found", 404
# ----------------------------------------
# 保存阅读进度
# ----------------------------------------
@app.route('/save_progress/<int:article_id>/<int:page>')
def save_progress(article_id, page):
    """保存用户的阅读进度"""
    if 'user_id' in session:
        user_id = session['user_id']
        query_db('INSERT OR REPLACE INTO progress (user_id, article_id, page) VALUES (?, ?, ?)', 
                 (user_id, article_id, page))
        return "Progress saved", 200
    return "Login required", 403

# ----------------------------------------
# 查看指定用户的所有文章
# ----------------------------------------
@app.route('/user/<username>/articles')
def view_user_articles(username):
    """查看某个用户的所有文章"""
    user_id = query_db('SELECT id FROM users WHERE username = ?', [username], one=True)
    if user_id:
        user_articles = query_db('SELECT id, title FROM articles WHERE user_id = ?', [user_id[0]])
        return render_template_string(user_articles_html, username=username, articles=user_articles)
    return "User not found", 404

# ----------------------------------------
# 内联 HTML 模板
# ----------------------------------------
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Home</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
    <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav mr-auto">
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('index') }}">Home</a>
            </li>
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('search_user') }}">Search Users</a>
            </li>
            {% if session.get('user_id') %}
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('create_article') }}">Create Article</a>
            </li>
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('logout') }}">Logout</a>
            </li>
            {% else %}
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('login') }}">Login</a>
            </li>
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('register') }}">Register</a>
            </li>
            {% endif %}
        </ul>
    </div>
</nav>
<div class="container mt-4">
    <div class="jumbotron">
        <h1 class="display-4">Welcome to the Blog</h1>
        <p class="lead">Discover articles from various authors or create your own if you're logged in!</p>
        {% if username %}
        <hr class="my-4">
        <p>Hello, {{ username }}! You can create new articles and manage your content.</p>
        {% endif %}
    </div>

    <h2>All Articles</h2>
    <ul class="list-group mb-3">
        {% for article in articles %}
        <li class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <strong>{{ article[#citation-1](citation-1) }}</strong> by <a href="{{ url_for('view_user_articles', username=article[#citation-2](citation-2)) }}">{{ article[#citation-2](citation-2) }}</a>
            </div>
            <a href="{{ url_for('view_article', article_id=article[0]) }}" class="btn btn-info btn-sm">Read More</a>
        </li>
        {% else %}
        <li class="list-group-item">No articles available</li>
        {% endfor %}
    </ul>

    <a href="{{ url_for('search_user') }}" class="btn btn-outline-primary">Search Users</a>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
"""

register_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
</nav>
<div class="container mt-4">
    <h1>Register</h1>
    <form method="post" class="needs-validation" novalidate>
        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" class="form-control" required>
            <div class="invalid-feedback">Please choose a username.</div>
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" class="form-control" required>
            <div class="invalid-feedback">Please enter a password.</div>
        </div>
        <div class="form-group">
            <label for="captcha">Captcha: {{ captcha }}</label>
            <input type="text" id="captcha" name="captcha" class="form-control" required>
            <div class="invalid-feedback">Please enter the captcha.</div>
        </div>
        <button type="submit" class="btn btn-primary">Register</button>
    </form>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
<script>
    (function() {
      'use strict';
      window.addEventListener('load', function() {
        var forms = document.getElementsByClassName('needs-validation');
        Array.prototype.filter.call(forms, function(form) {
          form.addEventListener('submit', function(event) {
            if (form.checkValidity() === false) {
              event.preventDefault();
              event.stopPropagation();
            }
            form.classList.add('was-validated');
          }, false);
        });
      }, false);
    })();
</script>
</body>
</html>
"""

login_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
</nav>
<div class="container mt-4">
    <h1>Login</h1>
    <form method="post" class="needs-validation" novalidate>
        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" class="form-control" required>
            <div class="invalid-feedback">Please enter your username.</div>
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" class="form-control" required>
            <div class="invalid-feedback">Please enter your password.</div>
        </div>
        <div class="form-group">
            <label for="captcha">Captcha: {{ captcha }}</label>
            <input type="text" id="captcha" name="captcha" class="form-control" required>
            <div class="invalid-feedback">Please enter the captcha.</div>
        </div>
        <button type="submit" class="btn btn-primary">Login</button>
    </form>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
<script>
    (function() {
      'use strict';
      window.addEventListener('load', function() {
        var forms = document.getElementsByClassName('needs-validation');
        Array.prototype.filter.call(forms, function(form) {
          form.addEventListener('submit', function(event) {
            if (form.checkValidity() === false) {
              event.preventDefault();
              event.stopPropagation();
            }
            form.classList.add('was-validated');
          }, false);
        });
      }, false);
    })();
</script>
</body>
</html>
"""

create_article_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Article</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
</nav>
<div class="container mt-4">
    <h1>Create a New Article</h1>
    <form method="post">
        <div class="form-group">
            <label for="title">Title</label>
            <input type="text" id="title" name="title" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="content">Content</label>
            <textarea id="content" name="content" class="form-control" rows="5" required></textarea>
        </div>
        <button type="submit" class="btn btn-success">Publish</button>
    </form>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
"""

view_article_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
</nav>
<div class="container mt-4">
    <h1>{{ title }}</h1>
    <div class="reading-area">
        <p>{{ content }}</p>
    </div>
    <div class="mt-3">
        {% if page > 1 %}
        <a href="{{ url_for('view_article', article_id=article_id, page=page-1) }}" class="btn btn-primary">&larr; Previous</a>
        {% endif %}
        {% if page < num_pages %}
        <a href="{{ url_for('view_article', article_id=article_id, page=page+1) }}" class="btn btn-primary">Next &rarr;</a>
        {% endif %}
    </div>
    <div>
        <a href="{{ url_for('index') }}" class="btn btn-secondary mt-3">Back to All Articles</a>
    </div>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
<style>
    .reading-area {
        max-width: 800px;
        margin: auto;
        line-height: 1.6;
        font-size: 18px;
    }
</style>
</body>
</html>
"""

user_articles_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ username }}'s Articles</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
    <a class="navbar-brand" href="{{ url_for('index') }}">Blog</a>
</nav>
<div class="container mt-4">
    <h1>Articles by {{ username }}</h1>
    <ul class="list-group mb-3">
        {% for article in articles %}
        <li class="list-group-item">
            <a href="{{ url_for('view_article', article_id=article[0]) }}">{{ article[#citation-1](citation-1) }}</a>
        </li>
        {% else %}
        <li class="list-group-item">No articles found</li>
        {% endfor %}
    </ul>
    <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Home</a>
</div>
<script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.4/dist/umd/popper.min.js"></script>
<script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
"""
# ----------------------------------------
# 启动应用程序
# ----------------------------------------
if __name__ == '__main__':
    init_db()
    app.run(debug=False)
