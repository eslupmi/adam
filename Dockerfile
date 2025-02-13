FROM python:3.12.3
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5067

VOLUME /config

CMD ["python", "app.py"]
