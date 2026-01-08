"""
SpineGuard API - Standalone версия для Render
Без зависимости от bot.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)

# Модели базы данных (скопированы из bot.py)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    username = Column(String)
    token_balance = Column(Float, default=0.0)
    psychological_profile = relationship("PsychologicalProfile", back_populates="user", uselist=False)

class PsychologicalProfile(Base):
    __tablename__ = 'psychological_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    stress_factors = Column(JSON, default=dict)
    emotional_patterns = Column(JSON, default=dict)
    last_updated = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="psychological_profile")

# Подключение к БД (на Render будет создана пустая)
engine = create_engine('sqlite:///spineguard.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Загружаем упражнения
try:
    with open('exercises.json', 'r', encoding='utf-8') as f:
        EXERCISES = json.load(f)
except FileNotFoundError:
    EXERCISES = []
    print("⚠️ Файл exercises.json не найден. Используем пустой массив.")

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/api/user/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    """
    Получить данные пользователя для Mini App
    """
    try:
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user:
            session.close()
            # Возвращаем дефолтные данные если пользователя нет
            return jsonify({
                'success': True,
                'user': {
                    'name': 'Пользователь',
                    'telegram_id': telegram_id,
                    'tokens': 0,
                    'status': 'Отлично',
                    'streak': 0,
                    'level': 1,
                    'exercises_completed': 0
                },
                'psych_map': {
                    'stress_factors': {},
                    'emotions': {},
                    'updated_at': None
                },
                'today': {'tokens': 0, 'exercises': 0},
                'changes': {'tokens': 0, 'exercises': 0},
                'reward_progress': 0
            })
        
        profile = user.psychological_profile
        
        # Формируем данные для дашборда
        data = {
            'success': True,
            'user': {
                'name': user.username or 'Пользователь',
                'telegram_id': user.telegram_id,
                'tokens': int(user.token_balance),
                'status': 'Отлично',
                'streak': 0,
                'level': 1,
                'exercises_completed': 0
            },
            'psych_map': {
                'stress_factors': profile.stress_factors if profile else {},
                'emotions': profile.emotional_patterns if profile else {},
                'updated_at': profile.last_updated.isoformat() if profile else None
            },
            'today': {'tokens': 0, 'exercises': 0},
            'changes': {'tokens': 0, 'exercises': 0},
            'reward_progress': 0
        }
        
        session.close()
        return jsonify(data)
        
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/exercises', methods=['GET'])
def get_exercises():
    """
    Получить список упражнений
    """
    try:
        return jsonify({
            'success': True,
            'exercises': EXERCISES
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/exercise/complete', methods=['POST'])
def complete_exercise():
    """
    Отметить выполнение упражнения
    """
    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        exercise_id = data.get('exercise_id')
        
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user:
            session.close()
            return jsonify({'error': 'User not found'}), 404
        
        # Начисляем токены
        tokens_earned = 20
        user.token_balance += tokens_earned
        session.commit()
        
        current_balance = user.token_balance
        session.close()
        
        return jsonify({
            'success': True,
            'tokens_earned': tokens_earned,
            'total_tokens': int(current_balance),
            'message': 'Упражнение засчитано!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/psych-map/<telegram_id>', methods=['GET'])
def get_psych_map(telegram_id):
    """
    Получить психологическую карту
    """
    try:
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user or not user.psychological_profile:
            session.close()
            return jsonify({'success': True, 'psych_map': None})
        
        profile = user.psychological_profile
        
        data = {
            'success': True,
            'psych_map': {
                'stress_factors': profile.stress_factors,
                'emotional_patterns': profile.emotional_patterns,
                'last_updated': profile.last_updated.isoformat()
            }
        }
        
        session.close()
        return jsonify(data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-user', methods=['POST'])
def sync_user():
    """
    Синхронизация пользователя из локального бота
    """
    try:
        data = request.json
        telegram_id = data.get('telegram_id')
        username = data.get('username')
        
        if not telegram_id:
            return jsonify({'error': 'telegram_id required'}), 400
        
        session = Session()
        
        # Проверяем существует ли пользователь
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user:
            # Создаём нового пользователя на Render
            user = User(
                telegram_id=telegram_id,
                username=username,
                token_balance=0.0
            )
            session.add(user)
            session.flush()  # Получаем ID пользователя
            
            # Создаём психологический профиль
            profile = PsychologicalProfile(user_id=user.id)
            session.add(profile)
            
            session.commit()
            message = 'User created on Render'
        else:
            # Обновляем username если изменился
            if username and user.username != username:
                user.username = username
                session.commit()
            message = 'User already exists'
        
        # ВАЖНО: Сохраняем данные ДО закрытия сессии
        result = {
            'success': True,
            'message': message,
            'user': {
                'telegram_id': user.telegram_id,
                'username': user.username,
                'tokens': int(user.token_balance)
            }
        }
        
        session.close()
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Ошибка sync-user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/fix-user/<telegram_id>', methods=['GET'])
def fix_user(telegram_id):
    """
    Временный endpoint для обновления username
    """
    try:
        session = Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user:
            user.username = 'MBM_13'
            user.token_balance = 0.0
            
            # Сохраняем ДО получения данных
            session.commit()
            
            result = {
                'success': True,
                'message': 'User updated',
                'username': user.username,
                'tokens': int(user.token_balance)
            }
            
            session.close()
            return jsonify(result)
        else:
            session.close()
            return jsonify({'error': 'User not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```
        
@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка работы API"""
    return jsonify({
        'status': 'ok',
        'message': 'SpineGuard API is running',
        'timestamp': datetime.now().isoformat(),
        'exercises_count': len(EXERCISES)
    })

# ============================================
# ЗАПУСК
# ============================================

if __name__ == '__main__':
    import os
    
    print("🚀 Запускаем SpineGuard API Server...")
    port = int(os.environ.get('PORT', 5000))
    print(f"📡 API доступен на порт {port}")
    print("")
    print("📋 Endpoints:")
    print("   GET  /api/user/<telegram_id> - Данные пользователя")
    print("   GET  /api/exercises - Список упражнений")
    print("   POST /api/exercise/complete - Отметить выполнение")
    print("   GET  /api/psych-map/<telegram_id> - Психологическая карта")
    print("   GET  /api/health - Проверка работы")
    print("")
    print("✅ Сервер готов к работе!")
    
    app.run(host='0.0.0.0', port=port, debug=False)
