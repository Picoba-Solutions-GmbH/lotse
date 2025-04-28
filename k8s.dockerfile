FROM python:3.13.2-slim-bookworm

RUN apt-get update && apt-get install -y p7zip-full curl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
RUN install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

WORKDIR /usr/src/app

COPY ./requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

ENV DATABASE_URL=your_database_url
ENV OPENAPI_PREFIX_PATH=
ENV DEPLOYMENT_STAGE=
ENV APP_VERSION="Lotse"
ENV API_VERSION="0.1.0"
ENV PYTHONUNBUFFERED=1

CMD [ "fastapi", "run", "main.py", "--host", "0.0.0.0" ]