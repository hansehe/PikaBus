import logging
logging.basicConfig(format='[%(levelname)s] service={SERVICE_NAME} message=%(name)s - %(message)s', level=logging.DEBUG)
logging.getLogger("pika").setLevel('WARNING')
