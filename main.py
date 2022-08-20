from telebot.types import InputMediaPhoto
from telebot.types import InputMediaVideo
from dotenv import load_dotenv
import telebot
import re
import vk_api
import requests
import sqlite3
import time
import os
import youtube_dl
import glob

load_dotenv()
telegram_api_token = os.getenv('telegram_api_token')
vk_api_token = os.environ.get('vk_api_token')
bot = telebot.TeleBot(telegram_api_token)
session = vk_api.VkApi(token=vk_api_token)
vk_last_post_dict_id = {}
bot_folder = '/home/alex/python_project/telegram_bot'
db_path = f'{bot_folder}/db/database.db'

# репосты
# музыка (блок аудио)
# кнопки
# управление из бота, а не из группы


def create_db():
    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        queries = []
        query_create_user_table = '''CREATE TABLE "telegram_user" (
                                        "telegram_chatid"	INTEGER NOT NULL,
                                        "telegram_userid"	INTEGER NOT NULL,
                                        "first_name"	TEXT,
                                        "last_name"	TEXT,
                                        "username"	TEXT,
                                        PRIMARY KEY("telegram_chatid")
                                 )'''
        queries.append(query_create_user_table)
        query_create_vk_group_table = '''CREATE TABLE "vk_user_group" (
                                            "FK_telegram_chatid"    INTEGER NOT NULL,
                                            "vk_group_name"	TEXT NOT NULL,
                                            "vk_group_url"	TEXT NOT NULL,
                                            FOREIGN KEY("FK_telegram_chatid") REFERENCES "telegram_user"("telegram_chatid"),
                                            PRIMARY KEY("FK_telegram_chatid","vk_group_name")
                                    )'''
        queries.append(query_create_vk_group_table)
        for query in queries:
            cursor.execute(query)


def sql_query(query, chat_id='', error_message=''):
    try:
        with sqlite3.connect(db_path) as db:
            cursor = db.cursor()
            output_query = query
            cursor.execute(output_query)
            output_query = cursor.fetchall()
            return output_query
    except sqlite3.IntegrityError:
        if error_message or chat_id:
            pass
        else:
            bot.send_message(chat_id, f'{error_message}')


def next_action_bot(message, response_text, next_func):
    chat_id = message.chat.id
    bot.send_message(chat_id, response_text)
    bot.register_next_step_handler(message, next_func)


def main():
    if not os.path.exists(f'{bot_folder}/temp'):
        os.makedirs(f'{bot_folder}/temp')

    if os.path.exists(db_path):
        pass
    else:
        create_db()

    @bot.message_handler(commands=['start', 'go'])
    def init_user(message):
        bot.send_message(message.chat.id, f'Приветствую')
        sql_query(
            query=f'''INSERT INTO telegram_user(telegram_userid, telegram_chatid, first_name, last_name, username) 
                VALUES (
                    {message.from_user.id},
                    {message.chat.id},
                    '{message.from_user.first_name}', 
                    '{message.from_user.last_name}', 
                    '{message.from_user.username}'
                )''', chat_id=message.chat.id)
        next_action_bot(message=message,
                        response_text='Хочешь добавить группу вк? (Да/Нет)',
                        next_func=vk_add_more_group)

    @bot.message_handler(commands=['save_vk_group'])
    def save_vk_group(message):
        groups = message.text.split(' ')
        for group in groups:
            try:
                if re.match('https://vk.com/([а-яА-Яa-zA-Z0-9]{1,9999}[^:])', group) != None \
                        and requests.get(url=group).status_code == 200:
                    vk_group_url = group
                    vk_group_name = vk_group_url.split('/')[3]
                    session.method('wall.get', {'domain': f'{vk_group_name}'})
                    sql_query(
                        query=f"""INSERT INTO vk_user_group(FK_telegram_chatid, vk_group_name, vk_group_url) 
                        VALUES (
                            {message.chat.id},
                            '{vk_group_name}',
                            '{vk_group_url}')""",
                        chat_id=message.chat.id,
                        error_message=f'{group} уже добавлена')
                else:
                    raise TypeError
            except (TypeError, vk_api.exceptions.ApiError):
                bot.send_message(message.chat.id, f'Группы {group} несуществует или является закрытой.')

        next_action_bot(message=message, response_text='Будем ещё группы добавлять? (Да/Нет)',
                        next_func=vk_add_more_group)

    @bot.message_handler(commands=['vk_add_more_group'])
    def vk_add_more_group(message):
        if message.content_type == 'text' and (message.text.lower() == 'да' or message.text.lower() == '/vk_add_more_group'):
            next_action_bot(message=message,
                            response_text='Вводи ссылку',
                            next_func=save_vk_group)
        elif message.content_type == 'text' and message.text.lower() == 'нет':
            bot.send_message(message.chat.id, 'Ок, начинаю смотреть за новыми постами')
            parse_source(message)
        else:
            next_action_bot(message=message,
                            response_text='Только да или нет',
                            next_func=vk_add_more_group)

    @bot.message_handler(commands=['list_groups'])
    def list_groups(message):
        text = 'Добавленные группы:\n'
        id_group = {}
        chat_groups = sql_query(
            query=f'''SELECT vk_group_name FROM vk_user_group WHERE FK_telegram_chatid={message.chat.id}''')
        for id, chat_group in enumerate(chat_groups):
            text = text + f'{id}. {chat_group[0]}\n'
            id_group[str(id)] = chat_group[0]
        parse_source(message)

    @bot.message_handler(commands=['vk_delete_group'])
    def vk_delete_group(message):
        text = 'Выберите группу для удаления:\n'
        id_group = {}
        chat_groups = sql_query(
            query=f'''SELECT vk_group_name FROM vk_user_group WHERE FK_telegram_chatid={message.chat.id}''')
        for id, chat_group in enumerate(chat_groups):
            text = text + f'{id}. {chat_group[0]}\n'
            id_group[str(id)] = chat_group[0]
        bot.send_message(message.chat.id, f'{text}\nТак же можно написать exit/cancel для отмены')

        @bot.message_handler(func=lambda message: True)
        def temp_vk_delete_group(message):
            if message.text in id_group.values() or message.text in id_group.keys():
                group_name = id_group[message.text] if message.text in id_group.keys() else message.text
                sql_query(
                    query=f'''DELETE FROM vk_user_group WHERE FK_telegram_chatid={message.chat.id} AND vk_group_name="{group_name}"''')
                bot.send_message(message.chat.id, 'Группа была удаленна')
                bot.send_message(message.chat.id, 'Ок, начинаю смотреть за новыми постами')
                parse_source(message)
            elif message.text == 'exit' or message.text == 'cancel':
                bot.send_message(message.chat.id, 'Ок, начинаю смотреть за новыми постами')
                parse_source(message)
            else:
                next_action_bot(message=message,
                                response_text='Вы ввели группу не из списка',
                                next_func=vk_delete_group)

    def vk_get_last_post(message, get_last_post_id=False, parse=True):
        vk_posts = {}
        vk_user_groups = sql_query(
            query=f"""SELECT vk_group_name FROM vk_user_group WHERE FK_telegram_chatid={message.chat.id}""")
        for vk_user_group in vk_user_groups:
            vk_user_group = vk_user_group[0]
            vk_last_post = session.method('wall.get', {'domain': f'{vk_user_group}'})
            vk_last_post = vk_last_post['items']
            vk_last_post = sorted(vk_last_post, key=lambda d: d['date'])[-1]
            if get_last_post_id:
                vk_last_post_dict_id[vk_user_group] = vk_last_post['id']
            if parse:
                vk_posts[vk_user_group] = vk_last_post
        #        time.sleep(60)
        return vk_posts

    def vk_parse_group_posts(message, parse_is_on):
        vk_posts = vk_get_last_post(message, get_last_post_id=False, parse=True)
        for vk_user_group, vk_group_post in vk_posts.items():
            print(vk_group_post)
            if 'attachments' in vk_group_post:
                all_photos = []
                all_videos = []
                all_links = []
                contains_photo = False
                contains_video = False
                contains_link = False
                attachments_last_post = vk_group_post['attachments']

                for attachment in attachments_last_post:
                    if attachment['type'] == 'photo':
                        photos = attachment['photo']['sizes']
                        photos = sorted(photos, key=lambda d: d['width'])
                        all_photos.append(
                            InputMediaPhoto(photos[-1]['url'], caption=f'{vk_group_post["text"]}\n\n{vk_user_group}')) \
                            if len(all_photos) == 0 \
                            else all_photos.append(InputMediaPhoto(photos[-1]['url']))
                        contains_photo = True

                    elif attachment['type'] == 'link':
                        vk_link_url = attachment['link']['url']
                        if 'photo' in attachment['link']:
                            photos = attachment['link']['photo']['sizes']
                            photos = sorted(photos, key=lambda d: d['width'])
                            all_links.append(
                                InputMediaPhoto(photos[-1]['url'],
                                                caption=f'{vk_group_post["text"]}\n{vk_link_url}\n\n{vk_user_group}')) \
                                if len(all_links) == 0 \
                                else all_links.append(InputMediaPhoto(photos[-1]['url']))
                        contains_link = True

                    elif attachment['type'] == 'video':
                        owner_id = attachment['video']['owner_id']
                        videos = attachment['video']['id']
                        access_key = attachment['video']['access_key']
                        vk_videos = session.method('video.get', {'videos': f'{owner_id}_{videos}_{access_key}'})
                        vk_videos = vk_videos['items']
                        for vk_video in vk_videos:
                            vk_video_url = vk_video['player']
                            ydl_opts = {
                                "outtmpl": f"{bot_folder}/temp/{vk_user_group}/{vk_video['id']}-{vk_video['date']}"}
                            if os.path.exists(ydl_opts['outtmpl']):
                                pass
                            else:
                                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                                    video_info = ydl.extract_info(vk_video_url, download=False)
                                    video_duration = video_info['duration']
                                    if video_duration < 600:
                                        ydl.download([vk_video_url])
                                        with open(ydl_opts['outtmpl'], "rb") as video:
                                            all_videos.append(InputMediaVideo(media=video.read(),
                                                                              caption=f"{vk_group_post['text']}\n\n{vk_user_group}"))  # тернарное выражение для первого ролика
                                        contains_video = True

                if vk_last_post_dict_id[vk_user_group] < vk_group_post['id']:
                    if contains_photo:
                        bot.send_media_group(message.chat.id, all_photos)
                        vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
                    elif contains_link:
                        bot.send_media_group(message.chat.id, all_links)
                        vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
                    elif contains_video:
                        bot.send_media_group(message.chat.id, all_videos)
                        vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
                        videos = glob.glob(f'{bot_folder}/temp/{vk_user_group}/*')
                        for video in videos:
                            os.remove(video)

            else:
                if vk_last_post_dict_id[vk_user_group] < vk_group_post['id']:
                    bot.send_message(message.chat.id, f'{vk_group_post["text"]}')
                    vk_last_post_dict_id[vk_user_group] = vk_group_post['id']

    def parse_source(message):
        parse_is_on = False
        vk_get_last_post(message, get_last_post_id=True, parse=False)
        while parse_is_on == False:
            parse_is_on = True
            vk_parse_group_posts(message, parse_is_on)

    bot.polling(none_stop=True)

if __name__ == "__main__":
    main()
