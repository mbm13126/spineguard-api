"""
SpineGuard API - Интеграция Mini App с существующим ботом
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

# Импортируем модели из твоего бота
from bot import User, PsychologicalProfile, Base

app = Flask(__name__)
CORS(app)

# Подключаемся к той же БД что и бот
engine = create_engine('sqlite:///spineguard.db')
Session = sessionmaker(bind=engine)

# Загружаем упражнения
with open('exercises.json', 'r', encoding='utf-8') as f:
    EXERCISES = json.load(f)

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
            return jsonify({'error': 'User not found'}), 404
        
        profile = user.psychological_profile
        
        # Формируем данные для дашборда
        data = {
            'success': True,
            'user': {
                'name': user.username or 'Пользователь',
                'telegram_id': user.telegram_id,
                'tokens': int(user.token_balance),
                'status': 'Отлично',  # Можно добавить логику определения
                # Для streak нужно добавить поле в БД, пока ставим 0
                'streak': 0,
                'level': 1,  # Можно рассчитывать от токенов
                'exercises_completed': 0  # Добавить счетчик в БД
            },
            'psych_map': {
                'stress_factors': profile.stress_factors if profile else {},
                'emotions': profile.emotional_patterns if profile else {},
                'updated_at': profile.last_updated.isoformat() if profile else None
            },
            'today': {
                'tokens': 0,  # Нужна статистика по дням
                'exercises': 0
            },
            'changes': {
                'tokens': 0,
                'exercises': 0
            },
            'reward_progress': 0  # Streak % 7
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
        
        # Начисляем токены (как в боте)
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

@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка работы API"""
    return jsonify({
        'status': 'ok',
        'message': 'SpineGuard API is running',
        'timestamp': datetime.now().isoformat()
    })

# ============================================
# ЗАПУСК
# ============================================

if __name__ == '__main__':
    print("🚀 Запускаем SpineGuard API Server...")
    print("📡 API доступен на http://localhost:5000")
    print("")
    print("📋 Endpoints:")
    print("   GET  /api/user/<telegram_id> - Данные пользователя")
    print("   GET  /api/exercises - Список упражнений")
    print("   POST /api/exercise/complete - Отметить выполнение")
    print("   GET  /api/psych-map/<telegram_id> - Психологическая карта")
    print("   GET  /api/health - Проверка работы")
    print("")
    print("✅ Сервер готов к работе!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
