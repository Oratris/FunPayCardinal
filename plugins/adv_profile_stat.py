from __future__ import annotations
import json
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cardinal import Cardinal
from FunPayAPI.account import Account
from FunPayAPI.types import OrderStatuses, MessageTypes
from FunPayAPI.updater.events import *
from FunPayAPI.common.utils import RegularExpressions
from os.path import exists
import tg_bot.CBT
from bs4 import BeautifulSoup as bs
import telebot
import time


NAME = "Advanced Profile Stat"
VERSION = "0.0.4"
DESCRIPTION = "Данный плагин меняет команду /profile,\nблагодаря которому можно получить более подробную статистику аккаунта. По вопросам @zmka6"
CREDITS = "@kiwy1"
UUID = "6d607fb3-bfa9-43e6-acc2-2bfe05f86abe"
SETTINGS_PAGE = False

ADV_PROFILE_CB = "adv_profile_1"

ORDER_CONFIRMED = {}


def generate_adv_profile(account: Account) -> str:
    sales = {"day": 0, "week": 0, "month": 0, "all": 0}
    salesPrice = {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0}
    refunds = {"day": 0, "week": 0, "month": 0, "all": 0}
    refundsPrice = {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0}
    canWithdraw = {"now": 0.0, "hour": 0.0, "day": 0.0, "2day": 0.0}

    account.get()

    for order in ORDER_CONFIRMED.copy():
        if time.time() - ORDER_CONFIRMED[order]["time"] > 172800:
            del ORDER_CONFIRMED[order]
            continue
        if time.time() - ORDER_CONFIRMED[order]["time"] > 169200:
            canWithdraw["hour"] += ORDER_CONFIRMED[order]["price"]
        elif time.time() - ORDER_CONFIRMED[order]["time"] > 86400:
            canWithdraw["day"] += ORDER_CONFIRMED[order]["price"]
        else:
            canWithdraw["2day"] += ORDER_CONFIRMED[order]["price"]

    randomLotPageLink = bs(account.method("get", "https://funpay.com/lots/693/", {}, {}).text, "html.parser").find("a", {"class": "tc-item"})["href"]
    randomLotPageParse = bs(account.method("get", randomLotPageLink, {}, {}).text, "html.parser")

    canWithdraw["now"] = randomLotPageParse.find("select", {"class": "form-control input-lg selectpicker"})["data-balance-rub"]
    if account.currency == "$":
        canWithdraw["now"] = randomLotPageParse.find("select", {"class": "form-control input-lg selectpicker"})["data-balance-usd"]
    elif account.currency == "€":
        canWithdraw["now"] = randomLotPageParse.find("select", {"class": "form-control input-lg selectpicker"})["data-balance-eur"]

    next_order_id, all_sales = account.get_sales()

    while next_order_id != None:
        time.sleep(1)
        next_order_id, new_sales = account.get_sales(start_from=next_order_id)
        all_sales += new_sales

    for sale in all_sales:
        if sale.status == OrderStatuses.REFUNDED:
            refunds["all"] += 1
            refundsPrice["all"] += sale.price
        else:
            sales["all"] += 1
            salesPrice["all"] += sale.price
        date = bs(sale.html, "html.parser").find("div", {"class": "tc-date-left"}).text

        if "час" in date or "мин" in date or "сек" in date or "годин" in date or "хвилин" in date or "hour" in date or "min" in date or "sec" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["day"] += 1
                refunds["week"] += 1
                refunds["month"] += 1
                refundsPrice["day"] += sale.price
                refundsPrice["week"] += sale.price
                refundsPrice["month"] += sale.price
            else:
                sales["day"] += 1
                sales["week"] += 1
                sales["month"] += 1
                salesPrice["day"] += sale.price
                salesPrice["week"] += sale.price
                salesPrice["month"] += sale.price
        elif "день" in date or "дня" in date or "дней" in date or "дні" in date or "day" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["week"] += 1
                refunds["month"] += 1
                refundsPrice["week"] += sale.price
                refundsPrice["month"] += sale.price
            else:
                sales["week"] += 1
                sales["month"] += 1
                salesPrice["week"] += sale.price
                salesPrice["month"] += sale.price
        elif "недел" in date or "тижд" in date or "week" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["month"] += 1
                refundsPrice["month"] += sale.price
            else:
                sales["month"] += 1
                salesPrice["month"] += sale.price

    return f"""Статистика аккаунта <b><i>{account.username}</i></b>

<b>ID:</b> <code>{account.id}</code>
<b>Баланс:</b> <code>{account.balance} {account.currency}</code>
<b>Незавершенных заказов:</b> <code>{account.active_sales}</code>

<b>Доступно для вывода</b>
<b>Сейчас:</b> <code>{canWithdraw["now"].split('.')[0]} {account.currency}</code>
<b>Через час:</b> <code>+{"{:.1f}".format(canWithdraw["hour"])} {account.currency}</code>
<b>Через день:</b> <code>+{"{:.1f}".format(canWithdraw["day"] + canWithdraw["hour"])} {account.currency}</code>
<b>Через 2 дня:</b> <code>+{"{:.1f}".format(canWithdraw["2day"] + canWithdraw["hour"] + canWithdraw["day"])} {account.currency}</code>

<b>Товаров продано</b>
<b>За день:</b> <code>{sales["day"]} ({"{:.1f}".format(salesPrice["day"])} {account.currency})</code>
<b>За неделю:</b> <code>{sales["week"]} ({"{:.1f}".format(salesPrice["week"])} {account.currency})</code>
<b>За месяц:</b> <code>{sales["month"]} ({"{:.1f}".format(salesPrice["month"])} {account.currency})</code>
<b>За всё время:</b> <code>{sales["all"]} ({"{:.1f}".format(salesPrice["all"])} {account.currency})</code>

<b>Товаров возвращено</b>
<b>За день:</b> <code>{refunds["day"]} ({"{:.1f}".format(refundsPrice["day"])} {account.currency})</code>
<b>За неделю:</b> <code>{refunds["week"]} ({"{:.1f}".format(refundsPrice["week"])} {account.currency})</code>
<b>За месяц:</b> <code>{refunds["month"]} ({"{:.1f}".format(refundsPrice["month"])} {account.currency})</code>
<b>За всё время:</b> <code>{refunds["all"]} ({"{:.1f}".format(refundsPrice["all"])} {account.currency})</code>

<i>Обновлено:</i>  <code>{time.strftime('%H:%M:%S', time.localtime(account.last_update))}</code>"""


def init_commands(cardinal: Cardinal, *args):
    if not cardinal.telegram:
        return
    tg = cardinal.telegram
    bot = tg.bot
    acc = cardinal.account

    if exists("storage/plugins/advProfileStat.json"):
        with open("storage/plugins/advProfileStat.json", "r", encoding="utf-8") as f:
            global ORDER_CONFIRMED
            ORDER_CONFIRMED = json.loads(f.read())

    def profile(call: telebot.types.CallbackQuery):
        new_msg = bot.send_message(call.message.chat.id, "Обновляю статистику аккаунта (это может занять некоторое время)...")

        try:
            bot.edit_message_text(generate_adv_profile(acc), call.message.chat.id, call.message.id, reply_markup=telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=ADV_PROFILE_CB)))
        except:
            bot.edit_message_text("❌ Не удалось обновить статистику аккаунта.", new_msg.chat.id, new_msg.id)
            bot.logger.debug("TRACEBACK", exc_info=True)
            bot.answer_callback_query(call.id)
            return

        bot.delete_message(new_msg.chat.id, new_msg.id)

    tg_bot.static_keyboards.UPDATE_PROFILE_BTN = telebot.types.InlineKeyboardMarkup().row(telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=tg_bot.CBT.UPDATE_PROFILE), telebot.types.InlineKeyboardButton("▶️ Еще", callback_data=ADV_PROFILE_CB))
    tg.cbq_handler(profile, lambda c: c.data == ADV_PROFILE_CB)


def message_hook(cardinal: Cardinal, event: NewMessageEvent):
    if event.message.type not in [MessageTypes.ORDER_CONFIRMED, MessageTypes.ORDER_CONFIRMED_BY_ADMIN, MessageTypes.ORDER_REOPENED, MessageTypes.REFUND]:
        return
    if event.message.type not in [MessageTypes.ORDER_REOPENED, MessageTypes.REFUND] and bs(event.message.html, "html.parser").find("a").text == cardinal.account.username:
        return

    id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]

    if event.message.type in [MessageTypes.ORDER_REOPENED, MessageTypes.REFUND]:
        if id in ORDER_CONFIRMED:
            del ORDER_CONFIRMED[id]
    else:
        ORDER_CONFIRMED[id] = {"time": time.time(), "price": cardinal.account.get_order(id).sum}
        with open("storage/plugins/advProfileStat.json", "w", encoding="UTF-8") as f:
            f.write(json.dumps(ORDER_CONFIRMED, indent=4, ensure_ascii=False))


BIND_TO_PRE_INIT = [init_commands]
BIND_TO_NEW_MESSAGE = [message_hook]
BIND_TO_DELETE = None
