from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo
from flask_wtf.file import FileField, FileRequired, FileAllowed

class RegisterForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(3, 20)])
    password = PasswordField('密码', validators=[DataRequired(), Length(6, 20)])
    password2 = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    captcha = StringField('验证码', validators=[DataRequired(), Length(5, 5)])
    submit = SubmitField('注册')

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    captcha = StringField('验证码', validators=[DataRequired(), Length(5, 5)])
    submit = SubmitField('登录')

class UploadForm(FlaskForm):
    video = FileField('选择视频', validators=[
        FileRequired(),
        FileAllowed(['mp4', 'avi', 'mov', 'mkv'], '只允许上传视频文件！')
    ])
    submit = SubmitField('上传')

class SearchForm(FlaskForm):
    keyword = StringField('搜索用户名', validators=[DataRequired()])
    submit = SubmitField('搜索')
