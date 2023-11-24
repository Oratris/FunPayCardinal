from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cardinal import Cardinal
from FunPayAPI.account import Account

import telebot
from tg_bot import utils

NAME = "Cookie Changer Plugin"
VERSION = "0.0.2"
DESCRIPTION = "Чтобы сменить куки, используй команду cookie_change (твой golden_key)."
CREDITS = "@kiwy1"
UUID = "5d9a1cd0-10e7-41b6-a3f3-d682cf143bc8"
SETTINGS_PAGE = False

def init_commands(cardinal: Cardinal, *args):
    if not cardinal.telegram:
        return
    tg = cardinal.telegram
    bot = tg.bot
    acc = cardinal.account

    def change_cookie(m: telebot.types.Message):
        if len(m.text.split(" ")) == 2:
            acc.golden_key = m.text.split(" ")[1]
            cardinal.MAIN_CFG.set("FunPay", "golden_key", m.text.split(" ")[1])
            cardinal.save_config(cardinal.MAIN_CFG, "configs/_main.cfg")
            acc.get(True)
            bot.send_message(m.chat.id, "✅ Успешно изменено перезапустите бота.")
        else:
            bot.send_message(m.chat.id, "Команда введена не правильно! /change_cookie [golden_key]")

    tg.msg_handler(change_cookie, commands=["change_cookie"])
    cardinal.add_telegram_commands(UUID, [
        ("change_cookie", "меняет golden_key куки", True)
    ])

BIND_TO_PRE_INIT = [init_commands]
BIND_TO_DELETE = None