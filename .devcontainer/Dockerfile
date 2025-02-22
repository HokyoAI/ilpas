FROM mcr.microsoft.com/vscode/devcontainers/python:3.12
ARG USERNAME=vscode

# install poetry and dev tools
RUN echo "\npoetry config virtualenvs.in-project true" >> "/home/$USERNAME/.bashrc"
RUN pipx install poetry==1.8.0
RUN pipx install black==24.8.0 isort==5.13.2 pytest==8.3.2 mypy==1.11.1