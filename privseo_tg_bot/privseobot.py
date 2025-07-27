import telebot
from telebot.types import (Message, ReplyKeyboardMarkup, 
                          ReplyKeyboardRemove, InlineKeyboardMarkup, 
                          InlineKeyboardButton)
import requests
from datetime import datetime
import base64
import re
from io import BytesIO
from PIL import Image
import yaml
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из .env файла
load_dotenv()

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER", "PrivateSeo")
REPO_NAME = os.getenv("REPO_NAME", "privateseo.github.io")
BRANCH = os.getenv("BRANCH", "main")
NEWS_DIR = "_posts/news"
IMAGES_DIR = "assets/images/news"
MENU_PATH = "_data/menu.yml"

# --- КАТЕГОРИИ ---
CATEGORIES = {
    "frontend": "👨‍💻 Frontend",
    "backend": "⚙️ Backend",
    "seo": "🔍 SEO",
    "tools": "🛠️ Инструменты",
    "cases": "📊 Кейсы"
}

# Таблица транслитерации
TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# --- ОБЩИЕ ФУНКЦИИ ---
def is_authorized(user_id):
    return user_id == AUTHORIZED_USER_ID

def get_menu_data():
    response = requests.get(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{MENU_PATH}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )
    if response.status_code == 200:
        content = base64.b64decode(response.json()['content']).decode('utf-8')
        return yaml.safe_load(content)
    return {"items": []}

def update_menu_data(data):
    content = yaml.dump(data, allow_unicode=True, sort_keys=False)
    sha = get_menu_sha()
    if not sha:
        return False
    
    response = requests.put(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{MENU_PATH}",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        },
        json={
            "message": "Обновление меню через Telegram бота",
            "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            "branch": BRANCH,
            "sha": sha
        }
    )
    return response.status_code == 200

def get_menu_sha():
    response = requests.get(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{MENU_PATH}",
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )
    return response.json().get('sha') if response.status_code == 200 else None

def menu_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📋 Показать меню", callback_data="show_menu"),
        InlineKeyboardButton("➕ Добавить пункт", callback_data="add_item")
    )
    markup.row(
        InlineKeyboardButton("✏️ Редактировать пункт", callback_data="edit_item"),
        InlineKeyboardButton("❌ Удалить пункт", callback_data="delete_item")
    )
    return markup

def category_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for cat in CATEGORIES.values():
        markup.add(cat)
    return markup

def transliterate(text):
    text = text.lower()
    result = []
    for char in text:
        if char in TRANSLIT_TABLE:
            result.append(TRANSLIT_TABLE[char])
        elif re.match(r'[a-z0-9-]', char):
            result.append(char)
        else:
            result.append('-')
    return ''.join(result)

def optimize_image(image_bytes, quality=80):
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        output = BytesIO()
        img.save(output, format='WEBP', quality=quality, method=6)
        optimized_bytes = output.getvalue()
        output.close()
        return optimized_bytes
    except Exception as e:
        raise Exception(f"Ошибка оптимизации изображения: {str(e)}")

def get_file_sha(path):
    try:
        response = requests.get(
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"}
        )
        if response.status_code == 200:
            return response.json().get('sha')
        return None
    except Exception:
        return None

def upload_to_github(path, content, message, is_binary=False):
    try:
        # Получаем текущий SHA файла (если он существует)
        sha = get_file_sha(path)
        
        if is_binary:
            content_base64 = base64.b64encode(content).decode('utf-8')
        else:
            content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        data = {
            "message": message,
            "branch": BRANCH,
            "content": content_base64
        }
        
        # Добавляем SHA, если файл уже существует
        if sha:
            data["sha"] = sha
        
        response = requests.put(
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            },
            json=data
        )
        
        if response.status_code not in (200, 201):
            error_data = response.json()
            error_msg = error_data.get('message', 'Неизвестная ошибка')
            
            # Добавляем дополнительную информацию об ошибке
            if 'documentation_url' in error_data:
                error_msg += f"\nДокументация: {error_data['documentation_url']}"
            
            raise Exception(f"GitHub API: {error_msg}")
        
        return response.json()
    except Exception as e:
        raise Exception(f"Ошибка загрузки на GitHub: {str(e)}")

def create_news_file_content(user_data, content, image_url=None):
    date = datetime.now().strftime('%Y-%m-%d')
    image_path = f"/{image_url}" if image_url else ""
    
    return f"""---
layout: news
name: "{user_data['name']}"
title: "{user_data['title']}"
description: "{user_data['description']}"
date: {date}
image: "{image_path}"
category: {user_data['category']}
---

{content}
"""

# --- ОБРАБОТЧИКИ КОМАНД ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if is_authorized(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "🌐 Управление сайтом\n\n"
            "/news - Добавить новость\n"
            "/menu - Управление меню\n"
            "/help - Справка"
        )
    else:
        bot.reply_to(message, "⛔ Доступ запрещен")

@bot.message_handler(commands=['menu'])
def manage_menu(message):
    if not is_authorized(message.from_user.id):
        return
    bot.send_message(message.chat.id, "🔧 Управление меню сайта:", reply_markup=menu_keyboard())

@bot.message_handler(commands=['news', 'add'])
def start_news_creation(message):
    if not is_authorized(message.from_user.id):
        return
    
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=category_keyboard())
    user_states[message.chat.id] = {'step': 'waiting_for_category'}

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---
@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_category' and m.text in CATEGORIES.values())
def process_category(message):
    category = next(k for k, v in CATEGORIES.items() if v == message.text)
    user_states[message.chat.id] = {
        'step': 'waiting_for_name',
        'category': category,
        'media': None
    }
    bot.send_message(message.chat.id, "📝 Введите название новости (для отображения на сайте):", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_name')
def process_name(message):
    user_states[message.chat.id]['name'] = message.text
    user_states[message.chat.id]['step'] = 'waiting_for_title'
    bot.send_message(message.chat.id, "🏷 Введите title (для SEO заголовка):")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_title')
def process_title(message):
    user_states[message.chat.id]['title'] = message.text
    user_states[message.chat.id]['step'] = 'waiting_for_description'
    bot.send_message(message.chat.id, "📄 Введите описание новости:")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_description')
def process_description(message):
    user_states[message.chat.id]['description'] = message.text
    user_states[message.chat.id]['step'] = 'waiting_for_media'
    bot.send_message(message.chat.id, "🖼 Отправьте изображение для новости (или /skip чтобы пропустить):")

@bot.message_handler(commands=['skip'], func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_media')
def skip_media(message):
    user_states[message.chat.id]['step'] = 'waiting_for_content'
    bot.send_message(message.chat.id, "💬 Введите основной текст новости (HTML/Markdown):")

@bot.message_handler(content_types=['photo'], func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_media')
def process_media(message):
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        original_image = bot.download_file(file_info.file_path)
        
        bot.send_chat_action(message.chat.id, 'upload_photo')
        optimized_image = optimize_image(original_image)
        
        user_states[message.chat.id]['media'] = optimized_image
        user_states[message.chat.id]['step'] = 'waiting_for_content'
        bot.send_message(message.chat.id, "✅ Изображение оптимизировано и готово к загрузке! Теперь введите основной текст:")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка обработки изображения: {str(e)}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('step') == 'waiting_for_content')
def process_content(message):
    try:
        user_data = user_states[message.chat.id]
        category = user_data['category']
        
        image_url = ""
        if user_data.get('media'):
            image_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.webp"
            image_path = f"{IMAGES_DIR}/{image_name}"
            
            try:
                upload_result = upload_to_github(
                    path=image_path,
                    content=user_data['media'],
                    message="Добавлено оптимизированное изображение новости (WebP)",
                    is_binary=True
                )
                
                if not upload_result:
                    raise Exception("Не удалось загрузить изображение")
                
                image_url = image_path
            except Exception as e:
                bot.send_message(message.chat.id, f"⚠️ Ошибка загрузки изображения: {str(e)}")
                # Продолжаем без изображения
                image_url = ""

        transliterated_name = transliterate(user_data['name'])
        filename = f"{datetime.now().strftime('%Y-%m-%d')}-{transliterated_name}.md"
        content = create_news_file_content(user_data, message.text, image_url)

        try:
            upload_result = upload_to_github(
                path=f"{NEWS_DIR}/{filename}",
                content=content,
                message=f"Добавлена новость: {user_data['name']}",
                is_binary=False
            )
            
            if upload_result:
                bot.send_message(
                    message.chat.id,
                    f"""✅ Новость успешно добавлена!
                    
📌 Категория: {CATEGORIES[category]}
📝 Название: {user_data['name']}
🔗 Ссылка: {upload_result["content"]["html_url"]}
🌐 URL на сайте: /news/{transliterated_name}/
🖼 Изображение: {'оптимизировано (WebP)' if image_url else 'отсутствует'}"""
                )
            else:
                raise Exception("Не удалось получить ссылку на новость")
        
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка загрузки новости: {str(e)}\n\nПопробуйте отправить новость еще раз.")
    
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Критическая ошибка: {str(e)}")
    finally:
        if message.chat.id in user_states:
            del user_states[message.chat.id]

# --- ОБРАБОТЧИКИ INLINE КНОПОК ---
@bot.callback_query_handler(func=lambda call: call.data == "show_menu")
def show_menu(call):
    try:
        menu = get_menu_data()
        text = "📋 Текущее меню:\n\n"
        for i, item in enumerate(menu['items'], 1):
            text += f"{i}. {item['title']} → {item['url']}\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=menu_keyboard())
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при получении меню: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "add_item")
def add_item_start(call):
    user_states[call.message.chat.id] = {"action": "add_item", "step": "title"}
    bot.edit_message_text(
        "Введите название нового пункта меню:",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_item"))
def edit_item_start(call):
    try:
        menu = get_menu_data()
        markup = InlineKeyboardMarkup()
        for i, item in enumerate(menu['items']):
            markup.add(InlineKeyboardButton(f"{i+1}. {item['title']}", callback_data=f"edit_select_{i}"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
        bot.edit_message_text(
            "Выберите пункт для редактирования:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при редактировании меню: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_item"))
def delete_item_start(call):
    try:
        menu = get_menu_data()
        markup = InlineKeyboardMarkup()
        for i, item in enumerate(menu['items']):
            markup.add(InlineKeyboardButton(f"{i+1}. {item['title']}", callback_data=f"delete_confirm_{i}"))
        markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
        bot.edit_message_text(
            "Выберите пункт для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при удалении пункта: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_select_"))
def edit_item_select(call):
    try:
        index = int(call.data.split("_")[2])
        user_states[call.message.chat.id] = {
            "action": "edit_item",
            "index": index,
            "step": "title"
        }
        bot.edit_message_text(
            "Введите новое название пункта (или /skip чтобы оставить текущее):",
            call.message.chat.id,
            call.message.message_id
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при выборе пункта: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_confirm_"))
def delete_item_confirm(call):
    try:
        index = int(call.data.split("_")[2])
        menu = get_menu_data()
        item = menu['items'][index]
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_execute_{index}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="back_to_menu")
        )
        
        bot.edit_message_text(
            f"Вы уверены, что хотите удалить пункт:\n\n{item['title']} → {item['url']}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при подтверждении удаления: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_execute_"))
def delete_item_execute(call):
    try:
        index = int(call.data.split("_")[2])
        menu = get_menu_data()
        deleted_item = menu['items'].pop(index)
        
        if update_menu_data(menu):
            bot.edit_message_text(
                f"✅ Пункт удален:\n{deleted_item['title']} → {deleted_item['url']}",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=menu_keyboard()
            )
        else:
            bot.edit_message_text(
                "❌ Ошибка при удалении пункта",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=menu_keyboard()
            )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка при удалении: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.edit_message_text(
        "🔧 Управление меню сайта:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=menu_keyboard()
    )

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('action') in ('add_item', 'edit_item') and 
                                  user_states[m.chat.id]['step'] == 'title')
def process_menu_item_title(message):
    try:
        user_data = user_states[message.chat.id]
        if message.text != '/skip':
            user_data['title'] = message.text
        user_data['step'] = 'url'
        bot.send_message(message.chat.id, "🌐 Введите URL для пункта меню:")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка обработки названия: {str(e)}")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get('action') in ('add_item', 'edit_item') and 
                                  user_states[m.chat.id]['step'] == 'url')
def process_menu_item_url(message):
    try:
        user_data = user_states[message.chat.id]
        menu = get_menu_data()
        
        if user_data['action'] == 'add_item':
            menu['items'].append({
                'title': user_data['title'],
                'url': message.text
            })
            success_msg = "✅ Пункт меню добавлен!"
        else:
            index = user_data['index']
            if 'title' in user_data:
                menu['items'][index]['title'] = user_data['title']
            menu['items'][index]['url'] = message.text
            success_msg = "✅ Пункт меню обновлен!"
        
        if update_menu_data(menu):
            bot.send_message(message.chat.id, success_msg, reply_markup=menu_keyboard())
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при сохранении меню")
        
        del user_states[message.chat.id]
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка обработки URL: {str(e)}")

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    print("🟢 Бот запущен! Ожидание сообщений...")
    bot.infinity_polling()