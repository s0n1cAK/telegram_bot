FROM python:3.9.13-buster
COPY . /app
RUN python3 -m pip install -r /app/requirements.txt
RUN python3 -m pip uninstall telebot
RUN python3 -m pip install telebot
ENTRYPOINT ["python3", "/app/main.py"]
