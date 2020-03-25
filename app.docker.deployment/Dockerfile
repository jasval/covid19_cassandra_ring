FROM python:3.7-alpine
WORKDIR /root
COPY . /root
RUN pip install -U -r requirements.txt
EXPOSE 8080
CMD ["python", "frontend-covid-api.py"]