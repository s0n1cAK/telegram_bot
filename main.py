from telebot.types import InputMediaPhoto
from dotenv import load_dotenv
import telebot
import re
import vk_api
import requests
import sqlite3
import time
import os

load_dotenv()
telegram_api_token = os.getenv('telegram_api_token')
vk_api_token = os.environ.get('vk_api_token')
bot = telebot.TeleBot(telegram_api_token)
session = vk_api.VkApi(token=vk_api_token)
vk_last_post_dict_id = {}
db_path = 'db/database.db'
def main():

    @bot.message_handler(commands=['start', 'go'])
    def init_user(message):
        bot.send_message(message.chat.id, f'Приветствую')
        message = bot.send_message(message.chat.id, f'Хочешь добавить группу вк? (Да/Нет)')
        bot.register_next_step_handler(message, vk_add_more_group)

    @bot.message_handler(commands=['save_vk_group'])
    def save_vk_group(message):
        try:
            if re.match('https://vk.com/([а-яА-Яa-zA-Z0-9]{1,9999}[^:])', message.text) != None \
                    and requests.get(url=message.text).status_code == 200:
                vk_group_url = message.text
                vk_group_name = vk_group_url.split('/')[3]
                try:
                    with sqlite3.connect(db_path) as db:
                        cursor = db.cursor()
                        add_telegram_user = f"""INSERT INTO telegram_user(telegram_userid, first_name, last_name, username) VALUES ({message.from_user.id}, '{message.from_user.first_name}', '{message.from_user.last_name}', '{message.from_user.username}')"""
                        cursor.execute(add_telegram_user)
                except sqlite3.IntegrityError:
                    pass
                finally:
                    try:
                        with sqlite3.connect(db_path) as db:
                            cursor = db.cursor()
                            add_vk_group = f"""INSERT INTO vk_user_group(FK_telegram_userid, vk_group_name, vk_group_url) VALUES ({message.from_user.id}, '{vk_group_name}', '{vk_group_url}')"""
                            cursor.execute(add_vk_group)
                    except sqlite3.IntegrityError:
                        bot.send_message(message.chat.id, 'Эта группа уже добавлена ')

                message = bot.send_message(message.chat.id, f'Будем ещё группы добавлять? (Да/Нет)')
                bot.register_next_step_handler(message, vk_add_more_group)
            elif message.text == '/exit' or message.text == 'exit':
                message = bot.send_message(message.chat.id, f'Будем ещё группы добавлять? (Да/Нет)')
                bot.register_next_step_handler(message, vk_add_more_group)
            else:
                bot.send_message(message.chat.id, 'Вы ввели не существующую группу')
                message = bot.send_message(message.chat.id, f'Введи группы вк, которую хочешь добавить.')
                bot.register_next_step_handler(message, save_vk_group)
        except TypeError:
            bot.send_message(message.chat.id, 'Вы ввели не существующую группу')
            message = bot.send_message(message.chat.id, f'Введи группы вк, которую хочешь добавить.')
            bot.register_next_step_handler(message, save_vk_group)
    @bot.message_handler(commands=['vk_add_more_group'])
    def vk_add_more_group(message):
        if message.content_type == 'text' and message.text.lower() == 'да':
            message = bot.send_message(message.chat.id, 'Вводи ссылку')
            bot.register_next_step_handler(message, save_vk_group)
        elif message.content_type == 'text' and message.text.lower() == 'нет':
            message = bot.send_message(message.chat.id, 'Ок, начинаю смотреть за новыми постами')
            vk_parse_group_posts(message)
        else:
            message = bot.send_message(message.chat.id, f"Только да или нет")
            bot.register_next_step_handler(message, vk_add_more_group)

    def vk_get_last_post(message, get_last_post_id=False, parse=True):
        vk_posts = {}

        with sqlite3.connect(db_path) as db:
            cursor = db.cursor()
            vk_user_groups = f"""SELECT vk_group_name FROM vk_user_group WHERE FK_telegram_userid={message.from_user.id}"""
            cursor.execute(vk_user_groups)
            vk_user_groups = cursor.fetchall()

            for vk_user_group in vk_user_groups:
                vk_user_group = vk_user_group[0]
                vk_last_post = session.method('wall.get', {'domain': f'{vk_user_group}'})
                vk_last_post = vk_last_post['items']
                vk_last_post = sorted(vk_last_post, key=lambda d: d['date'])[-1]
                if get_last_post_id:
                    vk_last_post_dict_id[vk_user_group] = vk_last_post['id']
                if parse:
                    vk_posts[vk_user_group] = vk_last_post
        time.sleep(10)
        return vk_posts

    @bot.message_handler()
    def vk_parse_group_posts(message):
        vk_get_last_post(message, get_last_post_id=True, parse=False)
        while True:
            vk_posts = vk_get_last_post(message, get_last_post_id=False, parse=True)
            for vk_user_group, vk_group_post in vk_posts.items():
                if 'attachments' in vk_group_post:
                    all_photos = []
                    all_videos = []
                    all_links = []
                    contains_photo = False
                    contains_video = False
                    contains_link = False
                    print(vk_group_post)
                    attachments_last_post = vk_group_post['attachments']

                    for attachment in attachments_last_post:
                        if attachment['type'] == 'photo':
                            photos = attachment['photo']['sizes']
                            photos = sorted(photos, key=lambda d: d['width'])
                            all_photos.append(InputMediaPhoto(photos[-1]['url'], vk_group_post["text"])) \
                                if len(all_photos) == 0 \
                                else all_photos.append(InputMediaPhoto(photos[-1]['url']))
                            contains_photo = True

                        elif attachment['type'] == 'link':
                            vk_link_url = attachment['link']['url']
                            if 'photo' in attachment['link']:
                                photos = attachment['link']['photo']['sizes']
                                photos = sorted(photos, key=lambda d: d['width'])
                                all_links.append(
                                    InputMediaPhoto(photos[-1]['url'], f'{vk_group_post["text"]}\n{vk_link_url}')) \
                                    if len(all_links) == 0 \
                                    else all_links.append(InputMediaPhoto(photos[-1]['url']))
                            contains_link = True
                        # elif attachment['type'] == 'video':
                        #     owner_id = attachment['video']['owner_id']
                        #     videos = attachment['video']['id']
                        #     access_key = attachment['video']['access_key']
                        #     print(owner_id, videos, access_key)
                        #     vk_video_url = session.method('video.get', {'videos':f'{owner_id}_{videos}_{access_key}'})
                        #     vk_video_url = f'https://vk.com/video-{owner_id}_{videos}'
                        #     vk_video_path = f'temp/videos/{owner_id}_{videos}_{access_key}.mp4'
                        #     contains_video = True
                    print(vk_last_post_dict_id[vk_user_group], vk_group_post['id'])
                    if vk_last_post_dict_id[vk_user_group] < vk_group_post['id']:
                        if contains_photo:
                            bot.send_media_group(message.chat.id, all_photos)
                            vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
                        elif contains_link:
                            bot.send_media_group(message.chat.id, all_links)
                            vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
                        # elif contains_video:
                        #     bot.send_video(message.chat.id, video=open(vk_video_path, 'rb'), caption=vk_last_post["text"])
                        #     os.remove(vk_video_path)
                else:
                    if vk_last_post_dict_id[vk_user_group] < vk_group_post['id']:
                        bot.send_message(message.chat.id, f'{vk_group_post["text"]}')
                        vk_last_post_dict_id[vk_user_group] = vk_group_post['id']
            print(1)
    bot.polling()


if __name__ == "__main__":
    main()