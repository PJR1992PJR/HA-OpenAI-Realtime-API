COPY assistant.py /assistant.py
COPY run.sh      /run.sh
RUN chmod +x /run.sh
ENTRYPOINT ["/run.sh"]
