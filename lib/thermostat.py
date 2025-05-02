class Thermostat(object):
    def __init__(self, temperature_table: dict, t_hysteresis: float = 3.0):
        if t_hysteresis < 0:
            raise ValueError("Значение гистерезиса не должно быть ниже нуля.")
        self.__temperature_table = temperature_table  # Температурная таблица NTC.
        self.heating = 0  # Состояние нагрева.
        self.__stable_temperature = 0  # Температура стабилизации.
        self.current_t = 0  # Текущая температура NTC.
        self.__inertia_t = 0  # Текущая температурная инерция.
        self.__t_hysteresis = t_hysteresis  # Температурный гистерезис.
        self.error = ''  # Состояние ошибки.

    # Вычисление температуры по значению напряжения на входе АЦП
    def __calc_temp(self, adc):
        t_start = 0
        v_start = 0
        t_end = 0
        v_end = 0
        for t, v in sorted(self.__temperature_table.items()):
            if adc > v:
                t_end = t
                v_end = v
                break
            else:
                t_start = t
                v_start = v
        if t_start == 0:  # Минимальная температура.
            return t_end
        if t_end == 0:  # Максимальная температура.
            return t_start
        else:  # Температура в заданном диапазоне.
            return self.__interpolation(t_start, t_end, v_start, v_end, adc)

    # Функция линейной интерполяции для вычисления промежуточного
    # значения температуры между двумя соседними значениями.
    @staticmethod
    def __interpolation(t1, t2, v1, v2, v):
        return t1 + ((v - v1) * (t2 - t1)) / (v2 - v1)

    # Терморегулятор
    def thermostat(self, analog_input, stable_temperature):
        self.__stable_temperature = stable_temperature
        self.error = ''
        conversion_factor = 3.3 / 65535
        reading = analog_input.read_u16() * conversion_factor
        self.current_t = self.__calc_temp(reading)
        if reading <= 3 and self.current_t < (self.__stable_temperature - self.__inertia_t):
            self.heating = 1
            self.__inertia_t = 0
        else:
            self.heating = 0
            self.__inertia_t = self.__t_hysteresis
        if reading > 3:  # Если значение на входе АЦП > 3V, считать обрыв NTC.
            self.error = 'Error: обрыв NTC.'
