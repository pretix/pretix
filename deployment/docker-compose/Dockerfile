FROM pretix/standalone
USER root
RUN apt-get update && apt-get -y install cron
RUN /etc/init.d/cron start
USER pretixuser
RUN echo "15,45 * * * * cd /pretix/src && python3 -m pretix runperiodic" > /tmp/crontab_runperiodic
RUN crontab /tmp/crontab_runperiodic
RUN rm /tmp/crontab_runperiodic
ENTRYPOINT ["pretix"]
CMD ["all"]
