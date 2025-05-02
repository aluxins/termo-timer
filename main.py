import asyncio
import gc
from lib import thermostat, tm1637, display, file_storage
from os import statvfs, uname
from time import ticks_ms
from micropython import mem_info
from machine import Pin, PWM, ADC, unique_id, freq

# Таблица зависимости напряжения на входе АЦП от температуры NTC.
# NTC 10k b3950.
temperature_table: dict = {
    0: 2.41018,
    5: 2.26006,
    10: 2.10318,
    15: 1.94281,
    20: 1.78225,
    25: 1.62462,
    30: 1.47259,
    35: 1.36555,
    40: 1.22584,
    45: 1.06858,
    50: 0.95452
}

# Настройки по умолчанию.
default_settings = {
    "CONST_TIMER": 10 * 60, # Время нагрева.
    "CONST_TEMPERATURE": 30, # Температура нагрева.
    "CONST_LOGO": "apkau sd-1", # Стартовая надпись на индикаторе.
    "CONST_INDICATOR_BRIGHTNESS": 1, # Яркость индикатора.
    "CONST_HYSTERESIS": 1.5,  # Температурный гистерезис.
    "CONST_PURGING_HEATER": 2 * 60,  # Время продува нагревателя перед отключением.
    "CONST_TIMER_MIN_VALUE": 10 * 60,  # Минимальное время таймера.
    "CONST_TIMER_MAX_VALUE": 10 * 60 * 60,  # Максимальное время таймера.
    "CONST_TIMER_STEP": 10 * 60,  # Шаг установки таймера.
    "CONST_TEMPERATURE_MIN_VALUE": 15,  # Минимальная температура.
    "CONST_TEMPERATURE_MAX_VALUE": 45,  # Максимальная температура.
    "CONST_TEMPERATURE_STEP": 1  # Шаг установки температуры.
}
# Инициализация настроек.
config = file_storage.FileStorage(default_settings, 'settings.json')

# Глобальные переменные.
time_left = config.values['CONST_TIMER']  # Состояние таймера.
temperature = config.values['CONST_TEMPERATURE']  # Температура стабилизации.
heating = 0  # Состояние нагрева.
current_t = 0  # Текущая температура NTC.
settings_step = 0  # Шаг меню установок.
display_show = 'starting'  # Тип отображаемой информации, start - начальный экран.
display_value = ''  # Отображаемое значение на дисплее.
display_time_fps = 0.1 # Частота обновления дисплея каждые [0.01 ... 0.5] сек.
settings_time_out = 0  # Количество миганий дисплея до возврата в начало.
start = False  # Состояние основного процесса.

"""Конфигурация портов"""

# Дисплей.
dp = display.Display(
    tm1637.TM1637(clk=Pin(0), dio=Pin(1)),
    2, display_time_fps)

# ШИМ для светодиодного индикатора.
pwm = PWM(Pin(25))
# Частота ШИМ.
pwm.freq(1000)
pwm.duty_u16(0)

# Кнопки.
list_buttons = [
    Pin(12, Pin.IN, Pin.PULL_UP), # start/stop
    Pin(13, Pin.IN, Pin.PULL_UP), # set
    Pin(14, Pin.IN, Pin.PULL_UP), # down
    Pin(15, Pin.IN, Pin.PULL_UP) # up
]

# Релейные выходы.
list_relays = [
    Pin(10, Pin.OUT), # heater
    Pin(11, Pin.OUT) # fan
]

# Вход ADC для NTC-датчика.
sensor_voltage = ADC(28)

# Термостат.
thermo = thermostat.Thermostat(temperature_table, config.values['CONST_HYSTERESIS'])


# Установка настроек.
def settings_set(action=''):
    global settings_step
    global display_show
    global display_value
    global config
    min_value = 0
    max_value = 0
    step = ''
    key = False
    if settings_step == 0:
        display_show = 'first'
    elif settings_step == 1:
        key = 'CONST_TIMER'
        step = config.values['CONST_TIMER_STEP']
        min_value = config.values['CONST_TIMER_MIN_VALUE']
        max_value = config.values['CONST_TIMER_MAX_VALUE']
    elif settings_step == 2:
        key = 'CONST_TEMPERATURE'
        step = config.values['CONST_TEMPERATURE_STEP']
        min_value = config.values['CONST_TEMPERATURE_MIN_VALUE']
        max_value = config.values['CONST_TEMPERATURE_MAX_VALUE']
    if key:
        if action == '<' and config.values[key] > min_value:
            config.values[key] -= step
        elif action == '>' and config.values[key] < max_value:
            config.values[key] += step
        display_show = key
        display_value = config.values[key]
        config.save()


# Терморегулятор
async def thermostat(analog_input):
    global heating
    global time_left
    global current_t
    global start
    global thermo
    while True:
        if time_left > 0 and start == True:
            thermo.thermostat(analog_input, config.values['CONST_TEMPERATURE'])
            heating = thermo.heating
            current_t = thermo.current_t
            if thermo.error:
                error(thermo.error)
        await asyncio.sleep(1)


# Отображение ошибки.
def error(message=''):
    global display_show
    global start
    display_show = 'error'
    start = False
    print(message)


# Плавное мигание светодиодом.
async def blink(led):
    global heating
    global start
    while True:
        if heating and start and time_left > config.values['CONST_PURGING_HEATER']:
            duty = 0
            direction = 1
            for _ in range(4 * 256):
                duty += direction
                if duty > 255:
                    duty = 255
                    direction = -1
                elif duty < 0:
                    duty = 0
                    direction = 1
                led.duty_u16(duty * duty)
                await asyncio.sleep(0.001)
        else:
            led.duty_u16(0)
            await asyncio.sleep(0.001)


# Таймер, отчитывающий секунды в обратную сторону.
async def tick():
    global time_left
    global start
    while True:
        if time_left > 0 and start == True:
            time_left -= 1
        await asyncio.sleep(1)


# Опрос кнопок.
async def buttons(buttons_list):
    global time_left
    global config
    global settings_step
    global settings_time_out
    global start
    global display_show
    settings_step_max = 2  # Максимальный шаг установки параметров.
    debounce_time = 0 # Debouncing.
    while True:
        for i in range(len(buttons_list)):
            button = buttons_list[i]
            if button.value() == 0 and (int(ticks_ms()) - debounce_time) > 300:
                debounce_time = ticks_ms()
                print("Press button", i)
                # Действия кнопок.
                if i == 0:  # Start/Stop
                    display_show = 'first'
                    settings_step = 0
                    time_left = config.values['CONST_TIMER']
                    if start:
                        start = False
                    else:
                        start = True
                elif i == 1:  # Выбор настройки параметров.
                    if settings_step < settings_step_max:
                        settings_step += 1
                    else:
                        settings_step = 0
                    settings_set()
                elif i == 2:  # Меньше
                    settings_set('<')
                    settings_time_out = 0
                elif i == 3:  # Больше
                    settings_set('>')
                    settings_time_out = 0
                # Интервал между нажатиями на кнопки.
                await asyncio.sleep(0.5)
        await asyncio.sleep(0.001)


# Отображение информации на дисплее.
async def display(indicator):
    global display_time_fps
    global settings_step
    global display_show
    global display_value
    global settings_time_out
    global current_t
    global time_left
    global start
    global config
    while True:
        # Возврат к начальному экрану по истечении 10 тактов
        # из меню настроек.
        if settings_time_out >= 10:
            display_show = 'first'
            settings_step = 0
            settings_time_out = 0

        if display_show == 'starting':
            indicator.value = config.values['CONST_LOGO']
            indicator.render(display_show)
            display_show = 'first'
        # Обратный отчет таймера / температура. Основной процесс.
        elif display_show == 'first':
            indicator.start = start
            indicator.time_left = time_left
            indicator.current_t = current_t

        # Установка времени таймера / температуры.
        elif display_show == 'CONST_TIMER' or display_show == 'CONST_TEMPERATURE':
            indicator.value = display_value

        # Вывод на дисплей.
        indicator.render(display_show)

        # Счетчик возврата к начальному экрану.
        if display_show != 'first' and display_show != 'start':
            settings_time_out += display_time_fps

        await asyncio.sleep(display_time_fps)


# Управление реле.
async def relay(relays):
    global heating
    global start
    global time_left
    while True:
        relays[0].value(1 if (heating and start and time_left > config.values['CONST_PURGING_HEATER']) else 0)
        relays[1].value(1 if (start and time_left > 0) else 0)
        await asyncio.sleep(0.01)


# Основная функция.
async def main():
    print(f"Device: {config.values['CONST_LOGO']}")
    # Запуск цикла обработки событий.
    loop.create_task(buttons(list_buttons))
    loop.create_task(display(dp))
    loop.create_task(thermostat(sensor_voltage))
    loop.create_task(relay(list_relays))
    loop.create_task(blink(pwm))
    loop.create_task(tick())

    i = 60
    while True:
        if i >= 60:
            # Служебная информация.
            s = statvfs('/')
            print(f"{uname()}")
            print(f"Free storage: {s[0] * s[3] / 1024} KB")
            print(f"{mem_info()}")
            print(f"CPU Freq: {freq() / 1000000}Mhz")
            print("Settings:\n", "\n".join("{}: {}".format(k,v) for k,v in config.values.items()),
                  "\nID:", "".join("{:02X}".format(b) for b in unique_id()))
            # Сборка мусора.
            gc.collect()
            gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
            i = 0

        # Информация о состоянии устройства.
        print('>>>Time:', time_left,
              '; Process', heating and start,
              '; Current T', round(current_t, 2),
              )
        i += 1
        await asyncio.sleep(1)


# Создание цикла обработки событий.
loop = asyncio.get_event_loop()
# Создание задачи для запуска основной функции.
loop.create_task(main())

try:
    # Запуск бесконечного цикла обработки событий.
    loop.run_forever()
except Exception as e:
    print(f"Error occurred: {e}")
except KeyboardInterrupt:
    print('Program Interrupted by the user')
