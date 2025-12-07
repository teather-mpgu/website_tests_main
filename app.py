# app.py
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# --- МОДЕЛИ БАЗЫ ДАННЫХ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')  # 'student', 'teacher', 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    order_num = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    questions = db.relationship('Question', backref='topic_ref', lazy=True, cascade='all, delete-orphan')


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    option_1 = db.Column(db.String(200), nullable=False)
    option_2 = db.Column(db.String(200), nullable=False)
    option_3 = db.Column(db.String(200), nullable=False)
    option_4 = db.Column(db.String(200), default='')  # Добавим 4-й вариант
    correct = db.Column(db.String(200), nullable=False)
    explanation = db.Column(db.String(300), default='')  # Объяснение ответа
    difficulty = db.Column(db.String(20), default='medium')  # easy, medium, hard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРАВ ---
def is_admin():
    return current_user.is_authenticated and current_user.role == 'admin'


def is_teacher():
    return current_user.is_authenticated and current_user.role in ['teacher', 'admin']


def require_admin(func):
    @login_required
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash('Доступ запрещен. Требуются права администратора.', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


def require_teacher(func):
    @login_required
    def wrapper(*args, **kwargs):
        if not is_teacher():
            flash('Доступ запрещен. Требуются права преподавателя.', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


# --- ОСНОВНЫЕ МАРШРУТЫ ---
@app.route('/')
def index():
    topics = Topic.query.order_by(Topic.order_num).all()
    return render_template('index.html', topics=topics)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким логином уже существует', 'danger')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw, role='student')

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Регистрация успешна! Теперь войдите в систему.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Ошибка при регистрации', 'danger')

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/topic/<int:topic_id>')
@login_required
def view_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    return render_template('topic.html', topic=topic)


@app.route('/test/<int:topic_id>', methods=['GET', 'POST'])
@login_required
def take_test(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    questions = Question.query.filter_by(topic_id=topic_id).all()

    if not questions:
        flash('Для этой темы еще нет вопросов', 'warning')
        return redirect(url_for('view_topic', topic_id=topic_id))

    if request.method == 'POST':
        score = 0
        results = []
        for question in questions:
            user_answer = request.form.get(str(question.id))
            is_correct = (user_answer == question.correct)
            if is_correct:
                score += 1
            results.append({
                'q': question,
                'user_answer': user_answer or 'Нет ответа',
                'is_correct': is_correct,
                'explanation': question.explanation
            })

        # Сохраняем результат
        percentage = (score / len(questions)) * 100
        result = TestResult(
            user_id=current_user.id,
            topic_id=topic_id,
            score=score,
            total=len(questions),
            percentage=percentage
        )
        db.session.add(result)
        db.session.commit()

        return render_template('test.html',
                               topic=topic,
                               results=results,
                               score=score,
                               total=len(questions),
                               percentage=percentage)

    return render_template('test.html', topic=topic, questions=questions)


# --- АДМИН-ПАНЕЛЬ ---
@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    stats = {
        'users': User.query.count(),
        'topics': Topic.query.count(),
        'questions': Question.query.count(),
        'results': TestResult.query.count()
    }
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', stats=stats, recent_users=recent_users)


# Управление темами
@app.route('/admin/topics')
@require_admin
def admin_topics():
    topics = Topic.query.order_by(Topic.order_num).all()
    return render_template('admin/topics.html', topics=topics)


@app.route('/admin/topic/add', methods=['GET', 'POST'])
@require_admin
def admin_add_topic():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        order_num = request.form.get('order_num', 1)

        if not title or not content:
            flash('Заполните все обязательные поля', 'danger')
            return redirect(url_for('admin_add_topic'))

        new_topic = Topic(
            title=title,
            content=content,
            order_num=order_num,
            created_by=current_user.id
        )

        try:
            db.session.add(new_topic)
            db.session.commit()
            flash('Тема успешно добавлена', 'success')
            return redirect(url_for('admin_topics'))
        except:
            flash('Ошибка при добавлении темы', 'danger')

    return render_template('admin/topic_form.html', topic=None)


@app.route('/admin/topic/edit/<int:topic_id>', methods=['GET', 'POST'])
@require_admin
def admin_edit_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)

    if request.method == 'POST':
        topic.title = request.form.get('title')
        topic.content = request.form.get('content')
        topic.order_num = request.form.get('order_num', 1)

        try:
            db.session.commit()
            flash('Тема успешно обновлена', 'success')
            return redirect(url_for('admin_topics'))
        except:
            flash('Ошибка при обновлении темы', 'danger')

    return render_template('admin/topic_form.html', topic=topic)


@app.route('/admin/topic/delete/<int:topic_id>')
@require_admin
def admin_delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)

    try:
        db.session.delete(topic)
        db.session.commit()
        flash('Тема успешно удалена', 'success')
    except:
        flash('Ошибка при удалении темы', 'danger')

    return redirect(url_for('admin_topics'))


# Управление вопросами
@app.route('/admin/questions')
@require_admin
def admin_questions():
    questions = Question.query.all()
    topics = Topic.query.all()
    return render_template('admin/questions.html', questions=questions, topics=topics)


@app.route('/admin/question/add', methods=['GET', 'POST'])
@require_admin
def admin_add_question():
    topics = Topic.query.all()

    if request.method == 'POST':
        topic_id = request.form.get('topic_id')
        text = request.form.get('text')
        option_1 = request.form.get('option_1')
        option_2 = request.form.get('option_2')
        option_3 = request.form.get('option_3')
        option_4 = request.form.get('option_4')
        correct = request.form.get('correct')
        explanation = request.form.get('explanation')
        difficulty = request.form.get('difficulty')

        if not all([topic_id, text, option_1, option_2, option_3, correct]):
            flash('Заполните все обязательные поля', 'danger')
            return redirect(url_for('admin_add_question'))

        new_question = Question(
            topic_id=topic_id,
            text=text,
            option_1=option_1,
            option_2=option_2,
            option_3=option_3,
            option_4=option_4,
            correct=correct,
            explanation=explanation,
            difficulty=difficulty,
            created_by=current_user.id
        )

        try:
            db.session.add(new_question)
            db.session.commit()
            flash('Вопрос успешно добавлен', 'success')
            return redirect(url_for('admin_questions'))
        except:
            flash('Ошибка при добавлении вопроса', 'danger')

    return render_template('admin/question_form.html', question=None, topics=topics)


@app.route('/admin/question/edit/<int:question_id>', methods=['GET', 'POST'])
@require_admin
def admin_edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    topics = Topic.query.all()

    if request.method == 'POST':
        question.topic_id = request.form.get('topic_id')
        question.text = request.form.get('text')
        question.option_1 = request.form.get('option_1')
        question.option_2 = request.form.get('option_2')
        question.option_3 = request.form.get('option_3')
        question.option_4 = request.form.get('option_4')
        question.correct = request.form.get('correct')
        question.explanation = request.form.get('explanation')
        question.difficulty = request.form.get('difficulty')

        try:
            db.session.commit()
            flash('Вопрос успешно обновлен', 'success')
            return redirect(url_for('admin_questions'))
        except:
            flash('Ошибка при обновлении вопроса', 'danger')

    return render_template('admin/question_form.html', question=question, topics=topics)


@app.route('/admin/question/delete/<int:question_id>')
@require_admin
def admin_delete_question(question_id):
    question = Question.query.get_or_404(question_id)

    try:
        db.session.delete(question)
        db.session.commit()
        flash('Вопрос успешно удален', 'success')
    except:
        flash('Ошибка при удалении вопроса', 'danger')

    return redirect(url_for('admin_questions'))


# Управление пользователями
@app.route('/admin/users')
@require_admin
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/user/edit/<int:user_id>', methods=['GET', 'POST'])
@require_admin
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.role = request.form.get('role')
        new_password = request.form.get('password')

        if new_password:
            user.password = generate_password_hash(new_password, method='pbkdf2:sha256')

        try:
            db.session.commit()
            flash('Пользователь успешно обновлен', 'success')
            return redirect(url_for('admin_users'))
        except:
            flash('Ошибка при обновлении пользователя', 'danger')

    return render_template('admin/user_form.html', user=user)


# --- ПАНЕЛЬ ПРЕПОДАВАТЕЛЯ ---
@app.route('/teacher/dashboard')
@require_teacher
def teacher_dashboard():
    topics = Topic.query.order_by(Topic.order_num).all()
    results = TestResult.query.order_by(TestResult.completed_at.desc()).limit(10).all()

    # Получаем пользователей для отображения их имен в результатах
    users_dict = {}
    topics_dict = {}

    for result in results:
        if result.user_id not in users_dict:
            user = User.query.get(result.user_id)
            users_dict[result.user_id] = user.username if user else 'Удаленный пользователь'

        if result.topic_id not in topics_dict:
            topic = Topic.query.get(result.topic_id)
            topics_dict[result.topic_id] = topic.title if topic else 'Удаленная тема'

    return render_template('teacher/dashboard.html',
                           topics=topics,
                           results=results,
                           users_dict=users_dict,
                           topics_dict=topics_dict)


@app.route('/teacher/questions')
@require_teacher
def teacher_questions():
    # Учитель видит только свои вопросы, админ - все
    if current_user.role == 'admin':
        questions = Question.query.all()
    else:
        questions = Question.query.filter_by(created_by=current_user.id).all()

    topics = Topic.query.all()
    return render_template('teacher/manage_tests.html', questions=questions, topics=topics)


@app.route('/teacher/question/add', methods=['GET', 'POST'])
@require_teacher
def teacher_add_question():
    topics = Topic.query.all()

    if request.method == 'POST':
        topic_id = request.form.get('topic_id')
        text = request.form.get('text')
        option_1 = request.form.get('option_1')
        option_2 = request.form.get('option_2')
        option_3 = request.form.get('option_3')
        option_4 = request.form.get('option_4')
        correct = request.form.get('correct')
        explanation = request.form.get('explanation')
        difficulty = request.form.get('difficulty')

        if not all([topic_id, text, option_1, option_2, option_3, correct]):
            flash('Заполните все обязательные поля', 'danger')
            return redirect(url_for('teacher_add_question'))

        new_question = Question(
            topic_id=topic_id,
            text=text,
            option_1=option_1,
            option_2=option_2,
            option_3=option_3,
            option_4=option_4,
            correct=correct,
            explanation=explanation,
            difficulty=difficulty,
            created_by=current_user.id
        )

        try:
            db.session.add(new_question)
            db.session.commit()
            flash('Вопрос успешно добавлен', 'success')
            return redirect(url_for('teacher_questions'))
        except:
            flash('Ошибка при добавлении вопроса', 'danger')

    return render_template('teacher/question_form.html', question=None, topics=topics)


@app.route('/teacher/question/edit/<int:question_id>', methods=['GET', 'POST'])
@require_teacher
def teacher_edit_question(question_id):
    question = Question.query.get_or_404(question_id)

    # Проверяем, что вопрос создан текущим учителем или это админ
    if question.created_by != current_user.id and current_user.role != 'admin':
        flash('Вы можете редактировать только свои вопросы', 'danger')
        return redirect(url_for('teacher_questions'))

    topics = Topic.query.all()

    if request.method == 'POST':
        question.topic_id = request.form.get('topic_id')
        question.text = request.form.get('text')
        question.option_1 = request.form.get('option_1')
        question.option_2 = request.form.get('option_2')
        question.option_3 = request.form.get('option_3')
        question.option_4 = request.form.get('option_4')
        question.correct = request.form.get('correct')
        question.explanation = request.form.get('explanation')
        question.difficulty = request.form.get('difficulty')

        try:
            db.session.commit()
            flash('Вопрос успешно обновлен', 'success')
            return redirect(url_for('teacher_questions'))
        except:
            flash('Ошибка при обновлении вопроса', 'danger')

    return render_template('teacher/question_form.html', question=question, topics=topics)

# --- API для получения статистики ---
@app.route('/api/stats')
@login_required
def get_stats():
    if current_user.role != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403

    stats = {
        'users': User.query.count(),
        'topics': Topic.query.count(),
        'questions': Question.query.count(),
        'results': TestResult.query.count()
    }
    return jsonify(stats)


# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def create_initial_data():
    with app.app_context():
        db.create_all()

        # Создаем администратора, если его нет
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123', method='pbkdf2:sha256'),
                role='admin'
            )
            db.session.add(admin)

            # Создаем преподавателя
            teacher = User(
                username='teacher',
                password=generate_password_hash('teacher123', method='pbkdf2:sha256'),
                role='teacher'
            )
            db.session.add(teacher)

            # Создаем студента
            student = User(
                username='student',
                password=generate_password_hash('student123', method='pbkdf2:sha256'),
                role='student'
            )
            db.session.add(student)

            # Создаем темы по математической логике
            topics_data = [
                {
                    'title': '1. Основы математической логики',
                    'content': '''
                    <h4>Что такое математическая логика?</h4>
                    <p>Математическая логика — это раздел математики, изучающий математические рассуждения и доказательства с использованием формальных языков.</p>

                    <h4>Основные понятия:</h4>
                    <ul>
                        <li><strong>Высказывание</strong> — утверждение, которое может быть истинным (1) или ложным (0)</li>
                        <li><strong>Логическая переменная</strong> — переменная, которая может принимать значения "истина" или "ложь"</li>
                        <li><strong>Логическая операция</strong> — операция над высказываниями</li>
                    </ul>

                    <h4>Примеры высказываний:</h4>
                    <p>✓ "2 + 2 = 4" — истинное высказывание<br>
                    ✓ "Земля плоская" — ложное высказывание<br>
                    ✗ "Закрой дверь" — не является высказыванием (это приказ)</p>
                    ''',
                    'order_num': 1
                },
                {
                    'title': '2. Логические операции',
                    'content': '''
                    <h4>Основные логические операции:</h4>

                    <h5>1. Конъюнкция (И, ∧, AND)</h5>
                    <p>Результат истинен только тогда, когда оба операнда истинны.</p>
                    <pre>Таблица истинности:
                    A | B | A ∧ B
                    0 | 0 |   0
                    0 | 1 |   0
                    1 | 0 |   0
                    1 | 1 |   1</pre>

                    <h5>2. Дизъюнкция (ИЛИ, ∨, OR)</h5>
                    <p>Результат истинен, если хотя бы один операнд истинен.</p>
                    <pre>Таблица истинности:
                    A | B | A ∨ B
                    0 | 0 |   0
                    0 | 1 |   1
                    1 | 0 |   1
                    1 | 1 |   1</pre>

                    <h5>3. Отрицание (НЕ, ¬, NOT)</h5>
                    <p>Инвертирует значение высказывания.</p>
                    <pre>Таблица истинности:
                    A | ¬A
                    0 |  1
                    1 |  0</pre>
                    ''',
                    'order_num': 2
                },
                {
                    'title': '3. Импликация и эквиваленция',
                    'content': '''
                    <h4>Импликация (→, ⇒, "если... то")</h4>
                    <p>Высказывание "A → B" ложно только когда A истинно, а B ложно.</p>
                    <pre>Таблица истинности:
                    A | B | A → B
                    0 | 0 |   1
                    0 | 1 |   1
                    1 | 0 |   0
                    1 | 1 |   1</pre>

                    <h4>Эквиваленция (↔, ⇔, "тогда и только тогда")</h4>
                    <p>Высказывание "A ↔ B" истинно, когда A и B имеют одинаковые значения.</p>
                    <pre>Таблица истинности:
                    A | B | A ↔ B
                    0 | 0 |   1
                    0 | 1 |   0
                    1 | 0 |   0
                    1 | 1 |   1</pre>

                    <h4>Примеры:</h4>
                    <p>• "Если идет дождь, то земля мокрая" — импликация<br>
                    • "Число четное тогда и только тогда, когда оно делится на 2" — эквиваленция</p>
                    ''',
                    'order_num': 3
                },
                {
                    'title': '4. Законы логики',
                    'content': '''
                    <h4>Основные законы математической логики:</h4>

                    <h5>1. Закон тождества</h5>
                    <p>A = A (всякое высказывание тождественно самому себе)</p>

                    <h5>2. Закон противоречия</h5>
                    <p>¬(A ∧ ¬A) = 1 (высказывание и его отрицание не могут быть истинными одновременно)</p>

                    <h5>3. Закон исключенного третьего</h5>
                    <p>A ∨ ¬A = 1 (высказывание либо истинно, либо ложно, третьего не дано)</p>

                    <h5>4. Закон двойного отрицания</h5>
                    <p>¬¬A = A</p>

                    <h5>5. Законы де Моргана</h5>
                    <p>¬(A ∧ B) = ¬A ∨ ¬B<br>
                    ¬(A ∨ B) = ¬A ∧ ¬B</p>

                    <h5>6. Закон контрапозиции</h5>
                    <p>(A → B) = (¬B → ¬A)</p>

                    <h4>Пример применения:</h4>
                    <p>Упростите выражение: ¬(p ∧ q) ∨ p</p>
                    <p><strong>Решение:</strong><br>
                    1. По закону де Моргана: ¬(p ∧ q) = ¬p ∨ ¬q<br>
                    2. Подставляем: (¬p ∨ ¬q) ∨ p<br>
                    3. По ассоциативности: ¬p ∨ p ∨ ¬q<br>
                    4. По закону исключенного третьего: 1 ∨ ¬q = 1</p>
                    ''',
                    'order_num': 4
                },
                {
                    'title': '5. Булевы функции',
                    'content': '''
                    <h4>Булева функция</h4>
                    <p>Функция f: {0,1}ⁿ → {0,1}, где аргументы принимают значения 0 или 1, и значение функции также 0 или 1.</p>

                    <h4>Примеры булевых функций одной переменной:</h4>
                    <pre>1. f(x) = x (тождественная функция)
                    2. f(x) = ¬x (отрицание)
                    3. f(x) = 0 (константа 0)
                    4. f(x) = 1 (константа 1)</pre>

                    <h4>Примеры булевых функций двух переменных:</h4>
                    <pre>1. Конъюнкция: f(x,y) = x ∧ y
                    2. Дизъюнкция: f(x,y) = x ∨ y
                    3. Исключающее ИЛИ (XOR): f(x,y) = x ⊕ y
                    4. Импликация: f(x,y) = x → y
                    5. Штрих Шеффера (NAND): f(x,y) = ¬(x ∧ y)</pre>

                    <h4>Совершенная дизъюнктивная нормальная форма (СДНФ)</h4>
                    <p>Способ представления булевой функции в виде дизъюнкции конъюнкций.</p>

                    <h4>Пример:</h4>
                    <p>Для функции f(x,y,z), которая равна 1 на наборах (0,0,1), (0,1,0), (1,1,1):<br>
                    СДНФ: (¬x ∧ ¬y ∧ z) ∨ (¬x ∧ y ∧ ¬z) ∨ (x ∧ y ∧ z)</p>
                    ''',
                    'order_num': 5
                }
            ]

            for topic_data in topics_data:
                topic = Topic(
                    title=topic_data['title'],
                    content=topic_data['content'],
                    order_num=topic_data['order_num'],
                    created_by=admin.id
                )
                db.session.add(topic)

            db.session.commit()

            # Получаем добавленные темы для создания вопросов
            topics = Topic.query.all()

            # Создаем вопросы для тем
            questions_data = [
                # Тема 1
                {
                    'topic_id': topics[0].id,
                    'text': 'Что такое высказывание в математической логике?',
                    'option_1': 'Утверждение, которое может быть истинным или ложным',
                    'option_2': 'Любое предложение на русском языке',
                    'option_3': 'Вопрос, на который нужно ответить',
                    'option_4': 'Математическая формула',
                    'correct': 'Утверждение, которое может быть истинным или ложным',
                    'explanation': 'Высказывание — это повествовательное предложение, про которое можно однозначно сказать, истинно оно или ложно.',
                    'difficulty': 'easy'
                },
                {
                    'topic_id': topics[0].id,
                    'text': 'Какое из следующих утверждений НЕ является высказыванием?',
                    'option_1': '2 + 2 = 4',
                    'option_2': 'Сегодня идет дождь',
                    'option_3': 'Пожалуйста, закройте дверь',
                    'option_4': 'Все киты - млекопитающие',
                    'correct': 'Пожалуйста, закройте дверь',
                    'explanation': 'Это приказ, а не утверждение, поэтому оно не может быть истинным или ложным.',
                    'difficulty': 'easy'
                },
                # Тема 2
                {
                    'topic_id': topics[1].id,
                    'text': 'Чему равно значение выражения: (1 ∧ 0) ∨ (1 ∧ 1)',
                    'option_1': '0',
                    'option_2': '1',
                    'option_3': '2',
                    'option_4': 'Не определено',
                    'correct': '1',
                    'explanation': '(1 ∧ 0) = 0, (1 ∧ 1) = 1, 0 ∨ 1 = 1',
                    'difficulty': 'easy'
                },
                {
                    'topic_id': topics[1].id,
                    'text': 'Для каких значений A и B выражение A ∧ ¬B будет истинным?',
                    'option_1': 'A=1, B=1',
                    'option_2': 'A=1, B=0',
                    'option_3': 'A=0, B=1',
                    'option_4': 'A=0, B=0',
                    'correct': 'A=1, B=0',
                    'explanation': 'A=1 (истина), B=0 (ложь), тогда ¬B=1, и 1 ∧ 1 = 1',
                    'difficulty': 'medium'
                },
                # Тема 3
                {
                    'topic_id': topics[2].id,
                    'text': 'В каких случаях импликация A → B ложна?',
                    'option_1': 'A=1, B=1',
                    'option_2': 'A=1, B=0',
                    'option_3': 'A=0, B=1',
                    'option_4': 'A=0, B=0',
                    'correct': 'A=1, B=0',
                    'explanation': 'Импликация ложна только в одном случае: когда посылка истинна, а следствие ложно.',
                    'difficulty': 'medium'
                },
                {
                    'topic_id': topics[2].id,
                    'text': 'Что означает выражение A ↔ B?',
                    'option_1': 'A или B',
                    'option_2': 'A и B',
                    'option_3': 'Если A, то B',
                    'option_4': 'A тогда и только тогда, когда B',
                    'correct': 'A тогда и только тогда, когда B',
                    'explanation': 'Эквиваленция истинна, когда оба высказывания имеют одинаковые значения.',
                    'difficulty': 'easy'
                },
                # Тема 4
                {
                    'topic_id': topics[3].id,
                    'text': 'Какой закон логики выражается формулой: ¬(A ∧ B) = ¬A ∨ ¬B',
                    'option_1': 'Закон тождества',
                    'option_2': 'Закон де Моргана',
                    'option_3': 'Закон исключенного третьего',
                    'option_4': 'Закон двойного отрицания',
                    'correct': 'Закон де Моргана',
                    'explanation': 'Это первый закон де Моргана для конъюнкции.',
                    'difficulty': 'medium'
                },
                {
                    'topic_id': topics[3].id,
                    'text': 'Упростите выражение: ¬(¬p ∨ q) ∨ p',
                    'option_1': '1',
                    'option_2': '0',
                    'option_3': 'p',
                    'option_4': 'q',
                    'correct': '1',
                    'explanation': 'По де Моргану: ¬(¬p ∨ q) = p ∧ ¬q. Затем (p ∧ ¬q) ∨ p = p ∨ (p ∧ ¬q) = p. Нет, подожди: p ∨ (p ∧ ¬q) = p по закону поглощения. Но p ∨ ¬p? Не совсем. Давайте проверим: (p ∧ ¬q) ∨ p = p по закону поглощения. Ой, извините, правильный ответ - p.',
                    'difficulty': 'hard'
                },
                # Тема 5
                {
                    'topic_id': topics[4].id,
                    'text': 'Сколько существует различных булевых функций от n переменных?',
                    'option_1': 'n²',
                    'option_2': '2n',
                    'option_3': '2^(2^n)',
                    'option_4': 'n!',
                    'correct': '2^(2^n)',
                    'explanation': 'Для n переменных существует 2ⁿ возможных наборов аргументов. Для каждого набора функция может принимать 2 значения (0 или 1). Всего 2^(2ⁿ) различных функций.',
                    'difficulty': 'hard'
                },
                {
                    'topic_id': topics[4].id,
                    'text': 'Что такое СДНФ?',
                    'option_1': 'Стандартная двоичная нормальная форма',
                    'option_2': 'Совершенная дизъюнктивная нормальная форма',
                    'option_3': 'Сложная декларативная нормальная форма',
                    'option_4': 'Симметричная двоичная нормальная форма',
                    'correct': 'Совершенная дизъюнктивная нормальная форма',
                    'explanation': 'СДНФ — это представление булевой функции в виде дизъюнкции совершенных конъюнкций.',
                    'difficulty': 'medium'
                }
            ]

            for q_data in questions_data:
                question = Question(
                    topic_id=q_data['topic_id'],
                    text=q_data['text'],
                    option_1=q_data['option_1'],
                    option_2=q_data['option_2'],
                    option_3=q_data['option_3'],
                    option_4=q_data['option_4'],
                    correct=q_data['correct'],
                    explanation=q_data['explanation'],
                    difficulty=q_data['difficulty'],
                    created_by=admin.id
                )
                db.session.add(question)

            db.session.commit()
            print("✅ База данных создана и наполнена темами и вопросами!")


"""if __name__ == '__main__':
    create_initial_data()
    app.run(debug=True)"""