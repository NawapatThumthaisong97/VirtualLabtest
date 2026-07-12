FROM codercom/code-server:latest

# so students can run `sqlite3 /data/library.db` straight from the IDE terminal
USER root
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# hide top-level dotfiles/folders (.cache, .config, .local, .bashrc, ...) in the Explorer
# sidebar - belt-and-suspenders alongside opening straight into /home/coder/project,
# since a browser can remember an old "last opened folder" (the home dir) from before
COPY settings.json /home/coder/.local/share/code-server/User/settings.json
RUN chown -R coder:coder /home/coder/.local

USER coder
