from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cardinal import Cardinal

from telebot.types import Message
from tg_bot import utils
import traceback
from io import StringIO
import sys


NAME = "Exec Plugin"
VERSION = "0.0.2"
DESCRIPTION = "Плагин, выполняющий произвольный Python код, переданный через команду /exec."
CREDITS = "@woopertail"
UUID = "cd6f4b98-e9ba-4c38-b3e8-0cffd6420cf0"
SETTINGS_PAGE = False


def main(cardinal: Cardinal, *args):
    if not cardinal.telegram:
        return

    tg = cardinal.telegram
    bot = tg.bot

    cardinal.add_telegram_commands(UUID, [
        ("exec", "выполняет произвольный Python код.", False)
    ])

    def run(message: Message):
        crd = cardinal
        command = message.text.split()[0]
        code = message.text.replace(command, "", 1)
        if code:
            try:
                output = sys.stdout = StringIO()
                exec(code)
                val = output.getvalue()
                if val.strip():
                    bot.send_message(message.chat.id, output.getvalue())
            except:
                bot.send_message(message.chat.id, utils.escape(traceback.format_exc()))

    tg.msg_handler(run, commands=["exec"])


def on_delete(c, call):
    ...


BIND_TO_PRE_INIT = [main]
BIND_TO_DELETE = on_delete
