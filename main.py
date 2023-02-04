import argparse
import json
import subprocess
import os
from queue import Queue
import threading
from typing import Tuple
import psycopg2
import datetime
from tools import *
import logging
import signal
import time

# hyper parameters
message_encoding = 'utf-8'
q_size = 20

expected_info_dict = [
    {'aws_name': 'user_id', 'sql_name': 'user_id', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'device_type', 'sql_name': 'device_type', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'ip', 'sql_name': 'masked_ip', 'type': str, 'process': encode_str, 'required': True},
    {'aws_name': 'device_id', 'sql_name': 'masked_device_id', 'type': str, 'process': encode_str, 'required': True},
    {'aws_name': 'locale', 'sql_name': 'locale', 'type': str, 'process': None, 'required': True},
    {'aws_name': 'app_version', 'sql_name': 'app_version', 'type': int, 'process': version_to_int, 'required': True},
    {'aws_name': 'create_date', 'sql_name': 'create_date', 'type': str, 'process': datetime.date.today,
     'required': False},
]

queue_url = 'http://localhost:4566/000000000000/login-queue'
logging.basicConfig(level=logging.DEBUG)

# Global variables
stop = False  # could be replaced by threading.Event()


def get_insert_query() -> str:
    """
    Get the insert query for the table user_logins
    :return: the insert query needed for the table user_logins
    """
    insert_query = "INSERT INTO user_logins ("
    for ele in expected_info_dict:
        key = ele['sql_name']
        insert_query += key + ", "

    insert_query = insert_query[:-2] + ") VALUES ("
    for ele in expected_info_dict:
        insert_query += "%s, "

    insert_query = insert_query[:-2] + ")"
    logging.info(insert_query)
    return insert_query


def parse_raw_values(stdout: str) -> Tuple[bool, dict]:
    """
    Parse the raw values from AWS. If the message is not correct, return False and empty dict.
    Since the message from AWS is wrong not every frequently, and we do want to read more messages,
    we do not exit the program, but just record the incorrect message and abandon it.
    Then, continue to read more messages.
    :param stdout: the raw values in the stdout from AWS
    :return: True and the parsed values if the message is correct, False and empty dict otherwise
    """
    try:
        json_obj = json.loads(stdout)
        body = json_obj['Messages'][0]['Body']
        body = json.loads(body)
    except Exception as e:
        logging.warning("Error parsing message from AWS")
        logging.warning(e)
        logging.warning(stdout)
        return False, {}

    out_dict = {}
    for ele in expected_info_dict:
        aws_key = ele['aws_name']
        sql_key = ele['sql_name']
        process_func = ele['process']
        if ele['required']:
            if aws_key not in body:
                # Exit before reading more messages
                logging.warning("Error: missing key: " + aws_key)
                logging.warning("Wrong message format")
                logging.warning(stdout)
                return False, {}
            else:
                if process_func is not None:
                    out_dict[sql_key] = process_func(body[aws_key])
                else:
                    out_dict[sql_key] = body[aws_key]
        else:
            out_dict[sql_key] = process_func()
    return True, out_dict


def get_from_aws(queue: Queue):
    """
    Get messages from AWS and put them into the queue
    :param queue: the queue to put the messages into
    :return: None
    """
    while not stop:
        # Execute aws command:
        #   awslocal sqs receive-message --queue-url {queue_url}
        raw_value = subprocess.run(['awslocal', 'sqs', 'receive-message', '--queue-url', queue_url],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if raw_value.returncode != 0:
            logging.error("Error getting message from AWS")
            continue
        else:
            stdout = raw_value.stdout.decode(message_encoding)
            is_correct, out_dict = parse_raw_values(stdout)

            if is_correct:
                queue.put(out_dict)
    logging.info("Exit producer thread")


def write_to_sql(queue: Queue, connection: psycopg2.connect):
    """
    Write the messages from the queue to the SQL database
    :param queue: the queue to get the messages from
    :param connection: the connection to the SQL database
    :return: None
    """
    insert_query = get_insert_query()
    while not stop or queue.qsize() > 0:
        if queue.qsize() > 0:
            message = queue.get()
            logging.debug(message)
            record_to_insert = []
            for ele in expected_info_dict:
                key = ele['sql_name']
                record_to_insert.append(message[key])
            # change to tuple
            record_to_insert = tuple(record_to_insert)
            cursor = connection.cursor()
            cursor.execute(insert_query, record_to_insert)
            connection.commit()
    logging.info("Exit consumer thread")


def app(args):
    """
    The main function of the program
    :return: None
    """

    time.sleep(10)  # wait for the database to start
    signal.signal(signal.SIGINT, signal_handler)
    queue = Queue(q_size)  # limit the size of the queue
    psql_connection = None
    if args.local:
        host = "localhost"
    else:
        # Set environment variable to connect to localstack in case ssh connection do not load it
        os.environ["LOCALSTACK_HOST"] = "localstack"
        host = "postgres"

    try:
        logging.info("Connecting to postgreSQL")
        psql_connection = psycopg2.connect("dbname=postgres user=postgres password=postgres host={}".format(host))
    except Exception as e:
        logging.error("Error connecting to postgreSQL: " + str(e))
        if psql_connection is not None:
            psql_connection.close()
        logging.error("Exit with Error")
        exit(1)

    # Create worker threads
    producer = threading.Thread(target=get_from_aws, args=(queue,))
    consumer = threading.Thread(target=write_to_sql, args=(queue, psql_connection,))

    try:
        logging.info("Starting producer and consumer")
        producer.start()
        consumer.start()
        # Keep the main thread running, otherwise signals are ignored.
        while True:
            time.sleep(0.5)
    except ServiceExit as e:
        global stop
        stop = True
    finally:
        # Wait for the worker to finish
        logging.info("Waiting for producer and consumer to finish")
        producer.join()
        consumer.join()

    if psql_connection is not None:
        psql_connection.close()

    if queue.qsize() > 0:
        logging.info("Logging remaining messages in the queue in case of error")
        while queue.qsize() > 0:
            logging.info(queue.get())

    logging.info("Exit with Success")


# %%
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", help="use local machine network path", default=False, action="store_true")
    args = parser.parse_args()
    app(args)
