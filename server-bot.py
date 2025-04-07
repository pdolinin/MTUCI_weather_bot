import re
import requests
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='weather_bot.log'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "YOUR_TG_TOKEN"
YANDEX_WEATHER_API_KEY = "YOUR_YANDEX_WEATHER_TOKEN"

WEATHER_API_URL = "https://api.weather.yandex.ru/v2/forecast"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
# Базовые URL API


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        "Привет! Я бот для прогноза погоды с использованием Яндекс.Погоды.\n"
        "Используйте команду /weather с параметрами:\n"
        "/weather -location <город> [-date <дата> | -from <дата> -to <дата>] [-full]\n\n"
        "Примеры:\n"
        "/weather -location Москва -date завтра\n"
        "/weather -location Санкт-Петербург -from 2023-12-25 -to 2023-12-31 -=-full"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    logger.info(f"User {update.effective_user.id} requested help")
    help_text = (
        "📌 Использование:\n"
        "/weather --location <город> [--date <дата> | --from <дата> --to <дата>] [--full]\n\n"
        "📌 Параметры:\n"
        "--location: город для прогноза (обязательный)\n"
        "--date: дата (сегодня, завтра или YYYY-MM-DD)\n"
        "--from и --to: начальная и конечная даты периода\n"
        "--full: подробный прогноз (по умолчанию краткий)\n\n"
        "📌 Примеры:\n"
        "/weather --location Москва --date завтра\n"
        "/weather -l Казань -t 2023-12-31 -f\n"
        "/weather --location Сочи --from 2023-12-25 --to 2023-12-31 --full"
    )
    await update.message.reply_text(help_text)


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /weather с параметрами"""
    try:
        logger.info(f"Weather command from {update.effective_user.id}: {update.message.text}")
        text = update.message.text

        # Парсинг параметров с помощью регулярных выражений
        location_match = re.search(r'-(?:l|location)\s+([^-]+)', text) or re.search(r'-location\s+([^-]+)', text)
        date_match = re.search(r'-(?:t|date)\s+(\S+)', text) or re.search(r'-date\s+(\S+)', text)
        from_match = re.search(r'-from\s+(\S+)', text)
        to_match = re.search(r'-to\s+(\S+)', text)
        full_match = re.search(r'-(?:f|full)', text) or re.search(r'-full', text)

        location = location_match.group(1).strip() if location_match else None
        date = date_match.group(1) if date_match else None
        date_from = from_match.group(1) if from_match else None
        date_to = to_match.group(1) if to_match else None
        full = bool(full_match)

        if not location:
            await update.message.reply_text("Пожалуйста, укажите город. Например: /weather --location Москва")
            return

        if date_from and date_to:
            # Запрос на период
            await get_weather_period(update, context, location, date_from, date_to, full)
        elif date:
            # Запрос на конкретную дату
            await get_weather(update, context, location, date, full)
        else:
            # Запрос без даты - по умолчанию на сегодня
            await get_weather(update, context, location, "сегодня", full)

    except Exception as e:
        logger.error(f"Error in weather_command: {str(e)}")
        await update.message.reply_text(
            "Произошла ошибка при обработке команды. Проверьте параметры и попробуйте еще раз.")


async def get_city_coordinates(city: str):
    """Получение координат через Nominatim API"""
    try:
        params = {
            "city": city,
            "format": "json",
            "limit": 1,
            "accept-language": "ru"
        }
        headers = {
            "User-Agent": "TelegramWeatherBot/1.0"
        }

        logger.info(f"Geocoding request for city: {city}")
        response = requests.get(GEOCODER_URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        if not data:
            logger.warning(f"City not found: {city}")
            return None

        logger.info(f"Found coordinates for {city}: {data[0]['lat']}, {data[0]['lon']}")
        return {
            'lat': float(data[0]['lat']),
            'lon': float(data[0]['lon'])
        }
    except Exception as e:
        logger.error(f"Geocoding error for {city}: {str(e)}")
        return None


async def get_weather_data(coords: dict, days: int = 7):
    """Получение данных о погоде от Яндекс API"""
    try:
        headers = {
            "X-Yandex-API-Key": YANDEX_WEATHER_API_KEY
        }

        params = {
            "lat": coords['lat'],
            "lon": coords['lon'],
            "lang": "ru_RU",
            "limit": days,
            "hours": False,
            "extra": True
        }

        logger.info(f"Requesting weather data for coordinates: {coords}")
        response = requests.get(WEATHER_API_URL, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Weather API error: {str(e)}")
        return None


async def get_weather(update: Update, context: ContextTypes.DEFAULT_TYPE, city: str, date: str, full: bool):
    """Получение и отправка прогноза погоды на конкретную дату"""
    try:
        logger.info(f"Weather request: city={city}, date={date}, full={full}")

        # Получаем координаты города
        coords = await get_city_coordinates(city)
        if not coords:
            await update.message.reply_text("Город не найден. Попробуйте уточнить название.")
            return

        # Получаем данные о погоде
        weather_data = await get_weather_data(coords)
        if not weather_data:
            await update.message.reply_text("Не удалось получить данные о погоде. Попробуйте позже.")
            return

        # Определяем целевую дату
        if date.lower() == 'сегодня':
            target_date = datetime.now().date()
        elif date.lower() == 'завтра':
            target_date = (datetime.now() + timedelta(days=1)).date()
        else:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                await update.message.reply_text("Неверный формат даты. Используйте ГГГГ-ММ-ДД, 'сегодня' или 'завтра'.")
                return

        # Ищем прогноз на нужную дату
        forecast = None
        for day in weather_data['forecasts']:
            if datetime.strptime(day['date'], "%Y-%m-%d").date() == target_date:
                forecast = day
                break

        if not forecast:
            await update.message.reply_text(f"Прогноз на {date} не найден.")
            return

        if full:
            message = format_detailed_forecast(forecast, city, date)
        else:
            message = format_short_forecast(forecast, city, date)

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in get_weather: {str(e)}")
        await update.message.reply_text("Произошла ошибка при получении прогноза погоды. Попробуйте позже.")


async def get_weather_period(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             city: str, date_from: str, date_to: str, full: bool):
    """Получение и отправка прогноза погоды на период"""
    try:
        logger.info(f"Period weather request: city={city}, from={date_from}, to={date_to}, full={full}")

        # Получаем координаты города
        coords = await get_city_coordinates(city)
        if not coords:
            await update.message.reply_text("Город не найден. Попробуйте уточнить название.")
            return

        # Получаем данные о погоде
        weather_data = await get_weather_data(coords)
        if not weather_data:
            await update.message.reply_text("Не удалось получить данные о погоде. Попробуйте позже.")
            return

        # Парсим даты
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            to_date = datetime.strptime(date_to, "%Y-%m-%d").date()

            if from_date > to_date:
                await update.message.reply_text("Начальная дата должна быть раньше конечной.")
                return

            if (to_date - from_date).days > 30:
                await update.message.reply_text("Максимальный период - 30 дней.")
                return
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Используйте ГГГГ-ММ-ДД.")
            return

        # Фильтруем прогнозы по датам
        forecasts = []
        for day in weather_data['forecasts']:
            day_date = datetime.strptime(day['date'], "%Y-%m-%d").date()
            if from_date <= day_date <= to_date:
                forecasts.append(day)

        if not forecasts:
            await update.message.reply_text(f"Нет данных за указанный период {date_from} - {date_to}.")
            return

        if full:
            message = format_detailed_period_forecast(forecasts, city, date_from, date_to)
        else:
            message = format_short_period_forecast(forecasts, city, date_from, date_to)

        # Разбиваем сообщение на части, если оно слишком длинное
        max_length = 4000  # Максимальная длина сообщения в Telegram
        if len(message) > max_length:
            parts = [message[i:i + max_length] for i in range(0, len(message), max_length)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in get_weather_period: {str(e)}")
        await update.message.reply_text("Произошла ошибка при получении прогноза погоды. Попробуйте позже.")


def format_short_forecast(forecast, city, date):
    """Форматирование краткого прогноза на одну дату"""
    day = forecast['parts']['day']
    night = forecast['parts']['night']

    return (
        f"🌤 Погода в {city} на {date}:\n"
        f"🌞 Днем: {day['temp_avg']}°C (ощущается как {day['feels_like']}°C)\n"
        f"☁ {translate_condition(day['condition'])}, 💧{day['humidity']}%, 🌬 {day['wind_speed']} м/с\n"
        f"🌙 Ночью: {night['temp_avg']}°C (ощущается как {night['feels_like']}°C)\n"
        f"☁ {translate_condition(night['condition'])}, 💧{night['humidity']}%, 🌬 {night['wind_speed']} м/с"
    )


def format_detailed_forecast(forecast, city, date):
    """Форматирование подробного прогноза на одну дату"""
    day = forecast['parts']['day']
    night = forecast['parts']['night']

    message = [
        f"📊 Подробный прогноз в {city} на {date}:\n",
        f"\n🌞 Дневной прогноз:",
        f"🌡 Температура: {day['temp_avg']}°C (мин {day['temp_min']}°C, макс {day['temp_max']}°C)",
        f"Ощущается как: {day['feels_like']}°C",
        f"☁ Состояние: {translate_condition(day['condition'])}",
        f"🌬 Ветер: {day['wind_speed']} м/с, направление: {get_wind_direction(day['wind_dir'])}",
        f"💧 Влажность: {day['humidity']}%",
        f"📊 Давление: {day['pressure_mm']} мм рт. ст.",
        f"🌧 Вероятность осадков: {day['prec_prob']}%",
        f"\n🌙 Ночной прогноз:",
        f"🌡 Температура: {night['temp_avg']}°C (мин {night['temp_min']}°C, макс {night['temp_max']}°C)",
        f"Ощущается как: {night['feels_like']}°C",
        f"☁ Состояние: {translate_condition(night['condition'])}",
        f"🌬 Ветер: {night['wind_speed']} м/с, направление: {get_wind_direction(night['wind_dir'])}",
        f"💧 Влажность: {night['humidity']}%",
        f"📊 Давление: {night['pressure_mm']} мм рт. ст.",
        f"🌧 Вероятность осадков: {night['prec_prob']}%"
    ]

    return "\n".join(message)


def format_short_period_forecast(forecasts, city, date_from, date_to):
    """Форматирование краткого прогноза на период"""
    message = [f"🌤 Погода в {city} с {date_from} по {date_to}:\n"]

    for forecast in forecasts:
        date = forecast['date']
        day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        day = forecast['parts']['day']

        message.append(
            f"\n📅 {date} ({day_name}):"
            f"\n🌞 Днем: {day['temp_avg']}°C, ☁ {translate_condition(day['condition'])}"
            f"\n🌙 Ночью: {forecast['parts']['night']['temp_avg']}°C"
        )

    return "\n".join(message)


def format_detailed_period_forecast(forecasts, city, date_from, date_to):
    """Форматирование подробного прогноза на период"""
    message = [f"📊 Подробный прогноз в {city} с {date_from} по {date_to}:\n"]

    for forecast in forecasts:
        date = forecast['date']
        day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        day = forecast['parts']['day']
        night = forecast['parts']['night']

        message.append(
            f"\n📅 {date} ({day_name}):"
            f"\n🌞 Дневной прогноз:"
            f"\n🌡 Температура: {day['temp_avg']}°C (мин {day['temp_min']}°C, макс {day['temp_max']}°C)"
            f"\nОщущается как: {day['feels_like']}°C"
            f"\n☁ Состояние: {translate_condition(day['condition'])}"
            f"\n🌬 Ветер: {day['wind_speed']} м/с, направление: {get_wind_direction(day['wind_dir'])}"
            f"\n💧 Влажность: {day['humidity']}%"
            f"\n📊 Давление: {day['pressure_mm']} мм рт. ст."
            f"\n🌧 Вероятность осадков: {day['prec_prob']}%"
            f"\n\n🌙 Ночной прогноз:"
            f"\n🌡 Температура: {night['temp_avg']}°C (мин {night['temp_min']}°C, макс {night['temp_max']}°C)"
            f"\nОщущается как: {night['feels_like']}°C"
            f"\n☁ Состояние: {translate_condition(night['condition'])}"
            f"\n🌬 Ветер: {night['wind_speed']} м/с, направление: {get_wind_direction(night['wind_dir'])}"
            f"\n💧 Влажность: {night['humidity']}%"
            f"\n📊 Давление: {night['pressure_mm']} мм рт. ст."
            f"\n🌧 Вероятность осадков: {night['prec_prob']}%"
            f"\n{'-' * 30}"
        )

    return "\n".join(message)


def translate_condition(condition):
    """Перевод состояния погоды на русский"""
    translations = {
        "clear": "ясно",
        "partly-cloudy": "малооблачно",
        "cloudy": "облачно с прояснениями",
        "overcast": "пасмурно",
        "light-rain": "небольшой дождь",
        "rain": "дождь",
        "heavy-rain": "сильный дождь",
        "showers": "ливень",
        "wet-snow": "дождь со снегом",
        "light-snow": "небольшой снег",
        "snow": "снег",
        "snow-showers": "снегопад",
        "hail": "град",
        "thunderstorm": "гроза",
        "thunderstorm-with-rain": "дождь с грозой",
        "thunderstorm-with-hail": "гроза с градом"
    }
    return translations.get(condition, condition)


def get_wind_direction(wind_dir):
    """Перевод направления ветра из буквенного обозначения в текст"""
    directions = {
        "nw": "северо-западный",
        "n": "северный",
        "ne": "северо-восточный",
        "e": "восточный",
        "se": "юго-восточный",
        "s": "южный",
        "sw": "юго-западный",
        "w": "западный",
        "c": "штиль"
    }
    return directions.get(wind_dir.lower(), wind_dir)


def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))

    # Запуск бота
    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()