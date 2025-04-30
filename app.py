import os
import random
import string
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from forms import RegisterForm, LoginForm, UploadForm, SearchForm
from captcha.image import ImageCaptcha

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # 请改成你自己的secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_share.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'avi', 'mov', 'mkv'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    videos = db.relationship('Video', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 视频模型
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def random_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/captcha')
def get_captcha():
    text = random_captcha_text()
    session['captcha_text'] = text
    image = ImageCaptcha(width=160, height=60)
    data = image.generate(text)
    return send_file(data, mimetype='image/png')

# 计算最长公共子序列长度的函数
def lcs_length(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m):
        for j in range(n):
            if s1[i].lower() == s2[j].lower():
                dp[i+1][j+1] = dp[i][j] + 1
            else:
                dp[i+1][j+1] = max(dp[i][j+1], dp[i+1][j])
    return dp[m][n]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.captcha.data.upper() != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=form.username.data).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))

        new_user = User(username=form.username.data)
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.captcha.data.upper() != session.get('captcha_text', ''):
            flash('验证码错误', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        file = form.video.data
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 确保目录存在
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            # 保存时加用户名防止重复
            save_filename = f"{current_user.username}_{filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], save_filename)
            file.save(save_path)
            video = Video(filename=save_path, owner=current_user)
            db.session.add(video)
            db.session.commit()
            flash('视频上传成功！', 'success')
            return redirect(url_for('user_profile', username=current_user.username))
        else:
            flash('不支持的视频格式', 'danger')
    return render_template('upload.html', form=form)

@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    videos = user.videos
    return render_template('user.html', user=user, videos=videos)

@app.route('/video/<int:video_id>')
def play_video(video_id):
    video = Video.query.get_or_404(video_id)
    return render_template('play_video.html', video=video)

@app.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    users = []
    if form.validate_on_submit():
        keyword = form.keyword.data.strip()
        all_users = User.query.all()
        scored_users = []
        for user in all_users:
            score = lcs_length(keyword, user.username)
            if score > 0:
                scored_users.append((score, user))
        scored_users.sort(key=lambda x: x[0], reverse=True)
        users = [u[1] for u in scored_users[:20]]
    return render_template('search.html', form=form, users=users)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    db.create_all()
    app.run(debug=True)
