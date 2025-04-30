# 导入Flask-WTF表单基类和WTForms字段类
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo
from flask_wtf.file import FileField, FileRequired, FileAllowed
# 定义用户注册用的表单
class RegisterForm(FlaskForm):
    # 用户名字段，要求必填，且长度在3到20字符之间
    username = StringField('用户名', validators=[DataRequired(), Length(3, 20)])
    # 密码字段，要求必填，且长度在6到20字符之间
    password = PasswordField('密码', validators=[DataRequired(), Length(6, 20)])
    # 确认密码字段，要求必填，且必须与密码字段相同
    password2 = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    # 验证码字段，要求必填，且长度固定为5字符
    captcha = StringField('验证码', validators=[DataRequired(), Length(5, 5)])
    # 提交按钮
    submit = SubmitField('注册')
# ----------------------------------------------------------------------------
# 定义用户登录用的表单
class LoginForm(FlaskForm):
    # 用户名字段，要求必填
    username = StringField('用户名', validators=[DataRequired()])
    # 密码字段，要求必填
    password = PasswordField('密码', validators=[DataRequired()])
    # 验证码字段，要求必填，且长度为5字符
    captcha = StringField('验证码', validators=[DataRequired(), Length(5, 5)])
    # 提交按钮
    submit = SubmitField('登录')
# ----------------------------------------------------------------------------
# 定义视频上传用的表单
class UploadForm(FlaskForm):
    # 视频文件字段，要求必选文件，且只允许特定视频格式
    video = FileField('选择视频', validators=[
        FileRequired(),  # 必须选择文件
        FileAllowed(['mp4', 'avi', 'mov', 'mkv'], '只允许上传视频文件！')  # 仅允许上传特定格式
    ])
    # 提交按钮
    submit = SubmitField('上传')
# ----------------------------------------------------------------------------
# 定义用户名搜索用的表单
class SearchForm(FlaskForm):
    # 搜索关键字字段，要求必填
    keyword = StringField('搜索用户名', validators=[DataRequired()])
    # 提交按钮
    submit = SubmitField('搜索')
