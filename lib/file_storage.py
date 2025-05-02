# JSON файл настроек будет создан при первом запуске программы
# со значениями по умолчанию.

import ujson as json

class FileStorage(object):
    def __init__(self, default, file_name):
        self.values = default
        self.file_name = file_name
        try:
            with open(self.file_name, 'r') as f:  # noinspection PyTypeChecker
                self.values = json.load(f)
        except Exception as err:
            print(f"{err}")
            self.save()

    # Сохранение значения параметра настроек в JSON файл
    def save(self, key=False, value=False):
        if key:
            self.values[key] = value
        try:
            with open(self.file_name, 'w') as f:  # noinspection PyTypeChecker
                json.dump(self.values, f)
        except Exception as err:
            print(f"Ошибка при сохранении конфигурации: {err}")