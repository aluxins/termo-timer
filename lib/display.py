# Перевод секунд в формат - [часы, минуты, секунды].
def formatted_time(seconds):
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return [hours, minutes, seconds]

class Display(object):
    """indicator - экземпляр класса TM1637.
    \n brightness - яркость индикатора."""
    def __init__(self, indicator, brightness = 5, time_fps = 0.1):
        if not 0.01 <= time_fps <= 0.5:
            raise ValueError("Time fps out of range")
        indicator.brightness(brightness)
        self.time_fps = time_fps
        self.indicator = indicator
        self.time_left = 0
        self.current_t = 0
        self.start = False
        self.colon_blink = 0  # Для мигания разделителя.
        self.tick_flag_1s = 0  # 1 секундный счетчик. Для переключения таймер/температура.
        self.tick_flag_10s = 0  # 10 секундный счетчик. Для переключения таймер/температура.
        self.value = ''
        self.error = ''

    def _first(self):
        if self.time_left > 0 and self.start == True:
            if self.tick_flag_10s <= 7:
                f_time = formatted_time(self.time_left)
                segments = [
                    self.indicator.encode_digit(f_time[0] // 10),
                    self.indicator.encode_digit(f_time[0] % 10),
                    self.indicator.encode_digit(f_time[1] // 10),
                    self.indicator.encode_digit(f_time[1] % 10)
                ]
                # Мигание разделителя.
                if self.tick_flag_1s // 0.5 != False:
                    segments[1] |= 0x80  # colon on
                self.indicator.write(segments)
            elif 7 < self.tick_flag_10s <= 8.5:
                self.indicator.temperature(round(self.current_t))
        else:
            self.indicator.show(' off', colon=False)

    def _const_timer(self):
        if self._blink():
            f_time = formatted_time(self.value)
            self.indicator.numbers(f_time[0], f_time[1], colon=True)

    def _const_temperature(self):
        if self._blink():
            self.indicator.temperature(self.value)

    def _blink(self):
        if self.tick_flag_1s >= 0.7:
            self.indicator.write([0, 0, 0, 0])
            return False
        return True

    def _starting(self):
        self.indicator.scroll(self.value)

    def _error(self):
        self.indicator.show(' Err', colon=False)

    """id_display - идентификатор экрана для отрисовки."""
    def render(self, id_display):
        try:
            getattr(self, f"_{id_display.lower()}")()
        except Exception as e:
            self.error = f"Экран {id_display.lower()} не найден: {e}"
        self.tick_flag_1s = self.tick_flag_1s + self.time_fps if self.tick_flag_1s < 1 else 0
        self.tick_flag_10s = self.tick_flag_10s + self.time_fps if self.tick_flag_10s < 10 else 0
