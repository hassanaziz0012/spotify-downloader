FROM ubuntu:20.04

ENV TZ=Etc/UTC
ENV DEBIAN_FRONTEND=noninteractive

COPY ./requirements.txt /tmp/requirements.txt
RUN apt-get update && \
    apt-get install -y python3 python3-pip jq curl mpv fzf git && \
    pip3 install -r /tmp/requirements.txt && \
    apt-get clean

#RUN git clone https://github.com/pystardust/ytfzf.git /home
    # cd /home && \
    # make install doc

# Copy files from host's current directory to container's home directory
WORKDIR /app
COPY ./spotify-downloader.py /app
COPY ./config.json /app
COPY ./ytfzf /usr/bin

CMD ["bash"]

