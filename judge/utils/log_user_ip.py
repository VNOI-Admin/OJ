import logging

user_ip_logger = logging.getLogger('judge.user_ip_logger')


def log_user_ip(request, message):
    try:
        ip = request.headers['CF-Connecting-IP']
    except KeyError:
        ip = request.META['REMOTE_ADDR']
    # I didn't log the timestamp here because
    # the logger can handle it.
    user_ip_logger.info(
        '%s,%s',
        ip,
        message,
    )
