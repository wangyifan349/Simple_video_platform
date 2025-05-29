import os
import re
import random
import string
from io import BytesIO

from flask import (
    Flask, render_template_string, request, redirect, url_for, flash, session,
    send_file, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from captcha.image import ImageCaptcha
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = '请替换为你的随机密钥'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

def allowed_file(filename):
    # 文件扩展名检查
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    # 过滤不可见和路径分隔符，不严格替换中文或特殊字符，保留中文
    filename = filename.strip().replace('/', '').replace('\\', '').replace('\0','')
    filename = re.sub(r'[<>:"|?*]', '', filename)
    filename = filename.replace('\n', '').replace('\r', '')
    return filename

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    videos = db.relationship('Video', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

def random_captcha_text(length=4):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

image_captcha = ImageCaptcha(width=160, height=60)
def generate_captcha_img(text):
    data = image_captcha.generate(text)
    return data

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def lcs_length(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    dp = [[0]*(lb+1) for _ in range(la+1)]
    a = a.lower()
    b = b.lower()
    for i in range(1, la+1):
        for j in range(1, lb+1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] +1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[la][lb]

# ========== 路由 ==========

@app.route('/captcha')
def captcha():
    text = random_captcha_text()
    session['captcha_text'] = text
    img_data = generate_captcha_img(text)
    return send_file(img_data, mimetype='image/png')

@app.route('/')
def index():
    query = request.args.get('q', '').strip()
    users = []
    if query:
        all_users = User.query.all()
        scored = []
        for u in all_users:
            score = lcs_length(query, u.username)
            if score > 0:
                scored.append((score, u))
        scored.sort(key=lambda x: x[0], reverse=True)
        users = [u for score,u in scored[:10]]
    return render_template_string(index_html, users=users, query=query)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').upper()

        if captcha_input != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))

        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))

    return render_template_string(register_html)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '').upper()

        if captcha_input != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
            return redirect(url_for('login'))

    return render_template_string(login_html)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    title = request.form.get('title', '').strip()
    file = request.files.get('file')

    if not title:
        return jsonify({'success': False, 'msg': '请输入视频标题'})
    if not file or file.filename == '':
        return jsonify({'success': False, 'msg': '请选择视频文件'})
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'msg': '只允许上传 mp4, avi, mov, mkv 视频格式'})

    filename = sanitize_filename(file.filename)
    filename = f"{current_user.id}_{random.randint(1000, 9999)}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    video = Video(filename=filename, title=title, owner=current_user)
    db.session.add(video)
    db.session.commit()

    return jsonify({'success': True, 'msg': '上传成功'})

@app.route('/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    video = Video.query.get_or_404(video_id)
    if video.owner != current_user:
        return jsonify({'success': False, 'msg': '没有权限删除该视频'})

    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], video.filename))
    except Exception as e:
        print("删除文件异常:", e)

    db.session.delete(video)
    db.session.commit()
    return jsonify({'success': True, 'msg': '删除成功'})

@app.route('/user/<int:user_id>')
def user_videos(user_id):
    user = User.query.get_or_404(user_id)
    videos = user.videos
    return render_template_string(user_videos_html, user=user, videos=videos)

@app.route('/video/<int:video_id>')
def video_player(video_id):
    video = Video.query.get_or_404(video_id)
    search_query = request.args.get('q', '').strip()

    user_videos_sorted = sorted(video.owner.videos, key=lambda v: v.id)
    current_index = next((i for i,v in enumerate(user_videos_sorted) if v.id == video_id), None)

    next_video_url = None
    if current_index is not None and current_index +1 < len(user_videos_sorted):
        next_vid = user_videos_sorted[current_index+1]
        next_video_url = url_for('video_player', video_id=next_vid.id, q=search_query)

    return render_template_string(video_player_html,
        video=video,
        next_video_url=next_video_url,
        search_query=search_query)

# ---- 视频文件直接静态访问 -- 通过 static/uploads 目录访问

# ========== 模板 ==========

base_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <title>{% block title %}视频网站{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
    <!-- Bootstrap 4 -->
    <link
        href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css"
        rel="stylesheet"
    />
    <style>
        body {
            background: #f8f9fa;
        }
        .navbar-brand {
            font-weight: bold;
            font-size: 1.5rem;
            letter-spacing: 1px;
        }
        .container {
            margin-top: 2rem;
            margin-bottom: 3rem;
        }
        video {
            border-radius: 6px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        .video-item h5 {
            margin-bottom: 0.5rem;
        }
        img.captcha-img {
            cursor: pointer;
            height: 50px;
            margin-top: 5px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        footer {
            margin-top: 4rem;
            padding: 1rem 0;
            text-align: center;
            color: #999;
            font-size: 0.9rem;
            border-top: 1px solid #ddd;
        }
    </style>
    {% block css %}{% endblock %}
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-light bg-white shadow-sm sticky-top">
    <div class="container">
        <a class="navbar-brand" href="{{ url_for('index') }}">视频站</a>
        <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#navMenu" 
            aria-controls="navMenu" aria-expanded="false" aria-label="Toggle navigation">
            <span class="navbar-toggler-icon"></span>
        </button>

        <div class="collapse navbar-collapse" id="navMenu">
            <ul class="navbar-nav mr-auto mt-2 mt-lg-0">
                <li class="nav-item {% if request.endpoint=='index' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('index') }}">首页</a>
                </li>
                {% if current_user.is_authenticated %}
                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for('user_videos', user_id=current_user.id) }}">我的视频</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link text-danger" href="{{ url_for('logout') }}">退出</a>
                </li>
                {% else %}
                <li class="nav-item {% if request.endpoint=='login' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('login') }}">登录</a>
                </li>
                <li class="nav-item {% if request.endpoint=='register' %}active{% endif %}">
                    <a class="nav-link" href="{{ url_for('register') }}">注册</a>
                </li>
                {% endif %}
            </ul>
            <form class="form-inline my-2 my-lg-0" method="get" action="{{ url_for('index') }}">
                <input class="form-control mr-sm-2" type="search" name="q" placeholder="搜索用户名"
                    aria-label="搜索用户名" value="{{ query|default('') }}">
                <button class="btn btn-outline-success my-2 my-sm-0" type="submit">搜索</button>
            </form>
        </div>
    </div>
</nav>

<div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="close" data-dismiss="alert" aria-label="关闭">
                <span aria-hidden="true">&times;</span>
            </button>
        </div>
        {% endfor %}
    {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</div>

<footer>
    &copy; 2024 视频网站 - 仅供测试学习使用
</footer>

<script src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.slim.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/popper.js@1.16.1/dist/umd/popper.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.min.js"></script>
{% block scripts %}{% endblock %}

</body>
</html>
'''

index_html = '''
{% extends base_html %}
{% block title %}首页 - 视频网站{% endblock %}
{% block content %}
<div class="card shadow-sm">
    <div class="card-header bg-white">
        <h4>搜索用户</h4>
    </div>
    <div class="card-body">
        {% if query %}
            {% if users %}
                <ul class="list-group">
                    {% for user in users %}
                    <li class="list-group-item list-group-item-action">
                        <a href="{{ url_for('user_videos', user_id=user.id) }}" class="font-weight-bold">{{ user.username }}</a>
                    </li>
                    {% endfor %}
                </ul>
            {% else %}
                <p class="text-muted">没有找到与 <code>{{ query }}</code> 相关的用户。</p>
            {% endif %}
        {% else %}
            <p class="text-secondary">请输入用户名进行搜索</p>
        {% endif %}
    </div>
</div>
{% endblock %}
'''

register_html = '''
{% extends base_html %}
{% block title %}注册 - 视频网站{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6 col-lg-5">
        <div class="card shadow-sm">
            <div class="card-header bg-white">
                <h4>注册账号</h4>
            </div>
            <div class="card-body">
                <form method="post" novalidate>
                    <div class="form-group">
                        <label for="username">用户名</label>
                        <input type="text" class="form-control" id="username" name="username" maxlength="150" required autofocus>
                    </div>
                    <div class="form-group">
                        <label for="password">密码</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <div class="form-group">
                        <label for="captcha">验证码</label>
                        <div class="d-flex align-items-center">
                            <input type="text" class="form-control mr-3" id="captcha" name="captcha" maxlength="4" required style="width:120px;">
                            <img src="{{ url_for('captcha') }}" title="点击刷新验证码" alt="验证码" class="captcha-img" id="captchaImg"
                                onclick="this.src='{{ url_for('captcha') }}?'+Math.random()">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success btn-block">注册</button>
                </form>
                <small class="form-text text-muted mt-2">
                    已有账号？<a href="{{ url_for('login') }}">马上登录</a>
                </small>
            </div>
        </div>
    </div>
</div>
{% endblock %}
'''

login_html = '''
{% extends base_html %}
{% block title %}登录 - 视频网站{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6 col-lg-5">
        <div class="card shadow-sm">
            <div class="card-header bg-white">
                <h4>用户登录</h4>
            </div>
            <div class="card-body">
                <form method="post" novalidate>
                    <div class="form-group">
                        <label for="username">用户名</label>
                        <input type="text" class="form-control" id="username" name="username" maxlength="150" required autofocus>
                    </div>
                    <div class="form-group">
                        <label for="password">密码</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <div class="form-group">
                        <label for="captcha">验证码</label>
                        <div class="d-flex align-items-center">
                            <input type="text" class="form-control mr-3" id="captcha" name="captcha" maxlength="4" required style="width:120px;">
                            <img src="{{ url_for('captcha') }}" title="点击刷新验证码" alt="验证码" class="captcha-img" id="captchaImg"
                             onclick="this.src='{{ url_for('captcha') }}?'+Math.random()">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary btn-block">登录</button>
                </form>
                <small class="form-text text-muted mt-2">
                    还没有账号？<a href="{{ url_for('register') }}">立即注册</a>
                </small>
            </div>
        </div>
    </div>
</div>
{% endblock %}
'''

user_videos_html = '''
{% extends base_html %}
{% block title %}{{ user.username }}的视频 - 视频网站{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap">
    <h3>{{ user.username }}的视频列表</h3>
    {% if current_user.is_authenticated and current_user.id == user.id %}
    <button class="btn btn-primary mb-2" id="uploadBtn">
        <i class="fas fa-upload"></i> 上传视频
    </button>
    {% endif %}
</div>
{% if current_user.is_authenticated and current_user.id == user.id %}
<div id="uploadArea" class="card p-3 mb-4" style="display:none;">
    <form id="uploadForm" novalidate enctype="multipart/form-data">
        <div class="form-row">
            <div class="form-group col-md-5">
                <label for="title">视频标题</label>
                <input type="text" class="form-control" id="title" name="title" maxlength="200" required>
            </div>
            <div class="form-group col-md-5">
                <label for="file">选择视频文件</label>
                <input type="file" accept="video/*" class="form-control-file" id="file" name="file" required>
            </div>
            <div class="form-group col-md-2 d-flex align-items-end">
                <button type="submit" class="btn btn-success btn-block mr-2">上传</button>
                <button type="button" class="btn btn-outline-secondary btn-block" id="cancelUpload">取消</button>
            </div>
        </div>
    </form>
</div>
{% endif %}

{% if videos %}
<div class="row" id="videosContainer">
    {% for video in videos %}
    <div class="col-md-6 col-sm-12 mb-4 video-item" data-video-id="{{ video.id }}">
        <div class="card h-100 shadow-sm">
            <div class="card-body">
                <h5 class="card-title">{{ video.title }}</h5>
                <video class="w-100 rounded" controls preload="metadata" style="cursor:pointer;"
                    onclick="playVideo({{ video.id }})">
                    <source src="{{ url_for('static', filename='uploads/' + video.filename) }}" type="video/mp4">
                    你的浏览器不支持 video 标签。
                </video>
            </div>
            {% if current_user.is_authenticated and current_user.id == user.id %}
            <div class="card-footer bg-transparent border-top-0 p-3 d-flex justify-content-end">
                <button class="btn btn-danger btn-sm delete-btn" title="删除视频">
                    <i class="fas fa-trash"></i> 删除
                </button>
            </div>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</div>
{% else %}
<p class="text-muted">该用户还没有上传视频。</p>
{% endif %}

{% block scripts %}
{{ super() }}
<script src="https://kit.fontawesome.com/a076d05399.js" crossorigin="anonymous"></script>
<script>
document.addEventListener('DOMContentLoaded', function(){
    {% if current_user.is_authenticated and current_user.id == user.id %}
    const uploadBtn = document.getElementById('uploadBtn');
    const uploadArea = document.getElementById('uploadArea');
    const cancelUpload = document.getElementById('cancelUpload');
    const uploadForm = document.getElementById('uploadForm');
    const videosContainer = document.getElementById('videosContainer');

    uploadBtn.addEventListener('click', () => {
        uploadArea.style.display = 'block';
        uploadBtn.style.display = 'none';
    });
    cancelUpload.addEventListener('click', () => {
        uploadArea.style.display = 'none';
        uploadBtn.style.display = 'inline-block';
        uploadForm.reset();
    });
    uploadForm.addEventListener('submit', function(e){
        e.preventDefault();
        const formData = new FormData(uploadForm);
        fetch("{{ url_for('upload') }}", {
            method: 'POST',
            body: formData,
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(r => r.json()).then(data => {
            if(data.success){
                alert(data.msg);
                location.reload();
            }
            else {
                alert(data.msg);
            }
        }).catch(() => alert('上传失败'));
        return false;
    });
    videosContainer.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', function(){
            if(!confirm('确定删除该视频吗？')) return;
            const videoDiv = this.closest('.video-item');
            const videoId = videoDiv.getAttribute('data-video-id');
            fetch('{{ url_for("delete_video", video_id=0) }}'.replace('0', videoId), {
                method:'POST',
                headers:{'X-Requested-With': 'XMLHttpRequest'}
            }).then(r => r.json()).then(data => {
                if(data.success){
                    alert(data.msg);
                    videoDiv.remove();
                } else {
                    alert(data.msg);
                }
            }).catch(() => alert('删除失败'));
        });
    });
    {% endif %}
});
function playVideo(videoId){
    let searchQuery = new URLSearchParams(window.location.search).get('q') || '';
    let url = "{{ url_for('video_player', video_id=0) }}".replace('0', videoId);
    if(searchQuery){
        url += "?q=" + encodeURIComponent(searchQuery);
    }
    window.location.href = url;
}
</script>
{% endblock %}
'''

video_player_html = '''
{% extends base_html %}
{% block title %}播放：{{ video.title }} - 视频网站{% endblock %}

{% block css %}
<style>
  .video-container {
    max-width: 600px;
    margin: 1rem auto;
    padding: 0 1rem;
  }
  video#player {
    width: 100%;
    max-height: 80vh;
    border-radius: 12px;
    background: #000;
    outline: none;
  }
  .controls {
    margin-top: 1rem;
    display: flex;
    justify-content: space-between;
    max-width: 600px;
    margin-left: auto;
    margin-right: auto;
  }
  .btn-control {
    flex: 1;
    margin: 0 0.3rem;
    font-weight: 600;
  }
  @media (max-width: 576px) {
    .controls {
      flex-direction: column;
      max-width: 100%;
    }
    .btn-control {
      margin: 0.3rem 0;
      width: 100%;
    }
  }
</style>
{% endblock %}

{% block content %}
<div class="video-container">
  <video id="player" controls autoplay playsinline>
    <source src="{{ url_for('static', filename='uploads/' + video.filename) }}" type="video/mp4" />
    你的浏览器不支持 video 标签。
  </video>
  <div class="controls">
    <button class="btn btn-outline-secondary btn-control" onclick="goBack()">
      <i class="fas fa-arrow-left"></i> 返回搜索结果
    </button>
    {% if next_video_url %}
    <button class="btn btn-primary btn-control" onclick="goNext()">
      <i class="fas fa-step-forward"></i> 下一个视频
    </button>
    {% else %}
    <button class="btn btn-primary btn-control" disabled>
      没有下一个视频了
    </button>
    {% endif %}
  </div>
</div>
{% endblock %}

{% block scripts %}
{{ super() }}
<script src="https://kit.fontawesome.com/a076d05399.js" crossorigin="anonymous"></script>
<script>
function goBack() {
    if (document.referrer && document.referrer.includes(window.location.host)) {
      window.history.back();
    } else {
      let q="{{ search_query }}";
      if(q){
        window.location.href = "{{ url_for('index') }}" + "?q=" + encodeURIComponent(q);
      } else {
        window.location.href = "{{ url_for('index') }}";
      }
    }
}
function goNext() {
    {% if next_video_url %}
    window.location.href = "{{ next_video_url }}";
    {% endif %}
}
</script>
{% endblock %}
'''

@app.context_processor
def inject_base_html():
    return dict(base_html=base_html)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
