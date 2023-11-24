from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cardinal import Cardinal

from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from tg_bot import CBT, static_keyboards as skb, utils
from locales.localizer import Localizer
from FunPayAPI.updater import events
from logging import getLogger
from threading import Thread
import telebot
import time
import json
import os


NAME = "Chat Sync Plugin"
VERSION = "0.0.2"
DESCRIPTION = "Плагин, синхронизирующий FunPay чаты с Telegram чатом (форумом).\n\nОтправляй сообщение в нужную тему - оно будет отправляться в нужный FunPay чат! И наоборот!"
CREDITS = "@woopertail"
UUID = "745ed27e-3196-47c3-9483-e382c09fd2d8"
SETTINGS_PAGE = True
PLUGIN_FOLDER = f"storage/plugins/{UUID}/"

SPECIAL_SYMBOL = "⁢"
MIN_BOTS = 4
LOGGER_PREFIX = "[CHAT SYNC PLUGIN]"
logger = getLogger("FPC.shat_sync")


localizer = Localizer()
_ = localizer.translate


# CALLBACKS
EDIT_SYNC_BOT = "sync_plugin.edit_bot"
ADD_SYNC_BOT = "sync_plugin.add_bot"
DELETE_SYNC_BOT = "sync_plugin.delete_bot"
SETUP_SYNC_CHAT = "sync_plugin.setup_chat"
DELETE_SYNC_CHAT = "sync_plugin.delete_chat"
PLUGIN_NO_BUTTON = "sunc_plugin.no"


# KEYBOARDS
def plugin_settings_kb(cs: ChatSync, offset: int) -> K:
    kb = K()
    for index, bot in enumerate(cs.bots):
        try:
            name = "@" + bot.get_me().username
        except:
            name = bot.token
        kb.row(B(name, callback_data=f"{EDIT_SYNC_BOT}:{index}:{offset}"),
               B("🗑️", callback_data=f"{DELETE_SYNC_BOT}:{index}:{offset}"))
    kb.add(B("➕ Добавить Telegram бота", callback_data=f"{ADD_SYNC_BOT}:{offset}"))
    kb.add(B(_("gl_back"), callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:{offset}"))
    return kb


def back_keyboard(offset: int) -> K:
    return K().add(B(_("gl_back"), callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}:{offset}"))


def setup_chat_keyboard() -> K:
    return K().row(B(_("gl_yes"), callback_data=SETUP_SYNC_CHAT),
                   B(_("gl_no"), callback_data=PLUGIN_NO_BUTTON))


def delete_chat_keyboard() -> K:
    return K().row(B(_("gl_yes"), callback_data=DELETE_SYNC_CHAT),
                   B(_("gl_no"), callback_data=PLUGIN_NO_BUTTON))


class ChatSync:
    def __init__(self, crd: Cardinal):
        self.cardinal = crd
        self.notification_last_stack_id = ""
        self.attributation_last_stack_id = ""
        self.sync_chats_running = False
        self.settings: dict | None = None
        self.threads: dict | None = None
        self.bots: list[telebot.TeleBot] | None = None
        self.current_bot: telebot.TeleBot | None = None
        self.initialized = False  # Боты, настройки и топики загружены без ошибок.
        self.ready = False  # Все условия для начала работы соблюдены (привязан чат, ботов 3 или больше).
        self.plugin_uuid = UUID
        self.tg = None
        self.tgbot = None
        if self.cardinal.telegram:
            self.tg = self.cardinal.telegram
            self.tgbot = self.tg.bot

        self.init_chat_synced = False

        setattr(ChatSync.send_message, "plugin_uuid", UUID)
        setattr(ChatSync.ingoing_message_handler, "plugin_uuid", UUID)
        setattr(ChatSync.sync_chat_on_start_handler, "plugin_uuid", UUID)
        setattr(ChatSync.setup_event_attributes, "plugin_uuid", UUID)

    def load_settings(self):
        """
        Загружает настройки плагина.
        """
        if not os.path.exists(os.path.join(PLUGIN_FOLDER, "settings.json")):
            logger.warning(f"{LOGGER_PREFIX} Файл с настройками не найден.")
            self.settings = {"chat_id": None}
        else:
            with open(os.path.join(PLUGIN_FOLDER, "settings.json"), "r", encoding="utf-8") as f:
                self.settings = json.loads(f.read())
            logger.info(f"{LOGGER_PREFIX} Загрузил настройки.")

    def load_threads(self):
        """
        Загружает список Telegram-топиков.
        """
        if not os.path.exists(os.path.join(PLUGIN_FOLDER, "threads.json")):
            logger.warning(f"{LOGGER_PREFIX} Файл с данными о Telegram топиках не найден.")
            self.threads = {}
        else:
            with open(os.path.join(PLUGIN_FOLDER, "threads.json"), "r", encoding="utf-8") as f:
                self.threads = json.loads(f.read())
            logger.info(f"{LOGGER_PREFIX} Загрузил данные о Telegram топиках.")

    def load_bots(self):
        """
        Загружает и инициализирует Telegram ботов.
        """
        if not os.path.exists(os.path.join(PLUGIN_FOLDER, "bots.json")):
            logger.warning(f"{LOGGER_PREFIX} Файл с токенами Telegram-ботов не найден.")
            self.bots = []
            return

        with open(os.path.join(PLUGIN_FOLDER, "bots.json"), "r", encoding="utf-8") as f:
            tokens = json.loads(f.read())

        bots = []
        for i in tokens:
            bot = telebot.TeleBot(i, parse_mode="HTML", allow_sending_without_reply=True)
            try:
                data = bot.get_me()
                if not data:
                    continue
                logger.info(f"{LOGGER_PREFIX} Бот @{data.username} инициализирован.")
                bots.append(bot)
            except:
                logger.error(
                    f"{LOGGER_PREFIX} Произошла ошибка при инициализации Telegram бота с токеном $YELLOW{i}$RESET.")
                logger.debug("TRACEBACK", exc_info=True)

        logger.info(f"{LOGGER_PREFIX} Инициализация ботов завершена. Ботов инициализировано: $YELLOW{len(bots)}$RESET.")
        self.bots = bots
        self.current_bot = self.bots[0] if self.bots else None

    def save_threads(self):
        """
        Сохраняет Telegram-топики.
        """
        if not os.path.exists(PLUGIN_FOLDER):
            os.makedirs(PLUGIN_FOLDER)
        with open(os.path.join(PLUGIN_FOLDER, "threads.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(self.threads))

    def save_settings(self):
        """
        Сохраняет настройки.
        """
        if not os.path.exists(PLUGIN_FOLDER):
            os.makedirs(PLUGIN_FOLDER)
        with open(os.path.join(PLUGIN_FOLDER, "settings.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(self.settings))

    def save_bots(self):
        """
        Сохраняет токены ботов.
        """
        if not os.path.exists(PLUGIN_FOLDER):
            os.makedirs(PLUGIN_FOLDER)
        with open(os.path.join(PLUGIN_FOLDER, "bots.json"), "w", encoding="utf-8") as f:
            data = [i.token for i in self.bots]
            f.write(json.dumps(data, ensure_ascii=False))

    def swap_curr_bot(self):
        """
        Переключает текущего бота на следующего.
        """
        if not self.current_bot and not self.bots:
            return
        try:
            self.current_bot = self.bots[self.bots.index(self.current_bot) + 1]
        except IndexError:
            self.current_bot = self.bots[0]

    def is_outgoing_message(self, m: telebot.types.Message) -> bool:
        if self.settings["chat_id"] and m.chat.id == self.settings["chat_id"] and \
                m.reply_to_message and m.reply_to_message.forum_topic_created:
            if m.entities:
                for i in m.entities:
                    if i.type == "bot_command" and i.offset == 0:
                        return False
            return True
        return False

    def new_synced_chat(self, chat_id: int, chat_name: str) -> bool:
        try:
            topic = self.current_bot.create_forum_topic(self.settings["chat_id"], f"{chat_name} ({chat_id})",
                                                        icon_custom_emoji_id="5417915203100613993")
            self.swap_curr_bot()
            self.threads[str(chat_id)] = topic.message_thread_id
            self.save_threads()
            logger.info(f"{LOGGER_PREFIX} FunPay чат $YELLOW{chat_name} (CID: {chat_id})$RESET связан с Telegram темой $YELLOW{topic.message_thread_id}$RESET.")
            return True
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при связывании FunPay чата с Telegram темой.")
            logger.debug("TRACEBACK", exc_info=True)
            return False

    # HANDLERS
    # pre init
    def load(self):
        try:
            self.load_settings()
            self.load_threads()
            self.load_bots()
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при инициализации плагина.")
            logger.debug("TRACEBACK", exc_info=True)
            return
        logger.info(f"{LOGGER_PREFIX} Плагин инициализирован.")
        self.initialized = True

        if self.settings["chat_id"] and len(self.bots) >= MIN_BOTS:
            self.ready = True

    def setup_event_attributes(self, c: Cardinal, e: events.NewMessageEvent):
        if e.stack.id() == self.attributation_last_stack_id:
            return
        self.attributation_last_stack_id = e.stack.id()
        for event in e.stack.get_stack():
            if event.message.text and SPECIAL_SYMBOL in event.message.text:
                event.message.text = event.message.text.replace(SPECIAL_SYMBOL, "")
                setattr(event, "sync_ignore", True)

    def replace_handler(self):
        if not self.initialized:
            return
        for index, handler in enumerate(self.cardinal.new_message_handlers):
            if handler.__name__ == "send_new_msg_notification_handler":
                break
        self.cardinal.new_message_handlers.insert(index, self.ingoing_message_handler)
        self.cardinal.new_message_handlers.insert(0, self.setup_event_attributes)
        self.cardinal.init_message_handlers.append(self.sync_chat_on_start_handler)

    def bind_tg_handlers(self):
        if not self.initialized:
            return

        self.tg.cbq_handler(self.open_settings_menu, lambda c: c.data.startswith(f"{CBT.PLUGIN_SETTINGS}:{UUID}:"))
        self.tg.cbq_handler(self.act_add_sync_bot, lambda c: c.data.startswith(ADD_SYNC_BOT))
        self.tg.cbq_handler(self.delete_sync_bot, lambda c: c.data.startswith(DELETE_SYNC_BOT))
        self.tg.cbq_handler(self.confirm_setup_sync_chat, lambda c: c.data == SETUP_SYNC_CHAT)
        self.tg.cbq_handler(self.confirm_delete_sync_chat, lambda c: c.data == DELETE_SYNC_CHAT)
        self.tg.cbq_handler(self.no, lambda c: c.data == PLUGIN_NO_BUTTON)
        self.tg.msg_handler(self.add_sync_bot, func=lambda m: self.tg.check_state(m.chat.id, m.from_user.id, ADD_SYNC_BOT))
        self.tg.msg_handler(self.send_funpay_image, content_types=["photo"], func=lambda m: self.is_outgoing_message(m))
        self.tg.msg_handler(self.send_message, func=lambda m: self.is_outgoing_message(m))
        self.tg.msg_handler(self.setup_sync_chat, commands=["setup_sync_chat"])
        self.tg.msg_handler(self.delete_sync_chat, commands=["delete_sync_chat"])
        self.tg.msg_handler(self.sync_chats, commands=["sync_chats"])
        self.tg.msg_handler(self.watch_handler, commands=["watch"])
        self.tg.msg_handler(self.history_handler, commands=["history"])

        self.cardinal.add_telegram_commands(UUID, [
            ("setup_sync_chat", "Активировать группу для синхронизации", True),
            ("delete_sync_chat", "Деактивировать группу для синхронизации", True),
            ("sync_chats", "Ручная синхронизация чатов", True),
            ("watch", "Что сейчас смотрит пользователь?", True),
            ("history", "Последние 25 сообщений чата", True)
        ])

    # new message
    def ingoing_message(self, c: Cardinal, e: events.NewMessageEvent):
        chat_id, chat_name = e.message.chat_id, e.message.chat_name
        if str(chat_id) not in self.threads:
            if not self.new_synced_chat(chat_id, chat_name):
                return

        events_list = [e for e in e.stack.get_stack() if not hasattr(e, "sync_ignore")]
        if not events_list:
            return

        thread_id = self.threads[str(chat_id)]
        text = ""
        last_message_author_id = -1
        last_by_bot = False
        for i in events_list:
            message_text = str(i.message)
            if i.message.author_id == last_message_author_id and i.message.by_bot == last_by_bot:
                author = ""
            elif i.message.author_id == c.account.id:
                author = f"<i><b>🤖 {_('you')} (<i>FPC</i>):</b></i> " if i.message.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
            elif i.message.author_id == 0:
                author = f"<i><b>🔵 {i.message.author}: </b></i>"
            elif i.message.badge:
                author = f"<i><b>🆘 {i.message.author} ({_('support')}): </b></i>"
            elif i.message.author == i.message.chat_name:
                author = f"<i><b>👤 {i.message.author}: </b></i>"
            else:
                author = f"<i><b>🆘 {i.message.author} {_('support')}: </b></i>"

            if not i.message.text:
                msg_text = f"<a href=\"{message_text}\">{_('photo')}</a>"
            elif i.message.author_id == 0:
                msg_text = f"<b><i>{utils.escape(message_text)}</i></b>"
            else:
                msg_text = utils.escape(message_text)

            text += f"{author}{msg_text}\n\n"
            last_message_author_id = i.message.author_id
            last_by_bot = i.message.by_bot

        try:
            self.current_bot.send_message(self.settings["chat_id"], text, message_thread_id=thread_id)
            self.swap_curr_bot()
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при отправке сообщения в Telegram чат.")
            logger.debug("TRACEBACK", exc_info=True)

    def ingoing_message_handler(self, c: Cardinal, e: events.NewMessageEvent):
        if not self.ready:
            return
        if e.stack.id() == self.notification_last_stack_id:
            return
        self.notification_last_stack_id = e.stack.id()
        Thread(target=self.ingoing_message, args=(c, e), daemon=True).start()

    # init message
    def sync_chat_on_start(self, c: Cardinal):
        chats = c.account.get_chats()
        self.sync_chats_running = True
        for i in chats:
            chat = chats[i]
            if str(i) in self.threads:
                continue
            self.new_synced_chat(chat.id, chat.name)
            time.sleep(1)
        self.sync_chats_running = False

    def sync_chat_on_start_handler(self, c: Cardinal, e: events.InitialChatEvent):
        if self.init_chat_synced or not self.ready:
            return
        self.init_chat_synced = True
        Thread(target=self.sync_chat_on_start, args=(c,), daemon=True).start()

    # TELEGRAM
    def no(self, c: telebot.types.CallbackQuery):
        self.tgbot.delete_message(c.message.chat.id, c.message.id)

    def open_settings_menu(self, c: telebot.types.CallbackQuery):
        """
        Основное меню настроек плагина.
        """
        split = c.data.split(":")
        uuid, offset = split[1], int(split[2])
        try:
            chat_name = self.tgbot.get_chat(self.settings["chat_id"])
            if not chat_name:
                chat_name = None
            elif chat_name.username:
                chat_name = f"@{chat_name.username}"
            elif chat_name.invite_link:
                chat_name = chat_name.invite_link
            else:
                chat_name = f"<code>{self.settings['chat_id']}</code>"
        except:
            chat_name = None

        instructions = "Все готово! Плагин работает, больше делать ничего не нужно :)"
        if len(self.bots) < MIN_BOTS:
            instructions = f"Сейчас тебе нужно создать {MIN_BOTS - len(self.bots)} бота(-ов) и добавить их токены в настройки плагина, нажав на кнопку <code>Добавить Telegram бота</code>.\n\n" \
                           f"Для удобства пропиши в названия ботов невидимые символы, а аватарки сделай одинаковыми."
        elif not self.settings.get('chat_id'):
            instructions = f"Сейчас тебе нужно создать группу, добавить в нее всех созданных ботов (в том числе основного (этого) бота) и назначить их администраторами со всеми правами.\n\n" \
                           f"Далее тебе нужно перевести группу в режим тем. Для этого открой настройки группы и включи переключатель <code>Темы</code>.\n\n" \
                           f"После всего введи команду /setup_sync_chat."
        elif not self.ready:
            instructions = f"Странно, вроде все правильно, но что-то не так... Попробуй перезапустить бота командой /restart :)"

        stats = f"""<b><i>Группа для FunPay чатов:</i></b> {chat_name or '<code>Не установлен.</code>'}\n
<b><i>Готов к работе:</i></b> <code>{"✅ Да." if self.ready else "❌ Нет."}</code>\n\n
<b><u>Что сейчас делать?</u></b>
{instructions}"""
        self.tgbot.edit_message_text(stats, c.message.chat.id, c.message.id,
                                     reply_markup=plugin_settings_kb(self, offset), disable_web_page_preview=True)

    def act_add_sync_bot(self, c: telebot.types.CallbackQuery):
        split = c.data.split(":")
        offset = int(split[1])
        if len(self.bots) >= 10:
            self.tgbot.answer_callback_query(c.id, "❌ Достигнуто максимальное кол-во ботов.", show_alert=True)
            return
        result = self.tgbot.send_message(c.message.chat.id, "Отправь мне токен Telegram бота.",
                                         reply_markup=skb.CLEAR_STATE_BTN())
        self.tg.set_state(c.message.chat.id, result.id, c.from_user.id, ADD_SYNC_BOT, {"offset": offset})
        self.tgbot.answer_callback_query(c.id)

    def add_sync_bot(self, m: telebot.types.Message):
        offset = self.tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        self.tg.clear_state(m.chat.id, m.from_user.id, True)
        token = m.text
        bot = telebot.TeleBot(token, parse_mode="HTML", allow_sending_without_reply=True)
        try:
            data = bot.get_me()
            username, bot_id = data.username, data.id
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при получении данных Telegram бота с токеном $YELLOW{token}$RESET.")
            logger.debug("TRACEBACK", exc_info=True)
            self.tgbot.reply_to(m, "❌ Произошла ошибка при получении данных о боте.", reply_markup=back_keyboard(offset))
            return

        self.bots.append(bot)
        self.save_bots()
        if not self.current_bot:
            self.current_bot = self.bots[0]
        if not self.ready and len(self.bots) >= MIN_BOTS and self.settings.get("chat_id"):
            self.ready = True
        self.tgbot.reply_to(m, f"✅ Telegram бот @{username} добавлен!", reply_markup=back_keyboard(offset))
        return

    def delete_sync_bot(self, c: telebot.types.CallbackQuery):
        split = c.data.split(":")
        index, offset = int(split[1]), int(split[2])
        if len(self.bots) < index + 1:
            self.tgbot.edit_message_text(f"❌ Бот с индексом {index} не найден.", c.message.chat.id, c.message.id,
                                         reply_markup=back_keyboard(offset))
            self.tgbot.answer_callback_query(c.id)
            return

        self.bots.pop(index)
        self.current_bot = self.bots[0] if self.bots else None
        if not self.current_bot or len(self.bots) < MIN_BOTS:
            self.ready = False
        self.save_bots()
        c.data = f"{CBT.PLUGIN_SETTINGS}:{UUID}:{offset}"
        self.open_settings_menu(c)

    def setup_sync_chat(self, m: telebot.types.Message):
        if self.settings.get("chat_id"):
            self.tgbot.reply_to(m, "Ты уверен, что хочешь изменить группу для синхронизации Funpay чатов?\n\n"
                                   "Пары <code>Telegram топик - FunPay чат</code> сбросятся!",
                                reply_markup=setup_chat_keyboard())
            return
        if not m.chat.is_forum:
            self.tgbot.reply_to(m, "❌ Чат должен быть перевед в режим тем!")
            return
        self.settings["chat_id"] = m.chat.id
        self.save_settings()
        self.threads = {}
        self.save_threads()
        if not self.ready and self.current_bot and len(self.bots) >= MIN_BOTS:
            self.ready = True
        self.tgbot.send_message(m.chat.id, "✅ Группа для синхронизации FunPay чатов установлена!")

    def confirm_setup_sync_chat(self, c: telebot.types.CallbackQuery):
        if not c.message.chat.is_forum:
            self.tgbot.edit_message_text("❌ Чат должен быть перевед в режим тем!",
                                         c.message.chat.id, c.message.id)
            self.tgbot.answer_callback_query(c.id)
            return
        self.settings["chat_id"] = c.message.chat.id
        self.save_settings()
        self.threads = {}
        self.save_threads()
        if not self.ready and self.current_bot and len(self.bots) >= MIN_BOTS:
            self.ready = True
        self.tgbot.edit_message_text("✅ Группа для синхронизации FunPay чатов установлена!",
                                     c.message.chat.id, c.message.id)

    def delete_sync_chat(self, m: telebot.types.Message):
        if not self.settings.get('chat_id'):
            self.tgbot.reply_to(m, "❌ Группа для синхронизации FunPay чатов итак не привязана!")
            return
        self.tgbot.reply_to(m, "Ты уверен, что хочешь отвязать группу для синхронизации FunPay чатов?\n\n"
                               "Пары <code>Telegram топик - FunPay чат</code> сбросятся!",
                            reply_markup=delete_chat_keyboard())

    def confirm_delete_sync_chat(self, c: telebot.types.CallbackQuery):
        self.settings["chat_id"] = None
        self.save_settings()
        self.threads = {}
        self.save_threads()
        self.ready = False
        self.tgbot.edit_message_text("✅ Группа для синхронизации FunPay чатов отвязана.",
                                     c.message.chat.id, c.message.id)

    def sync_chats(self, m: telebot.types.Message):
        if not self.current_bot:
            return
        if self.sync_chats_running:
            self.tgbot.reply_to(m, "❌ Синхронизация чатов уже запущена! Дождитесь окончания процесса или перезапустите <i>FPC</i>.")
            return

        self.sync_chats_running = True
        chats = self.cardinal.account.get_chats(update=True)
        for chat in chats:
            obj = chats[chat]
            if str(chat) not in self.threads:
                self.new_synced_chat(obj.id, obj.name)
            time.sleep(1)
        self.sync_chats_running = False

    def send_message(self, m: telebot.types.Message):
        split = m.reply_to_message.forum_topic_created.name.split()
        chat_name, chat_id = split[0], split[1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        result = self.cardinal.send_message(chat_id, f"{SPECIAL_SYMBOL}{m.text}", chat_name, watermark=False)
        if not result:
            self.current_bot.reply_to(m, _("msg_sending_error", chat_id, chat_name),
                                      message_thread_id=m.message_thread_id)
            self.swap_curr_bot()

    def watch(self, m: telebot.types.Message):
        if not m.chat.id == self.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            self.tgbot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        try:
            chat = self.cardinal.account.get_chat(chat_id)
            looking_text = chat.looking_text
            looking_link = chat.looking_link
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при получении данных чата $YELLOW{username} (CID: {chat_id})$RESET.")
            logger.debug("TRACEBACK", exc_info=True)
            self.current_bot.reply_to(m, f"❌ Произошла ошибка при получении данных чата с <a href=\"https://funpay.com/chat/?node={chat_id}\">{username}</a>")
            self.swap_curr_bot()
            return

        if looking_text and looking_link:
            text = f"<b><i>Смотрит: </i></b> <a href=\"{looking_link}\">{looking_text}</a>"
        else:
            text = f"<b>Пользователь <code>{username}</code> ничего не смотрит.</b>"
        self.current_bot.reply_to(m, text)
        self.swap_curr_bot()

    def watch_handler(self, m: telebot.types.Message):
        Thread(target=self.watch, args=(m,)).start()

    def history(self, m: telebot.types.Message):
        if not m.chat.id == self.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            self.tgbot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        try:
            history = self.cardinal.account.get_chat_history(chat_id, interlocutor_username=username)
            if not history:
                self.tgbot.reply_to(m, f"❌ История чата с <a href=\"https://funpay.com/chat/?node={chat_id}\">{username}</a> пуста.")
                return
            history = history[-25:]
        except:
            logger.error(f"{LOGGER_PREFIX} Произошла ошибка при получении истории чата $YELLOW{username} (CID: {chat_id})$RESET.")
            logger.debug("TRACEBACK", exc_info=True)
            self.tgbot.reply_to(m, f"❌ Произошла ошибка при получении истории чата с <a href=\"https://funpay.com/chat/?node={chat_id}\">{username}</a>")
            self.swap_curr_bot()
            return

        text = ""
        last_message_author_id = -1
        last_by_bot = False
        for i in history:
            message_text = str(i)
            if i.author_id == last_message_author_id and i.by_bot == last_by_bot:
                author = ""
            elif i.author_id == self.cardinal.account.id:
                author = f"<i><b>🤖 {_('you')} (<i>FPC</i>):</b></i> " if i.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
            elif i.author_id == 0:
                author = f"<i><b>🔵 {i.author}: </b></i>"
            elif i.badge:
                author = f"<i><b>🆘 {i.author} ({_('support')}): </b></i>"
            elif i.author == i.chat_name:
                author = f"<i><b>👤 {i.author}: </b></i>"
            else:
                author = f"<i><b>🆘 {i.author} {_('support')}: </b></i>"

            if not i.text:
                msg_text = f"<a href=\"{message_text}\">{_('photo')}</a>"
            elif i.author_id == 0:
                msg_text = f"<b><i>{utils.escape(message_text)}</i></b>"
            else:
                msg_text = utils.escape(message_text)

            text += f"{author}{msg_text}\n\n"
            last_message_author_id = i.author_id
            last_by_bot = i.by_bot

        self.tgbot.reply_to(m, text)

    def history_handler(self, m: telebot.types.Message):
        Thread(target=self.history, args=(m,)).start()

    def send_funpay_image(self, m: telebot.types.Message):
        if not self.settings["chat_id"] or m.chat.id != self.settings["chat_id"] or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            return

        photo = m.photo[-1]
        if photo.file_size >= 20971520:
            self.tgbot.reply_to(m, "❌ Размер файла не должен превышать 20МБ.")
            return

        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        try:
            file_info = self.tgbot.get_file(photo.file_id)
            file = self.tgbot.download_file(file_info.file_path)
            result = self.cardinal.account.send_image(chat_id, file, username, True,
                                                      update_last_saved_message=self.cardinal.old_mode_enabled)
            if not result:
                self.current_bot.reply_to(m, _("msg_sending_error", chat_id, username),
                                          message_thread_id=m.message_thread_id)
                return
        except:
            self.current_bot.reply_to(m, _("msg_sending_error", chat_id, username),
                                      message_thread_id=m.message_thread_id)
            return


def main(c: Cardinal):
    cs = ChatSync(c)
    cs.load()
    cs.replace_handler()
    cs.bind_tg_handlers()


BIND_TO_PRE_INIT = [main]
BIND_TO_DELETE = None
