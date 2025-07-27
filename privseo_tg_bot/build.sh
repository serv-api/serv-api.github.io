#!/bin/bash
python -m pip install --upgrade "pip<24.0"  # Понижаем pip для совместимости
pip install wheel==0.38.4 setuptools==59.8.0  # Конкретные стабильные версии
pip install -r requirements.txt --no-build-isolation