# The api's dependencies come with the tools: mypy needs them to type the api's code. Wheels only: building a package
# from its source would fetch its build dependencies without checking their hashes.
FROM python:3.12-slim-bookworm
COPY server/requirements-test.lock /tmp/api.lock
COPY scripts/lint/requirements.lock /tmp/lint.lock
RUN pip install --no-cache-dir --require-hashes --no-deps --only-binary :all: -r /tmp/api.lock \
 && pip install --no-cache-dir --require-hashes --no-deps --only-binary :all: -r /tmp/lint.lock \
 && rm /tmp/api.lock /tmp/lint.lock
USER 1000:1000
WORKDIR /src
