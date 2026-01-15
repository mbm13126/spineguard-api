"""
SpineGuard API — Standalone, production-ready версия
SQLite БД только здесь. Всё остальное через HTTP.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
CORS(app)  # Разрешаем запросы из Mini App
app.config['JSON_AS_ASCII'] = False

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    token_balance = Column(Float, default=0.0)
    streak = Column(Integer, default=0)
    last_exercise_date = Column(DateTime, nullable=True)
    exercises_completed = Column(Integer, default=0)
    psychological_profile = relationship("PsychologicalProfile", back_populates="user", uselist=False)
    
    # ПОЛЯ ДЛЯ ДЕРЕВА И ЕЖЕДНЕВНОГО STREAK
    current_streak = Column(Integer, default=0)
    last_checkin_date = Column(DateTime, nullable=True)
    trees_planted = Column(Integer, default=0)

class PsychologicalProfile(Base):
    __tablename__ = 'psychological_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    stress_factors = Column(JSON, default=dict)
    emotional_patterns = Column(JSON, default=dict)
    last_updated = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="psychological_profile")

engine = create_engine('sqlite:///spineguard.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Упражнения
try:
    with open('exercises.json', 'r', encoding='utf-8') as f:
        EXERCISES = json.load(f)
except FileNotFoundError:
    EXERCISES = []
    print("⚠️ exercises.json не найден — упражнения пустые")

# ФУНКЦИЯ ОБНОВЛЕНИЯ STREAK ДЛЯ ДЕРЕВА
def update_streak(session, user):
    today = datetime.utcnow().date()
    last = user.last_checkin_date.date() if user.last_checkin_date else None
    
    if last == today:
        return user.current_streak  # Уже чек-ин сегодня
    
    if last == today - timedelta(days=1):
        user.current_streak += 1
    else:
        user.current_streak = 1  # Новый старт
    
    user.last_checkin_date = datetime.utcnow()
    
    if user.current_streak % 30 == 0 and user.current_streak > 0:
        user.trees_planted += 1
        print(f"🌳 Дерево посажено для {user.telegram_id}! Всего: {user.trees_planted}")
    
    session.commit()
    return user.current_streak

# ==================== ENDPOINTS ====================

@app.route('/api/sync-user', methods=['POST'])
def sync_user():
    """Бот вызывает при /start — создаёт/обновляет пользователя"""
    data = request.json
    telegram_id = data.get('telegram_id')
    username = data.get('username')
    if not telegram_id:
        return jsonify({'error': 'telegram_id required'}), 400
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        profile = PsychologicalProfile(user=user)
        session.add(user)
        session.add(profile)
    else:
        user.username = username or user.username
    session.commit()
    session.close()
    return jsonify({'success': True})

@app.route('/api/update-psych-map', methods=['POST'])
def update_psych_map():
    data = request.json
    telegram_id = data['telegram_id']
    new_map = data['psych_map']
   
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user and user.psychological_profile:
        user.psychological_profile.psych_map = new_map
        session.commit()
    session.close()
    return jsonify({'success': True})

@app.route('/api/add-tokens', methods=['POST'])
def add_tokens():
    """Для онбординга и других начислений из бота"""
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount', 0)
    reason = data.get('reason', '')
    if not telegram_id or amount <= 0:
        return jsonify({'error': 'invalid data'}), 400
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        session.close()
        return jsonify({'error': 'user not found'}), 404
    user.token_balance += amount
    session.commit()
    session.close()
    return jsonify({'success': True, 'new_balance': int(user.token_balance), 'added': amount, 'reason': reason})

@app.route('/api/user/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        # Дефолты для нового пользователя
        default = {
            'success': True,
            'user': {
                'name': 'Пользователь',
                'tokens': 0,
                'status': 'Отлично',
                'streak': 0,
                'level': 1,
                'exercises_completed': 0,
                'current_streak': 0,
                'trees_planted': 0
            },
            'psych_map': {'stress_factors': {}, 'emotions': {}, 'updated_at': None},
            'reward_progress': 0
        }
        session.close()
        return jsonify(default)
    profile = user.psychological_profile or {}
    level = (int(user.token_balance) // 100) + 1
    data = {
        'success': True,
        'user': {
            'name': user.username or 'Пользователь',
            'tokens': int(user.token_balance),
            'status': 'Отлично',
            'streak': user.streak or 0,
            'level': level,
            'exercises_completed': user.exercises_completed or 0,
            'current_streak': user.current_streak or 0,
            'trees_planted': user.trees_planted or 0
        },
        'psych_map': {
            'stress_factors': profile.stress_factors or {},
            'emotions': profile.emotional_patterns or {},
            'updated_at': profile.last_updated.isoformat() if profile.last_updated else None
        },
        'reward_progress': (user.streak or 0) % 7
    }
    session.close()
    return jsonify(data)

@app.route('/api/exercises', methods=['GET'])
def get_exercises():
    return jsonify({'success': True, 'exercises': EXERCISES})

@app.route('/api/exercise/complete', methods=['POST'])
def complete_exercise():
    data = request.json
    telegram_id = data.get('telegram_id')
    if not telegram_id:
        return jsonify({'error': 'telegram_id required'}), 400
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        session.close()
        return jsonify({'error': 'user not found'}), 404
    tokens_earned = 20
    user.token_balance += tokens_earned
    user.exercises_completed += 1
    today = datetime.utcnow().date()
    if user.last_exercise_date:
        last = user.last_exercise_date.date()
        if last == today:
            pass
        elif last == today - timedelta(days=1):
            user.streak += 1
        else:
            user.streak = 1
    else:
        user.streak = 1
    user.last_exercise_date = datetime.utcnow()
    session.commit()
    session.close()
    return jsonify({
        'success': True,
        'tokens_earned': tokens_earned,
        'total_tokens': int(user.token_balance),
        'streak': user.streak,
        'message': 'Упражнение засчитано!'
    })

# НОВЫЙ ЭНДПОИНТ ДЛЯ ЕЖЕДНЕВНОГО ЧЕК-ИНА (ДЕРЕВО)
@app.route('/api/daily-checkin', methods=['POST'])
def daily_checkin():
    data = request.json
    telegram_id = data.get('telegram_id')
    
    if not telegram_id:
        return jsonify({'error': 'telegram_id required'}), 400
    
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    
    if not user:
        session.close()
        return jsonify({'error': 'User not found'}), 404
    
    streak = update_streak(session, user)
    session.close()
    
    planted_today = (streak % 30 == 0 and streak > 0)
    
    return jsonify({
        'success': True,
        'current_streak': streak,
        'trees_planted': user.trees_planted,
        'planted_today': planted_today,
        'message': 'Чек-ин засчитан! Твоё дерево растёт 🌱'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'exercises_count': len(EXERCISES)
    })

from openai import OpenAI
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

@app.route('/api/personalized-exercises/<telegram_id>', methods=['GET'])
def personalized_exercises(telegram_id):
    session = Session()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    session.close()
    profile_text = "Нет данных о психологическом профиле."
    if user and user.psychological_profile:
        stress = user.psychological_profile.stress_factors or {}
        emotions = user.psychological_profile.emotional_patterns or {}
        profile_text = f"Стресс-факторы: {json.dumps(stress, ensure_ascii=False)}. Эмоциональные паттерны: {json.dumps(emotions, ensure_ascii=False)}."
    prompt = f"""
    Ты — эксперт по здоровью спины и осанки.
    {profile_text}
   
    Сгенерируй 5-7 простых упражнений (1-3 минуты) для улучшения осанки и снижения стресса.
    Упражнения безопасные, без инвентаря.
    Формат строго JSON массив объектов:
    [
      {{
        "title": "Короткое название",
        "description": "Пошаговое описание выполнения",
        "duration": "2 минуты",
        "benefit": "Снижает напряжение в шее"
      }}
    ]
    Только JSON, без лишнего текста.
    """
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1000
        )
        exercises = json.loads(completion.choices[0].message.content)
        return jsonify({'success': True, 'exercises': exercises})
    except Exception as e:
        print(f"GPT error: {e}")
        return jsonify({'success': True, 'exercises': EXERCISES[:5]})
       
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
